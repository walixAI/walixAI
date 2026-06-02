"""Pipeline agent: detects bottlenecks and suggests corrective actions to managers."""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import PIPELINE_AGENT_PROMPT
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.activity import ActivityType, LeadActivity
from app.models.agent import AgentSuggestion
from app.models.lead import Lead, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch
from app.models.user import User, UserRole
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_whatsapp = WhatsAppService()


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in response: {text[:200]}")
    return json.loads(match.group())


async def run_pipeline_agent(branch_id: uuid.UUID) -> bool:
    """Analyze pipeline health and create a suggestion for the manager if needed."""
    try:
        async with AsyncSessionLocal() as db:
            return await _run_pipeline(branch_id, db)
    except Exception:
        logger.exception("pipeline_agent: unhandled error branch=%s", branch_id)
        return False


async def _run_pipeline(branch_id: uuid.UUID, db: AsyncSession) -> bool:
    branch = await db.get(Branch, branch_id)
    if not branch:
        return False

    stall_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    prev_week_start = week_ago - timedelta(days=7)

    # Active pipeline stages for the branch
    stages_result = await db.execute(
        select(PipelineStage).where(
            PipelineStage.branch_id == branch_id,
            PipelineStage.is_active.is_(True),
        ).order_by(PipelineStage.order_index)
    )
    stages = stages_result.scalars().all()
    if not stages:
        return False

    stage_by_id = {s.id: s for s in stages}
    terminal_statuses = [LeadStatus.PERDIDO, LeadStatus.CALIFICADO]

    # Stalled leads per stage (no STAGE_CHANGE activity in last 7 days)
    bottleneck_stages: list[dict] = []
    for stage in stages:
        total_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.pipeline_stage_id == stage.id,
                Lead.branch_id == branch_id,
                Lead.status.notin_(terminal_statuses),
            )
        )
        total = total_r.scalar_one() or 0
        if total == 0:
            continue

        # Leads in this stage that moved recently
        recent_r = await db.execute(
            select(LeadActivity.lead_id)
            .join(Lead, LeadActivity.lead_id == Lead.id)
            .where(
                Lead.pipeline_stage_id == stage.id,
                LeadActivity.activity_type == ActivityType.STAGE_CHANGE,
                LeadActivity.created_at >= stall_cutoff,
            )
        )
        moved_ids = {row[0] for row in recent_r.fetchall()}
        stalled = total - len(moved_ids)

        if total > 0 and stalled / total > 0.40:
            bottleneck_stages.append({
                "stage_id": str(stage.id),
                "stage_name": stage.name,
                "total": total,
                "stalled": stalled,
                "stalled_pct": int(stalled / total * 100),
            })

    # Asesores with low conversion (<15%) — minimum 5 leads for statistical relevance
    asesores_result = await db.execute(
        select(User).where(
            User.branch_id == branch_id,
            User.role == UserRole.ASESOR.value,
            User.is_active.is_(True),
        )
    )
    asesores = asesores_result.scalars().all()

    low_conversion: list[dict] = []
    for asesor in asesores:
        total_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.assigned_to == asesor.id,
                Lead.branch_id == branch_id,
            )
        )
        total = total_r.scalar_one() or 0
        if total < 5:
            continue

        won_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.assigned_to == asesor.id,
                Lead.branch_id == branch_id,
                Lead.status == LeadStatus.CALIFICADO,
            )
        )
        won = won_r.scalar_one() or 0
        if won / total < 0.15:
            low_conversion.append({
                "asesor_id": str(asesor.id),
                "asesor_name": asesor.name,
                "total": total,
                "won": won,
                "conversion_pct": int(won / total * 100),
            })

    # Weekly pipeline volume comparison
    this_week_r = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.branch_id == branch_id,
            Lead.created_at >= week_ago,
        )
    )
    leads_this_week = this_week_r.scalar_one() or 0

    prev_week_r = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.branch_id == branch_id,
            Lead.created_at >= prev_week_start,
            Lead.created_at < week_ago,
        )
    )
    leads_prev_week = prev_week_r.scalar_one() or 0

    if not bottleneck_stages and not low_conversion:
        logger.info("pipeline_agent: no issues detected for branch=%s", branch_id)
        return False

    context_msg = (
        f"ANÁLISIS DE PIPELINE (branch={branch.name}):\n\n"
        f"Etapas con >40% leads estancados >7 días:\n"
        f"{json.dumps(bottleneck_stages, ensure_ascii=False) or 'Ninguna'}\n\n"
        f"Asesores con conversión <15%:\n"
        f"{json.dumps(low_conversion, ensure_ascii=False) or 'Ninguno'}\n\n"
        f"Volumen: {leads_this_week} leads esta semana vs {leads_prev_week} la semana anterior.\n\n"
        f"Detecta el problema más crítico y propón UNA acción concreta."
    )

    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=350,
        system=PIPELINE_AGENT_PROMPT,
        messages=[{"role": "user", "content": context_msg}],
    )
    parsed = _extract_json(response.content[0].text)
    if not parsed.get("should_suggest"):
        return False

    # Build action_payload with all computed context
    action_payload: dict[str, Any] = parsed.get("action_detail") or {}
    action_payload["action"] = parsed.get("action", "create_task")
    action_payload["bottleneck_stages"] = bottleneck_stages
    action_payload["low_conversion_asesores"] = low_conversion

    # Find gerente to notify
    gerente_result = await db.execute(
        select(User).where(
            User.branch_id == branch_id,
            User.role == UserRole.GERENTE.value,
            User.is_active.is_(True),
        ).limit(1)
    )
    gerente = gerente_result.scalar_one_or_none()

    suggestion = AgentSuggestion(
        tenant_id=branch.tenant_id,
        branch_id=branch.id,
        agent_type="pipeline",
        trigger_description=str(parsed.get("trigger_description", ""))[:80],
        suggestion_text=str(parsed.get("suggestion_text", ""))[:150],
        action_payload=action_payload,
        target_role="gerente",
        target_user_id=gerente.id if gerente else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(suggestion)
    await db.flush()

    # Notify gerente via WhatsApp if credentials are available
    if gerente and gerente.wa_phone and branch.wa_phone_number_id and branch.wa_token:
        notify_msg = (
            f"📊 Walix · Análisis de Pipeline\n"
            f"{suggestion.suggestion_text}\n"
            f"Revisa el dashboard para aprobar o descartar."
        )
        await _whatsapp.send_text_message(
            to_phone=gerente.wa_phone,
            message=notify_msg,
            phone_number_id=branch.wa_phone_number_id,
            token=branch.wa_token,
        )

    await db.commit()
    logger.info(
        "pipeline_agent: suggestion created branch=%s action=%s",
        branch_id, action_payload.get("action"),
    )
    return True
