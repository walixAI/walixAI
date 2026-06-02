"""Config agent: detects inactive pipeline stages and suggests cleanup to owners."""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import CONFIG_AGENT_PROMPT
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.activity import ActivityType, LeadActivity
from app.models.agent import AgentSuggestion
from app.models.lead import Lead
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


async def run_config_agent(branch_id: uuid.UUID) -> bool:
    """Detect inactive stages and suggest pipeline cleanup to the owner."""
    try:
        async with AsyncSessionLocal() as db:
            return await _run_config(branch_id, db)
    except Exception:
        logger.exception("config_agent: unhandled error branch=%s", branch_id)
        return False


async def _run_config(branch_id: uuid.UUID, db: AsyncSession) -> bool:
    branch = await db.get(Branch, branch_id)
    if not branch:
        return False

    inactive_cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    stages_result = await db.execute(
        select(PipelineStage).where(
            PipelineStage.branch_id == branch_id,
            PipelineStage.is_active.is_(True),
            PipelineStage.is_won.is_(False),
            PipelineStage.is_lost.is_(False),
        ).order_by(PipelineStage.order_index)
    )
    stages = stages_result.scalars().all()
    if not stages:
        return False

    # Find stages with no leads or no STAGE_CHANGE activity in 30+ days
    inactive_stages: list[dict] = []
    for stage in stages:
        # Count leads ever assigned to this stage
        total_leads_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.pipeline_stage_id == stage.id,
                Lead.branch_id == branch_id,
            )
        )
        total_leads = total_leads_r.scalar_one() or 0

        # Count STAGE_CHANGE activities into this stage in the last 30 days
        recent_r = await db.execute(
            select(func.count(LeadActivity.id)).where(
                LeadActivity.activity_type == ActivityType.STAGE_CHANGE,
                LeadActivity.created_at >= inactive_cutoff,
            ).join(Lead, LeadActivity.lead_id == Lead.id)
            .where(Lead.pipeline_stage_id == stage.id)
        )
        recent_activity = recent_r.scalar_one() or 0

        if recent_activity == 0:
            inactive_stages.append({
                "stage_id": str(stage.id),
                "stage_name": stage.name,
                "current_leads": total_leads,
                "recent_activity": 0,
            })

    if not inactive_stages:
        logger.info("config_agent: no inactive stages for branch=%s", branch_id)
        return False

    total_stages = len(stages)
    context_msg = (
        f"ANÁLISIS DE CONFIGURACIÓN (branch={branch.name}):\n\n"
        f"Etapas activas: {total_stages}\n"
        f"Etapas sin actividad en 30+ días:\n"
        f"{json.dumps(inactive_stages, ensure_ascii=False)}\n\n"
        f"¿Alguna etapa debería desactivarse para limpiar el pipeline?"
    )

    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        system=CONFIG_AGENT_PROMPT,
        messages=[{"role": "user", "content": context_msg}],
    )
    parsed = _extract_json(response.content[0].text)
    if not parsed.get("should_suggest"):
        return False

    action_payload: dict[str, Any] = parsed.get("action_detail") or {}
    action_payload["action"] = parsed.get("action", "no_action")
    action_payload["inactive_stages"] = inactive_stages

    # Find owner to notify
    owner_result = await db.execute(
        select(User).where(
            User.branch_id == branch_id,
            User.role == UserRole.OWNER.value,
            User.is_active.is_(True),
        ).limit(1)
    )
    owner = owner_result.scalar_one_or_none()

    suggestion = AgentSuggestion(
        tenant_id=branch.tenant_id,
        branch_id=branch.id,
        agent_type="config",
        trigger_description=str(parsed.get("trigger_description", ""))[:80],
        suggestion_text=str(parsed.get("suggestion_text", ""))[:150],
        action_payload=action_payload,
        target_role="owner",
        target_user_id=owner.id if owner else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(suggestion)
    await db.flush()

    # Notify owner via WhatsApp
    if owner and owner.wa_phone and branch.wa_phone_number_id and branch.wa_token:
        notify_msg = (
            f"⚙️ Walix · Sugerencia de configuración\n"
            f"{suggestion.suggestion_text}\n"
            f"Revisa el dashboard para aprobar o descartar."
        )
        await _whatsapp.send_text_message(
            to_phone=owner.wa_phone,
            message=notify_msg,
            phone_number_id=branch.wa_phone_number_id,
            token=branch.wa_token,
        )

    await db.commit()
    logger.info(
        "config_agent: suggestion created branch=%s action=%s inactive_stages=%d",
        branch_id, action_payload.get("action"), len(inactive_stages),
    )
    return True
