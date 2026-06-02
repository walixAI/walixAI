"""Metrics, sentiment, forecast, and pipeline-summary endpoints for Walix."""
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import redis_client
from app.models.lead import Lead, LeadStatus
from app.models.metrics import DailyMetric, SentimentSnapshot
from app.models.pipeline import PipelineStage
from app.models.scoring import LeadScore
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])
pipeline_router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

_MULTI_BRANCH_ROLES = {UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER}
_TERMINAL = [LeadStatus.PERDIDO, LeadStatus.CALIFICADO]

CACHE_TTL = 300  # 5 min


# ── Schemas ────────────────────────────────────────────────────────────────────

class DailyMetricOut(BaseModel):
    metric_date: date
    leads_created: int
    leads_qualified: int
    leads_won: int
    leads_lost: int
    messages_sent: int
    messages_received: int
    calls_logged: int
    tasks_completed: int
    quotes_sent: int
    avg_first_response_sec: int

    model_config = ConfigDict(from_attributes=True)


class PeriodSummary(BaseModel):
    leads_created: int = 0
    leads_qualified: int = 0
    leads_won: int = 0
    leads_lost: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    calls_logged: int = 0
    tasks_completed: int = 0
    quotes_sent: int = 0
    avg_first_response_sec: int = 0
    conversion_rate: float = 0.0


class DashboardMetricsOut(BaseModel):
    period: str
    branch_id: uuid.UUID
    current: PeriodSummary
    previous: PeriodSummary | None
    delta: dict[str, Any] | None
    daily: list[DailyMetricOut]


class SentimentSnapshotOut(BaseModel):
    snapshot_date: date
    overall_score: float
    distribution: dict[str, Any]
    by_stage: dict[str, Any]
    by_agent: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SentimentOut(BaseModel):
    current: SentimentSnapshotOut | None
    trend: float | None
    insight: str


class ForecastLeadOut(BaseModel):
    lead_id: uuid.UUID
    name: str | None
    wa_phone: str
    score: int
    stage_name: str | None


class ForecastOut(BaseModel):
    pipeline_forecast: dict[str, int]
    high_probability_leads: list[ForecastLeadOut]
    at_risk_leads: list[ForecastLeadOut]


# ── GET /api/metrics/dashboard ────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardMetricsOut)
async def get_dashboard_metrics(
    period: str = Query(default="month", pattern="^(week|month|quarter)$"),
    compare: bool = Query(default=False),
    branch_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardMetricsOut:
    resolved_branch_id = _resolve_branch(branch_id, current_user)
    cache_key = f"metrics:dashboard:{resolved_branch_id}:{period}:{compare}"

    cached = await redis_client.get(cache_key)
    if cached:
        return DashboardMetricsOut(**json.loads(cached))

    days = {"week": 7, "month": 30, "quarter": 90}[period]
    today = datetime.now(timezone.utc).date()
    period_start = today - timedelta(days=days - 1)

    rows = await db.execute(
        select(DailyMetric).where(
            DailyMetric.branch_id == resolved_branch_id,
            DailyMetric.metric_date >= period_start,
            DailyMetric.metric_date <= today,
        ).order_by(DailyMetric.metric_date.asc())
    )
    metrics = rows.scalars().all()
    daily = [DailyMetricOut.model_validate(m) for m in metrics]
    current = _sum_period(metrics)

    previous: PeriodSummary | None = None
    delta: dict[str, Any] | None = None
    if compare:
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)
        prev_rows = await db.execute(
            select(DailyMetric).where(
                DailyMetric.branch_id == resolved_branch_id,
                DailyMetric.metric_date >= prev_start,
                DailyMetric.metric_date <= prev_end,
            )
        )
        prev_metrics = prev_rows.scalars().all()
        previous = _sum_period(prev_metrics)
        delta = _compute_delta(current, previous)

    out = DashboardMetricsOut(
        period=period,
        branch_id=resolved_branch_id,
        current=current,
        previous=previous,
        delta=delta,
        daily=daily,
    )
    try:
        await redis_client.set(cache_key, out.model_dump_json(), ex=CACHE_TTL)
    except Exception:
        logger.warning("metrics: Redis cache write failed for key=%s", cache_key)

    return out


