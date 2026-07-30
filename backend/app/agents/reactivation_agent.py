"""Reactivation agent: suggests re-engagement messages for leads dormant 30+ days."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import cast, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import AgentSuggestion
from app.models.conversation import Conversation, Message
from app.models.lead import Lead, LeadStatus
from app.models.user import User

logger = logging.getLogger(__name__)
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = (
    "Eres el agente de reactivación de Walix. Genera un mensaje corto de reactivación "
    "(máx 2 oraciones) personalizado basado en el historial. Responde SOLO en JSON: "
    '{"should_suggest": bool, "message": str, "reason": str}'
)

_TERMINAL_STATUSES = [LeadStatus.CALIFICADO, LeadStatus.PERDIDO]


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in response: {text[:200]}")
    return json.loads(match.group())


async def run_reactivation_agent(
    tenant_id: uuid.UUID, db: AsyncSession
) -> int:
    """Scan dormant leads and create reactivation suggestions. Returns count created."""
    try:
        return await _run_reactivation(tenant_id, db)
    except Exception:
        logger.exception("reactivation_agent: unhandled error tenant=%s", tenant_id)
        return 0


async def _run_reactivation(tenant_id: uuid.UUID, db: AsyncSession) -> int:
    dormant_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Correlated subquery: at least 1 message for this lead
    msg_count_subq = (
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.lead_id == Lead.id)
        .correlate(Lead)
        .scalar_subquery()
    )

    # Correlated EXISTS: a recent reactivation suggestion already exists for this lead
    has_recent_suggestion = (
        select(AgentSuggestion.id)
        .where(
            AgentSuggestion.agent_type == "reactivation",
            AgentSuggestion.action_payload["lead_id"].astext == cast(Lead.id, String),
            AgentSuggestion.created_at > dedup_cutoff,
        )
        .correlate(Lead)
        .exists()
    )

    candidates = (
        await db.execute(
            select(Lead)
            .where(
                Lead.tenant_id == tenant_id,
                Lead.deleted_at.is_(None),
                Lead.status.notin_(_TERMINAL_STATUSES),
                Lead.updated_at < dormant_cutoff,
                msg_count_subq >= 1,
                ~has_recent_suggestion,
            )
            .limit(20)
        )
    ).scalars().all()

    if not candidates:
        return 0

    created = 0
    for lead in candidates:
        try:
            if await _process_lead(lead, db):
                created += 1
        except Exception:
            logger.exception("reactivation_agent: failed for lead=%s", lead.id)

    logger.info(
        "reactivation_agent: tenant=%s suggestions_created=%d", tenant_id, created
    )
    return created


async def _process_lead(lead: Lead, db: AsyncSession) -> bool:
    # Last message for context
    last_msg = (
        await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.lead_id == lead.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalars().first()

    if not last_msg:
        return False

    # Days since last activity (using updated_at as proxy)
    ref_ts = lead.updated_at
    if ref_ts and ref_ts.tzinfo is None:
        ref_ts = ref_ts.replace(tzinfo=timezone.utc)
    days_inactive = int(
        (datetime.now(timezone.utc) - ref_ts).total_seconds() / 86_400
    ) if ref_ts else 30

    user_msg = (
        f"Lead: {lead.name or lead.wa_phone}. "
        f"Último mensaje hace {days_inactive} días: '{last_msg.content[:200]}'. "
        f"Score: {lead.current_score if lead.current_score is not None else 'sin score'}."
    )

    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    parsed = _extract_json(response.content[0].text)

    if not parsed.get("should_suggest"):
        return False

    message = str(parsed.get("message", "")).strip()
    reason = str(parsed.get("reason", "")).strip()

    if not message:
        return False

    target_user: User | None = None
    if lead.assigned_to:
        target_user = await db.get(User, lead.assigned_to)

    db.add(
        AgentSuggestion(
            tenant_id=lead.tenant_id,
            branch_id=lead.branch_id,
            agent_type="reactivation",
            trigger_description=reason[:80] or f"Lead inactivo {days_inactive} días",
            suggestion_text=(
                f"{lead.name or lead.wa_phone} lleva {days_inactive} días sin actividad. "
                f'¿Envío este mensaje de reactivación?\n\n"{message}"'
            ),
            action_payload={"lead_id": str(lead.id), "message": message},
            entity_type="contact",
            entity_id=lead.id,
            target_role="asesor",
            target_user_id=target_user.id if target_user else None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
    )
    await db.flush()

    logger.info(
        "reactivation_agent: suggestion created lead=%s days_inactive=%d",
        lead.id, days_inactive,
    )
    return True
