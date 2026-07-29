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
from app.models.agent import AgentSuggestion
from app.models.conversation import Conversation, ConversationHandler, Message, MessageRole
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.metrics import DailyMetric, SentimentSnapshot
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import resolve_default_pipeline_id
from app.models.scoring import LeadScore
from app.models.tenant import Branch, Tenant
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


# ── GET /api/metrics/roi ──────────────────────────────────────────────────────

# Minutes saved per bot message (marketing assumption, documented in response)
_BOT_MIN_PER_MESSAGE: float = 3.3
_QUALIFY_SCORE_THRESHOLD: float = 60.0
_RESPONSE_WAIT_MINUTES: int = 60


class PipelineStageROI(BaseModel):
    stage_name: str
    stage_key: str | None
    count: int
    avg_days_in_stage: float | None


class ROIOut(BaseModel):
    period_days: int
    period_label: str
    # Captación
    leads_total: int
    leads_by_source: dict[str, int]
    # Calificación del bot
    bot_qualified: int
    bot_qualification_rate: float
    avg_qualification_score: float | None
    avg_messages_to_qualify: float | None
    handoffs_executed: int
    # Conversión
    converted: int
    conversion_rate: float
    pipeline_by_stage: list[PipelineStageROI]
    # Tiempo ahorrado
    bot_messages_sent: int
    estimated_minutes_saved: float
    estimated_hours_saved: float
    # Valor generado
    revenue_per_conversion: float | None
    estimated_revenue: float | None
    # Respuesta humana
    avg_response_time_minutes: float | None
    leads_waiting_response: int
    # Sentimiento
    sentiment_breakdown: dict[str, int]
    # Agentes IA
    agent_suggestions_generated: int
    agent_suggestions_accepted: int
    agent_acceptance_rate: float
    # Transparencia de supuestos
    assumptions: dict[str, str]


_PERIOD_LABELS = {7: "Últimos 7 días", 30: "Últimos 30 días", 90: "Últimos 90 días"}