# ── GET /api/metrics/sentiment ────────────────────────────────────────────────

@router.get("/sentiment", response_model=SentimentOut)
async def get_sentiment(
    branch_id: uuid.UUID | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SentimentOut:
    resolved_branch_id = _resolve_branch(branch_id, current_user)

    # Latest snapshot
    latest_row = await db.execute(
        select(SentimentSnapshot).where(
            SentimentSnapshot.branch_id == resolved_branch_id,
        ).order_by(SentimentSnapshot.snapshot_date.desc()).limit(1)
    )
    latest = latest_row.scalar_one_or_none()

    trend: float | None = None
    if latest:
        cutoff_date = latest.snapshot_date - timedelta(days=days)
        old_row = await db.execute(
            select(SentimentSnapshot).where(
                SentimentSnapshot.branch_id == resolved_branch_id,
                SentimentSnapshot.snapshot_date <= cutoff_date,
            ).order_by(SentimentSnapshot.snapshot_date.desc()).limit(1)
        )
        old = old_row.scalar_one_or_none()
        if old:
            trend = round(latest.overall_score - old.overall_score, 4)

    insight = await _sentiment_insight(latest)

    return SentimentOut(
        current=SentimentSnapshotOut.model_validate(latest) if latest else None,
        trend=trend,
        insight=insight,
    )


# ── GET /api/metrics/forecast ────────────────────────────────────────────────

@router.get("/forecast", response_model=ForecastOut)
async def get_forecast(
    branch_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastOut:
    resolved_branch_id = _resolve_branch(branch_id, current_user)

    # Active leads with a current_score
    leads_result = await db.execute(
        select(Lead).where(
            Lead.branch_id == resolved_branch_id,
            Lead.status.notin_(_TERMINAL),
            Lead.current_score.isnot(None),
        ).order_by(Lead.current_score.desc())
    )
    leads = leads_result.scalars().all()

    # Preload stage names
    stage_ids = {lead.pipeline_stage_id for lead in leads if lead.pipeline_stage_id}
    stage_names: dict[uuid.UUID, str] = {}
    if stage_ids:
        stages_result = await db.execute(
            select(PipelineStage).where(PipelineStage.id.in_(stage_ids))
        )
        stage_names = {s.id: s.name for s in stages_result.scalars().all()}

    # Stage order_index for "advanced stage" detection in at_risk
    stage_orders: dict[uuid.UUID, int] = {}
    if stage_ids:
        for s in stages_result.scalars():
            stage_orders[s.id] = s.order_index
    # Re-query since we already consumed the result
    if stage_ids:
        so_result = await db.execute(
            select(PipelineStage.id, PipelineStage.order_index).where(
                PipelineStage.id.in_(stage_ids)
            )
        )
        stage_orders = {r[0]: r[1] for r in so_result.fetchall()}

    pipeline_forecast = {"high": 0, "medium": 0, "low": 0}
    high_probability: list[ForecastLeadOut] = []
    at_risk: list[ForecastLeadOut] = []

    for lead in leads:
        score = lead.current_score or 0
        stage_name = stage_names.get(lead.pipeline_stage_id) if lead.pipeline_stage_id else None
        order = stage_orders.get(lead.pipeline_stage_id, 0) if lead.pipeline_stage_id else 0

        if score >= 70:
            pipeline_forecast["high"] += 1
            high_probability.append(ForecastLeadOut(
                lead_id=lead.id, name=lead.name, wa_phone=lead.wa_phone,
                score=score, stage_name=stage_name,
            ))
        elif score >= 30:
            pipeline_forecast["medium"] += 1
        else:
            pipeline_forecast["low"] += 1
            if order >= 2:  # at-risk only in stages beyond the first two
                at_risk.append(ForecastLeadOut(
                    lead_id=lead.id, name=lead.name, wa_phone=lead.wa_phone,
                    score=score, stage_name=stage_name,
                ))

    return ForecastOut(
        pipeline_forecast=pipeline_forecast,
        high_probability_leads=high_probability[:20],
        at_risk_leads=at_risk[:20],
    )


# ── GET /api/pipeline/sentiment-summary ──────────────────────────────────────

@pipeline_router.get("/sentiment-summary", response_model=SentimentSnapshotOut | None)
async def get_pipeline_sentiment_summary(
    branch_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SentimentSnapshotOut | None:
    """Returns the latest sentiment snapshot (by_stage breakdown) for the branch."""
    resolved_branch_id = _resolve_branch(branch_id, current_user)

    row = await db.execute(
        select(SentimentSnapshot).where(
            SentimentSnapshot.branch_id == resolved_branch_id,
        ).order_by(SentimentSnapshot.snapshot_date.desc()).limit(1)
    )
    snapshot = row.scalar_one_or_none()
    if snapshot is None:
        return None
    return SentimentSnapshotOut.model_validate(snapshot)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_branch(
    branch_id: uuid.UUID | None, user: User
) -> uuid.UUID:
    resolved = branch_id or user.branch_id
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="branch_id is required for users without an assigned branch",
        )
    if user.role not in _MULTI_BRANCH_ROLES and user.branch_id and resolved != user.branch_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this branch")
    return resolved


def _sum_period(metrics: list[DailyMetric]) -> PeriodSummary:
    if not metrics:
        return PeriodSummary()
    s = PeriodSummary(
        leads_created=sum(m.leads_created for m in metrics),
        leads_qualified=sum(m.leads_qualified for m in metrics),
        leads_won=sum(m.leads_won for m in metrics),
        leads_lost=sum(m.leads_lost for m in metrics),
        messages_sent=sum(m.messages_sent for m in metrics),
        messages_received=sum(m.messages_received for m in metrics),
        calls_logged=sum(m.calls_logged for m in metrics),
        tasks_completed=sum(m.tasks_completed for m in metrics),
        quotes_sent=sum(m.quotes_sent for m in metrics),
        avg_first_response_sec=int(
            sum(m.avg_first_response_sec for m in metrics if m.avg_first_response_sec)
            / max(1, sum(1 for m in metrics if m.avg_first_response_sec))
        ),
    )
    s.conversion_rate = (
        round(s.leads_won / s.leads_created * 100, 1) if s.leads_created else 0.0
    )
    return s


def _compute_delta(current: PeriodSummary, previous: PeriodSummary) -> dict[str, Any]:
    fields = [
        "leads_created", "leads_won", "leads_lost", "messages_sent",
        "calls_logged", "tasks_completed", "conversion_rate",
    ]
    delta: dict[str, Any] = {}
    for f in fields:
        curr_val = getattr(current, f)
        prev_val = getattr(previous, f)
        delta[f] = {
            "current": curr_val,
            "previous": prev_val,
            "diff": round(curr_val - prev_val, 2),
            "pct_change": round((curr_val - prev_val) / prev_val * 100, 1) if prev_val else None,
        }
    return delta


async def _sentiment_insight(snapshot: SentimentSnapshot | None) -> str:
    if snapshot is None:
        return "No hay datos de sentimiento disponibles aún."
    try:
        prompt = (
            f"Analiza este resumen de sentimiento de clientes y escribe UNA sola oración de insight en español:\n"
            f"Score general: {snapshot.overall_score:.2f}/1.0\n"
            f"Distribución: {json.dumps(snapshot.distribution, ensure_ascii=False)}\n"
            f"Solo la oración, sin texto adicional."
        )
        resp = await _anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        logger.warning("metrics: sentiment insight Claude call failed")
        score = snapshot.overall_score
        if score >= 0.75:
            return "El sentimiento general de los leads es positivo y favorable."
        elif score >= 0.5:
            return "El sentimiento general de los leads es neutro con áreas de mejora."
        else:
            return "Se detecta sentimiento negativo en varios leads activos — requiere atención."
