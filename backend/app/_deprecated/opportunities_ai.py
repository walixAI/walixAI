"""AI-powered endpoints for the Opportunities Pipeline.

Routes (all under /opportunities prefix):
  POST /opportunities/ai/insights            — pipeline health + AI analysis (cached 10 min)
  POST /opportunities/ai/bulk-suggestions    — enqueue Celery bulk-suggestion task
  POST /opportunities/{opp_id}/ai/next-step  — generate + persist next-step suggestion
  POST /opportunities/{opp_id}/ai/probability — predict close probability (read-only)

Route ordering matters: the two /ai/* collection routes must be defined BEFORE
the /{opp_id}/* parameterised routes so FastAPI doesn't attempt to parse "ai"
as a UUID.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import redis_client
from app.models.opportunity import Opportunity
from app.models.opportunity_activity import OpportunityActivity
from app.models.pipeline import PipelineStage
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["opportunities-ai"])

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)

_URGENCY_SCORE = {"high": 85, "medium": 55, "low": 25}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    return json.loads(match.group())


def _days_since(dt: datetime | None) -> int:
    if dt is None:
        return 0
    now = datetime.now(timezone.utc)
    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return max(0, (now - aware).days)


def _days_until(d: date | None) -> int | str:
    if d is None:
        return "—"
    delta = (d - datetime.now(timezone.utc).date()).days
    return delta


async def _get_opportunity(db: AsyncSession, opp_id: uuid.UUID, user: User) -> Opportunity:
    """Load and authorise an opportunity (inlined to avoid circular import)."""
    opp = await db.get(Opportunity, opp_id)
    if opp is None or opp.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Oportunidad no encontrada")
    if opp.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Oportunidad no encontrada")
    if user.role not in _MULTI_BRANCH_ROLES and opp.branch_id != user.branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Oportunidad no encontrada")
    return opp


def _validate_branch_access(user: User, branch_id: uuid.UUID) -> None:
    """Raise 403 if the user cannot access the requested branch."""
    if user.role in _MULTI_BRANCH_ROLES:
        return
    if user.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="No tienes acceso a esta sucursal")


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class NextStepResponse(BaseModel):
    text: str | None = None
    reasoning: str | None = None
    urgency: str | None = None


class ProbabilityResponse(BaseModel):
    suggested: int
    signals: list[str]
    current: int | None


class InsightsRequest(BaseModel):
    branch_id: uuid.UUID


class BulkSuggestionsRequest(BaseModel):
    branch_id: uuid.UUID


class RiskItem(BaseModel):
    title: str
    severity: str
    description: str


class RecommendationItem(BaseModel):
    title: str
    impact: str
    action: str


class InsightsResponse(BaseModel):
    health_score: int
    summary: str
    risks: list[RiskItem]
    recommendations: list[RecommendationItem]


class BulkSuggestionsResponse(BaseModel):
    status: str
    branch_id: str


# ── ROUTE 1: POST /ai/insights (BEFORE /{opp_id} routes) ─────────────────────

@router.post("/ai/insights", response_model=InsightsResponse)
async def pipeline_insights(
    body: InsightsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InsightsResponse:
    """Return AI-generated pipeline health insights with Redis caching (TTL=600s)."""
    branch_id = body.branch_id
    _validate_branch_access(current_user, branch_id)

    # ── Cache check ────────────────────────────────────────────────────────────
    cache_key = f"opp:insights:{branch_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            return InsightsResponse(**data)
        except Exception:
            logger.warning("[insights] cache parse failed, regenerating")

    # ── Rule-based signals ─────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    stale_cutoff = now.replace(tzinfo=timezone.utc)
    from datetime import timedelta
    stale_cutoff = now - timedelta(days=14)

    open_agg = await db.execute(
        select(
            func.count(Opportunity.id),
            func.coalesce(func.sum(Opportunity.amount), 0),
        ).where(
            Opportunity.branch_id == branch_id,
            Opportunity.tenant_id == current_user.tenant_id,
            Opportunity.status == "open",
            Opportunity.deleted_at.is_(None),
        )
    )
    open_count_raw, total_amount_raw = open_agg.one()
    open_count = int(open_count_raw)
    total_amount = float(total_amount_raw)

    stale_agg = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.branch_id == branch_id,
            Opportunity.tenant_id == current_user.tenant_id,
            Opportunity.status == "open",
            Opportunity.deleted_at.is_(None),
            Opportunity.stage_entered_at < stale_cutoff,
        )
    )
    stale_count = int(stale_agg.scalar_one())

    stale_pct = stale_count / max(open_count, 1) * 100

    # Bottleneck: stages with > 10 open opps
    stage_counts = await db.execute(
        select(
            Opportunity.stage_id,
            func.count(Opportunity.id).label("cnt"),
        ).where(
            Opportunity.branch_id == branch_id,
            Opportunity.tenant_id == current_user.tenant_id,
            Opportunity.status == "open",
            Opportunity.deleted_at.is_(None),
            Opportunity.stage_id.isnot(None),
        ).group_by(Opportunity.stage_id)
    )
    bottleneck_stage_ids = [row.stage_id for row in stage_counts.fetchall() if row.cnt > 10]

    bottleneck_names: list[str] = []
    for sid in bottleneck_stage_ids:
        stage = await db.get(PipelineStage, sid)
        if stage:
            bottleneck_names.append(stage.name)

    health_score = int(max(0, min(100, round(100 - stale_pct * 0.4 - len(bottleneck_stage_ids) * 5))))

    # ── Fallback defaults ──────────────────────────────────────────────────────
    summary = "Análisis no disponible."
    risks: list[RiskItem] = []
    recommendations: list[RecommendationItem] = []

    # ── Haiku call ─────────────────────────────────────────────────────────────
    try:
        bottleneck_list = ", ".join(bottleneck_names) if bottleneck_names else "Ninguna"
        branch_id_short = str(branch_id)[:8]
        prompt = (
            f"Eres un analista de ventas senior para un CRM. Analiza estas señales del pipeline y genera insights accionables.\n\n"
            f"SEÑALES DEL PIPELINE (sucursal {branch_id_short}):\n"
            f"- Oportunidades abiertas: {open_count} (monto total: {total_amount:.0f} MXN)\n"
            f"- Oportunidades estancadas (>14 días en etapa): {stale_count} ({stale_pct:.0f}%)\n"
            f"- Health score calculado: {health_score}/100\n"
            f"- Etapas con cuello de botella (>10 opps): {bottleneck_list}\n\n"
            f"Devuelve ÚNICAMENTE un JSON con esta estructura:\n"
            f'{{\n'
            f'  "summary": "<resumen ejecutivo 1-2 oraciones, español México, menciona el health score>",\n'
            f'  "risks": [\n'
            f'    {{"title": "<≤60 chars>", "severity": "<high|medium|low>", "description": "<≤120 chars>"}},\n'
            f'    ...\n'
            f'  ],\n'
            f'  "recommendations": [\n'
            f'    {{"title": "<≤60 chars>", "impact": "<high|medium|low>", "action": "<≤120 chars>"}},\n'
            f'    ...\n'
            f'  ]\n'
            f'}}\n'
            f"Máximo 3 riesgos y 3 recomendaciones. Sé específico y accionable."
        )
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extract_json(response.content[0].text)
        summary = data.get("summary", summary)
        risks = [RiskItem(**r) for r in data.get("risks", [])]
        recommendations = [RecommendationItem(**r) for r in data.get("recommendations", [])]
    except Exception:
        logger.exception("[insights] Haiku call failed, using rule-based fallback")

    result = InsightsResponse(
        health_score=health_score,
        summary=summary,
        risks=risks,
        recommendations=recommendations,
    )

    # ── Cache store ────────────────────────────────────────────────────────────
    try:
        await redis_client.setex(cache_key, 600, json.dumps(result.model_dump(), default=str))
    except Exception:
        logger.warning("[insights] Redis setex failed")

    return result


# ── ROUTE 2: POST /ai/bulk-suggestions (BEFORE /{opp_id} routes) ──────────────

@router.post("/ai/bulk-suggestions", response_model=BulkSuggestionsResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def bulk_suggestions(
    body: BulkSuggestionsRequest,
    current_user: User = Depends(get_current_user),
) -> BulkSuggestionsResponse:
    """Enqueue a Celery task to generate AI suggestions for all open opps in a branch."""
    _validate_branch_access(current_user, body.branch_id)

    from app.tasks.opp_ai_tasks import generate_bulk_suggestions
    generate_bulk_suggestions.delay(str(body.branch_id))

    return BulkSuggestionsResponse(status="queued", branch_id=str(body.branch_id))


# ── ROUTE 3: POST /{opp_id}/ai/next-step ──────────────────────────────────────

@router.post("/{opp_id}/ai/next-step", response_model=NextStepResponse)
async def next_step(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NextStepResponse:
    """Generate and persist an AI next-step suggestion for an opportunity."""
    try:
        opp = await _get_opportunity(db, opp_id, current_user)

        stage: PipelineStage | None = None
        if opp.stage_id:
            stage = await db.get(PipelineStage, opp.stage_id)

        stage_name = stage.name if stage else "Sin etapa"
        days_in_stage = _days_since(opp.stage_entered_at)
        last_activity_human = (
            f"hace {_days_since(opp.last_activity_at)} días"
            if opp.last_activity_at
            else "sin registro"
        )

        prompt = (
            f"Eres un asistente de CRM de ventas. Analiza esta oportunidad y sugiere el siguiente paso concreto.\n\n"
            f"Oportunidad: {opp.title}\n"
            f"Monto: {opp.amount} {opp.currency}\n"
            f"Etapa: {stage_name}\n"
            f"Días en etapa: {days_in_stage}\n"
            f"Última actividad: {last_activity_human}\n"
            f"Fecha cierre objetivo: {opp.close_date or '—'}\n"
            f"Notas: {opp.notes or '—'}\n\n"
            f'Devuelve ÚNICAMENTE un JSON con esta estructura:\n'
            f'{{"text": "<acción concreta en ≤120 chars, español México>", "reasoning": "<razonamiento breve ≤200 chars>", "urgency": "<high|medium|low>"}}'
        )

        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extract_json(response.content[0].text)

        text = data.get("text") or ""
        reasoning = data.get("reasoning") or ""
        urgency = data.get("urgency", "medium")

        # Persist on opp
        opp.ai_suggestion = text[:500] if text else None
        opp.ai_suggestion_urgency = urgency
        opp.urgency_score = _URGENCY_SCORE.get(urgency, 55)

        # Add activity
        db.add(OpportunityActivity(
            opportunity_id=opp.id,
            tenant_id=opp.tenant_id,
            type="ai_suggestion",
            description=(text[:200] if text else "Sugerencia IA generada"),
        ))

        await db.commit()

        return NextStepResponse(
            text=text or None,
            reasoning=reasoning or None,
            urgency=urgency or None,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("[next_step] failed for opp=%s", opp_id)
        return NextStepResponse(text=None, reasoning=None, urgency=None)


# ── ROUTE 4: POST /{opp_id}/ai/probability ────────────────────────────────────

@router.post("/{opp_id}/ai/probability", response_model=ProbabilityResponse)
async def predict_probability(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProbabilityResponse:
    """Return an AI-suggested close probability. Never auto-applies to the opp."""
    try:
        opp = await _get_opportunity(db, opp_id, current_user)

        stage: PipelineStage | None = None
        if opp.stage_id:
            stage = await db.get(PipelineStage, opp.stage_id)

        stage_name = stage.name if stage else "Sin etapa"
        stage_prob_default = stage.probability_default if stage else None
        days_in_stage = _days_since(opp.stage_entered_at)
        days_to_close = _days_until(opp.close_date)
        last_activity_human = (
            f"hace {_days_since(opp.last_activity_at)} días"
            if opp.last_activity_at
            else "sin registro"
        )

        prompt = (
            f"Eres un motor de predicción de cierre para un CRM de ventas B2C en México.\n\n"
            f"Oportunidad: {opp.title}\n"
            f"Monto: {opp.amount} {opp.currency}\n"
            f"Etapa actual: {stage_name} (probabilidad por defecto de la etapa: {stage_prob_default}%)\n"
            f"Días en etapa: {days_in_stage}\n"
            f"Días hasta cierre: {days_to_close}\n"
            f"Última actividad: {last_activity_human}\n"
            f"Estado: {opp.status}\n"
            f"Notas: {opp.notes or '—'}\n\n"
            f"Considera: valor, tiempo en etapa, urgencia, actividad reciente, fecha de cierre.\n"
            f'Devuelve ÚNICAMENTE un JSON:\n'
            f'{{"suggested": <integer 0-100>, "signals": ["<señal 1, ≤60 chars>", "<señal 2>", "<señal 3>"]}}'
        )

        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extract_json(response.content[0].text)
        suggested = int(data.get("suggested", opp.probability or 50))
        suggested = max(0, min(100, suggested))
        signals = [str(s) for s in data.get("signals", [])]

        return ProbabilityResponse(
            suggested=suggested,
            signals=signals,
            current=opp.probability,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("[probability] failed for opp=%s", opp_id)
        opp_prob = None
        try:
            # Try to get current probability for fallback
            opp_fallback = await db.get(Opportunity, opp_id)
            if opp_fallback:
                opp_prob = opp_fallback.probability
        except Exception:
            pass
        return ProbabilityResponse(
            suggested=opp_prob or 50,
            signals=[],
            current=opp_prob,
        )
