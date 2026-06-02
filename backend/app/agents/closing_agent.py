"""Closing agent: generates closing proposals for high-score leads (>=70)."""
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import CLOSING_AGENT_PROMPT
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.activity import ActivityType, LeadActivity
from app.models.agent import AgentSuggestion
from app.models.conversation import Conversation, Message
from app.models.lead import Lead
from app.models.tenant import Branch
from app.models.user import User, UserRole
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)
CLAUDE_MODEL = "claude-sonnet-4-6"

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_whatsapp = WhatsAppService()


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in response: {text[:200]}")
    return json.loads(match.group())


async def run_closing_agent(lead_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    """Evaluate a high-score lead and suggest a closing proposal if appropriate."""
    try:
        async with AsyncSessionLocal() as db:
            return await _run_closing(lead_id, tenant_id, db)
    except Exception:
        logger.exception("closing_agent: unhandled error lead=%s", lead_id)
        return False


async def _run_closing(
    lead_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> bool:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        logger.warning("closing_agent: lead %s not found", lead_id)
        return False

    # Guard: no QUOTE activity in the last 5 days
    quote_cutoff = datetime.now(timezone.utc) - timedelta(days=5)
    recent_quote = await db.execute(
        select(LeadActivity).where(
            LeadActivity.lead_id == lead_id,
            LeadActivity.activity_type == ActivityType.QUOTE,
            LeadActivity.created_at >= quote_cutoff,
        ).limit(1)
    )
    if recent_quote.scalar_one_or_none():
        logger.info("closing_agent: lead %s already has a recent quote — skip", lead_id)
        return False

    # Get last 20 messages across all conversations for this lead
    msgs_result = await db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.lead_id == lead_id)
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    messages = list(reversed(msgs_result.scalars().all()))

    history_text = "\n".join(
        f"[{getattr(m.role, 'value', m.role)}]: {m.content}" for m in messages
    ) or "(Sin interacciones)"

    qual_pct = (
        f"{lead.qualification_score * 100:.0f}%"
        if lead.qualification_score is not None
        else "Sin calificar"
    )

    user_msg = (
        f"Lead: {lead.name or lead.wa_phone}\n"
        f"Score de predicción: {lead.current_score or 'N/A'}/100\n"
        f"Score de calificación: {qual_pct}\n"
        f"Status: {getattr(lead.status, 'value', str(lead.status))}\n\n"
        f"HISTORIAL ({len(messages)} mensajes):\n{history_text}\n\n"
        f"¿Es el momento ideal para cerrar? Genera la propuesta si corresponde."
    )

    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        system=CLOSING_AGENT_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    parsed = _extract_json(response.content[0].text)
    if not parsed.get("should_suggest"):
        return False

    proposal_text = str(parsed.get("proposal_text", ""))[:200]
    suggestion_text = str(parsed.get("suggestion_text", ""))[:120]
    trigger_description = str(parsed.get("trigger_description", ""))[:80]

    # Find target user (assigned asesor → any asesor with wa_phone)
    target_user: User | None = None
    if lead.assigned_to:
        target_user = await db.get(User, lead.assigned_to)
    if not target_user:
        u_result = await db.execute(
            select(User).where(
                User.branch_id == lead.branch_id,
                User.role == UserRole.ASESOR.value,
                User.is_active.is_(True),
            ).limit(1)
        )
        target_user = u_result.scalar_one_or_none()

    branch = await db.get(Branch, lead.branch_id)

    suggestion = AgentSuggestion(
        tenant_id=tenant_id,
        branch_id=lead.branch_id,
        agent_type="closing",
        trigger_description=trigger_description,
        suggestion_text=suggestion_text,
        action_payload={"lead_id": str(lead_id), "proposal_text": proposal_text},
        target_role="asesor",
        target_user_id=target_user.id if target_user else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(suggestion)
    await db.flush()

    # Notify asesor via WhatsApp
    if (
        target_user
        and target_user.wa_phone
        and branch
        and branch.wa_phone_number_id
        and branch.wa_token
    ):
        notify_msg = (
            f"🎯 Walix · Propuesta de cierre\n"
            f"{lead.name or lead.wa_phone} tiene score {lead.current_score}/100.\n"
            f"Propuesta: {proposal_text}\n"
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
        "closing_agent: suggestion created lead=%s score=%s", lead_id, lead.current_score
    )
    return True
