"""Follow-up agent: suggests re-engagement messages for leads inactive >24h."""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import FOLLOW_UP_AGENT_PROMPT
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.agent import AgentSuggestion
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
)
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch
from app.models.user import User

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


async def run_follow_up_agent(branch_id: uuid.UUID) -> int:
    """Scan branch for stale leads and create follow-up suggestions. Returns count created."""
    try:
        async with AsyncSessionLocal() as db:
            return await _run_follow_up(branch_id, db)
    except Exception:
        logger.exception("follow_up_agent: unhandled error branch=%s", branch_id)
        return 0


async def _run_follow_up(branch_id: uuid.UUID, db: AsyncSession) -> int:
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)

    branch = await db.get(Branch, branch_id)
    if not branch or not branch.wa_phone_number_id or not branch.wa_token:
        logger.info("follow_up_agent: branch %s missing WA credentials — skip", branch_id)
        return 0

    # Correlated subquery: latest message timestamp for each conversation
    latest_msg_at = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )

    conv_result = await db.execute(
        select(Conversation)
        .join(Lead, Conversation.lead_id == Lead.id)
        .where(
            Conversation.branch_id == branch_id,
            Conversation.current_handler == ConversationHandler.BOT,
            Conversation.status != ConversationStatus.CLOSED,
            Lead.status.notin_([LeadStatus.PERDIDO, LeadStatus.CALIFICADO]),
            latest_msg_at.isnot(None),
            latest_msg_at < threshold,
        )
        .limit(20)
    )
    conversations = conv_result.scalars().all()
    if not conversations:
        return 0

    created = 0
    for conv in conversations:
        lead = await db.get(Lead, conv.lead_id)
        if lead is None:
            continue
        try:
            if await _process_lead(lead, conv, branch, dedup_cutoff, db):
                created += 1
        except Exception:
            logger.exception("follow_up_agent: failed for lead=%s", lead.id)

    logger.info("follow_up_agent: branch=%s suggestions_created=%d", branch_id, created)
    return created


async def _process_lead(
    lead: Lead,
    conv: Conversation,
    branch: Branch,
    dedup_cutoff: datetime,
    db: AsyncSession,
) -> bool:
    # Skip if a follow_up suggestion for this lead already exists in the last 6h
    dup = await db.execute(
        select(AgentSuggestion).where(
            AgentSuggestion.agent_type == "follow_up",
            AgentSuggestion.status == "suggested",
            AgentSuggestion.created_at >= dedup_cutoff,
            AgentSuggestion.action_payload["lead_id"].astext == str(lead.id),
        ).limit(1)
    )
    if dup.scalar_one_or_none():
        return False

    # Last 8 messages for context
    msgs_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc())
        .limit(8)
    )
    messages = list(reversed(msgs_result.scalars().all()))

    last_ts = messages[-1].created_at if messages else conv.started_at
    if last_ts and last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)
    hours_inactive = int(
        (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
    ) if last_ts else 25

    history_text = "\n".join(
        f"[{getattr(m.role, 'value', m.role)}]: {m.content}" for m in messages
    ) or "(Sin mensajes)"

    user_msg = (
        f"Lead: {lead.name or lead.wa_phone}\n"
        f"Horas sin respuesta: {hours_inactive}\n\n"
        f"Conversación:\n{history_text}\n\n"
        f"¿Se debe sugerir un mensaje de follow-up?"
    )

    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        system=FOLLOW_UP_AGENT_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    parsed = _extract_json(response.content[0].text)
    if not parsed.get("should_suggest"):
        return False

    suggestion_text = str(parsed.get("suggestion_text", ""))[:120]
    trigger_description = str(parsed.get("trigger_description", ""))[:80]
    message = str(parsed.get("message", ""))

    # Find target user (assigned asesor, or any asesor with wa_phone in the branch)
    target_user: User | None = None
    if lead.assigned_to:
        target_user = await db.get(User, lead.assigned_to)
    if not target_user or not target_user.wa_phone:
        u_result = await db.execute(
            select(User).where(
                User.branch_id == lead.branch_id,
                User.is_active.is_(True),
                User.wa_phone.isnot(None),
            ).limit(1)
        )
        target_user = u_result.scalar_one_or_none()

    suggestion = AgentSuggestion(
        tenant_id=lead.tenant_id,
        agent_type="follow_up",
        trigger_description=trigger_description,
        suggestion_text=suggestion_text,
        action_payload={"lead_id": str(lead.id), "message": message},
        target_role="asesor",
        target_user_id=target_user.id if target_user else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(suggestion)
    await db.flush()

    # Notify asesor via WhatsApp
    if target_user and target_user.wa_phone:
        notify_msg = (
            f"💬 Walix · Follow-up sugerido\n"
            f"{lead.name or lead.wa_phone} lleva {hours_inactive}h sin respuesta.\n"
            f"Mensaje: {message}\n"
            f"Responde 'sí' para enviar o 'no' para descartar."
        )
        await _whatsapp.send_text_message(
            to_phone=target_user.wa_phone,
            message=notify_msg,
            phone_number_id=branch.wa_phone_number_id,
            token=branch.wa_token,
        )

    await db.commit()
    logger.info(
        "follow_up_agent: suggestion created lead=%s hours_inactive=%d", lead.id, hours_inactive
    )
    return True