@router.get("/roi", response_model=ROIOut)
async def get_roi(
    period: int = Query(30, ge=7, le=90, description="Days back: 7, 30, or 90"),
    branch_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ROIOut:
    """ROI dashboard — aggregates across all tenant branches (or one if specified).

    Assumption documented in response.assumptions:
      bot_minutes_per_message = 3.3  (industry average for WhatsApp support)
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=period)

    # Resolve branches to aggregate
    if branch_id:
        branch_ids = [branch_id]
    else:
        branches_result = await db.execute(
            select(Branch.id).where(
                Branch.tenant_id == current_user.tenant_id,
                Branch.is_active.is_(True),
            )
        )
        branch_ids = list(branches_result.scalars().all())

    if not branch_ids:
        branch_ids = []

    tenant = await db.get(Tenant, current_user.tenant_id)
    revenue_cfg = float(tenant.roi_revenue_per_conversion) if tenant and tenant.roi_revenue_per_conversion else None

    # ── Captación ─────────────────────────────────────────────────────────────
    leads_result = await db.execute(
        select(Lead).where(
            Lead.tenant_id == current_user.tenant_id,
            Lead.created_at >= since,
            Lead.deleted_at.is_(None),
            Lead.branch_id.in_(branch_ids) if branch_ids else Lead.id.isnot(None),
        )
    )
    leads = leads_result.scalars().all()
    leads_total = len(leads)
    lead_ids = [l.id for l in leads]

    leads_by_source: dict[str, int] = {}
    for l in leads:
        src = getattr(l.source, "value", str(l.source))
        leads_by_source[src] = leads_by_source.get(src, 0) + 1

    # ── Calificación del bot ──────────────────────────────────────────────────
    qualified = [l for l in leads if l.qualification_score is not None and l.qualification_score >= _QUALIFY_SCORE_THRESHOLD]
    bot_qualified = len(qualified)
    bot_qualification_rate = round(bot_qualified / leads_total * 100, 1) if leads_total else 0.0

    scores = [l.qualification_score for l in leads if l.qualification_score is not None]
    avg_qualification_score = round(sum(scores) / len(scores), 1) if scores else None

    handoffs_executed = sum(1 for l in leads if l.handoff_at is not None)

    # avg_messages_to_qualify: count bot messages in conversations for qualified leads
    avg_messages_to_qualify: float | None = None
    if qualified and lead_ids:
        # Get first conversation per qualified lead and count assistant messages
        conv_result = await db.execute(
            select(Conversation.id, Conversation.lead_id).where(
                Conversation.lead_id.in_([l.id for l in qualified]),
            ).order_by(Conversation.started_at)
        )
        conv_rows = conv_result.all()
        conv_ids = [r[0] for r in conv_rows]

        if conv_ids:
            msg_count_result = await db.execute(
                select(
                    Message.conversation_id,
                    func.count(Message.id).label("msg_count"),
                ).where(
                    Message.conversation_id.in_(conv_ids),
                    Message.role == MessageRole.ASSISTANT,
                ).group_by(Message.conversation_id)
            )
            msg_counts = {r[0]: r[1] for r in msg_count_result.all()}
            if msg_counts:
                avg_messages_to_qualify = round(sum(msg_counts.values()) / len(msg_counts), 1)

    # ── Conversión ────────────────────────────────────────────────────────────
    # Resolve default pipeline once for both won_stages and all_stages queries
    roi_pipeline_id = await resolve_default_pipeline_id(
        current_user.tenant_id, db, user_branch_id=current_user.branch_id
    )

    if roi_pipeline_id is None:
        won_stage_ids: set = set()
        all_stages = []
    else:
        won_stages_result = await db.execute(
            select(PipelineStage.id).where(
                PipelineStage.pipeline_id == roi_pipeline_id,
                PipelineStage.is_won.is_(True),
                PipelineStage.is_active.is_(True),
            )
        )
        won_stage_ids = set(won_stages_result.scalars().all())

        all_stages_result = await db.execute(
            select(PipelineStage).where(
                PipelineStage.pipeline_id == roi_pipeline_id,
                PipelineStage.is_active.is_(True),
            ).order_by(PipelineStage.order_index)
        )
        all_stages = all_stages_result.scalars().all()

    converted = sum(1 for l in leads if l.pipeline_stage_id in won_stage_ids)
    conversion_rate = round(converted / leads_total * 100, 1) if leads_total else 0.0

    pipeline_by_stage: list[PipelineStageROI] = []
    for stage in all_stages:
        stage_leads = [l for l in leads if l.pipeline_stage_id == stage.id]
        pipeline_by_stage.append(PipelineStageROI(
            stage_name=stage.name,
            stage_key=stage.stage_key,
            count=len(stage_leads),
            avg_days_in_stage=None,  # would need activity events — skip for now
        ))

    # ── Tiempo ahorrado ───────────────────────────────────────────────────────
    bot_msg_result = await db.execute(
        select(func.count(Message.id)).where(
            Message.conversation_id.in_(
                select(Conversation.id).where(
                    Conversation.lead_id.in_(lead_ids) if lead_ids else Conversation.id.isnot(None),
                    Conversation.started_at >= since,
                )
            ),
            Message.role == MessageRole.ASSISTANT,
        )
    )
    bot_messages_sent = bot_msg_result.scalar_one() or 0
    estimated_minutes_saved = round(bot_messages_sent * _BOT_MIN_PER_MESSAGE, 1)
    estimated_hours_saved = round(estimated_minutes_saved / 60, 1)

    # ── Valor generado ────────────────────────────────────────────────────────
    estimated_revenue = round(converted * revenue_cfg, 2) if revenue_cfg is not None else None

    # ── Respuesta humana ──────────────────────────────────────────────────────
    # avg_response_time from daily_metrics (convert seconds → minutes)
    metrics_result = await db.execute(
        select(DailyMetric).where(
            DailyMetric.branch_id.in_(branch_ids) if branch_ids else DailyMetric.id.isnot(None),
            DailyMetric.metric_date >= since.date(),
            DailyMetric.avg_first_response_sec > 0,
        )
    )
    metric_rows = metrics_result.scalars().all()
    avg_response_time_minutes: float | None = None
    if metric_rows:
        avg_sec = sum(m.avg_first_response_sec for m in metric_rows) / len(metric_rows)
        avg_response_time_minutes = round(avg_sec / 60, 1)

    # Leads waiting response: handed off, not terminal, no outbound message in last 60 min
    cutoff_60m = now - timedelta(minutes=_RESPONSE_WAIT_MINUTES)
    waiting_leads_result = await db.execute(
        select(Lead.id).where(
            Lead.tenant_id == current_user.tenant_id,
            Lead.handoff_at.isnot(None),
            Lead.deleted_at.is_(None),
            Lead.status.notin_([LeadStatus.PERDIDO, LeadStatus.CALIFICADO]),
        )
    )
    handoff_lead_ids = list(waiting_leads_result.scalars().all())
    leads_waiting_response = 0
    if handoff_lead_ids:
        # Check which have no recent outbound message
        recent_outbound_result = await db.execute(
            select(Conversation.lead_id).where(
                Conversation.lead_id.in_(handoff_lead_ids),
            ).join(
                Message,
                (Message.conversation_id == Conversation.id) &
                (Message.role == MessageRole.ASSISTANT) &
                (Message.created_at >= cutoff_60m),
            ).distinct()
        )
        leads_with_recent = set(recent_outbound_result.scalars().all())
        leads_waiting_response = len(set(handoff_lead_ids) - leads_with_recent)

    # ── Sentimiento ───────────────────────────────────────────────────────────
    sentiment_breakdown: dict[str, int] = {s.value: 0 for s in LeadSentiment}
    for l in leads:
        sent = getattr(l.sentiment, "value", str(l.sentiment))
        sentiment_breakdown[sent] = sentiment_breakdown.get(sent, 0) + 1

    # ── Agentes IA ────────────────────────────────────────────────────────────
    suggestions_result = await db.execute(
        select(AgentSuggestion).where(
            AgentSuggestion.tenant_id == current_user.tenant_id,
            AgentSuggestion.created_at >= since,
        )
    )
    suggestions = suggestions_result.scalars().all()
    agent_suggestions_generated = len(suggestions)
    accepted_statuses = {"accepted", "confirmed", "executed"}
    agent_suggestions_accepted = sum(1 for s in suggestions if s.status in accepted_statuses)
    agent_acceptance_rate = round(
        agent_suggestions_accepted / agent_suggestions_generated * 100, 1
    ) if agent_suggestions_generated else 0.0

    return ROIOut(
        period_days=period,
        period_label=_PERIOD_LABELS.get(period, f"Últimos {period} días"),
        leads_total=leads_total,
        leads_by_source=leads_by_source,
        bot_qualified=bot_qualified,
        bot_qualification_rate=bot_qualification_rate,
        avg_qualification_score=avg_qualification_score,
        avg_messages_to_qualify=avg_messages_to_qualify,
        handoffs_executed=handoffs_executed,
        converted=converted,
        conversion_rate=conversion_rate,
        pipeline_by_stage=pipeline_by_stage,
        bot_messages_sent=bot_messages_sent,
        estimated_minutes_saved=estimated_minutes_saved,
        estimated_hours_saved=estimated_hours_saved,
        revenue_per_conversion=revenue_cfg,
        estimated_revenue=estimated_revenue,
        avg_response_time_minutes=avg_response_time_minutes,
        leads_waiting_response=leads_waiting_response,
        sentiment_breakdown=sentiment_breakdown,
        agent_suggestions_generated=agent_suggestions_generated,
        agent_suggestions_accepted=agent_suggestions_accepted,
        agent_acceptance_rate=agent_acceptance_rate,
        assumptions={
            "bot_minutes_per_message": f"{_BOT_MIN_PER_MESSAGE} min — promedio industria WhatsApp support",
            "qualification_threshold": f"qualification_score >= {_QUALIFY_SCORE_THRESHOLD}",
            "response_wait_threshold": f"{_RESPONSE_WAIT_MINUTES} min para considerar lead sin respuesta",
        },
    )
