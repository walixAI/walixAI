"""Automatic lead qualifier for Walix.

Called as a fire-and-forget background task after every bot turn.
Asks Claude Haiku to extract structured qualification data from the
conversation and updates the lead record accordingly.

Design note: qualify_lead() creates its own DB session so it is safe to
run as an asyncio background task after the caller's session has closed.
"""
import json
import logging
import re
import uuid

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
)
from app.models.lead import Lead, LeadSentiment, LeadStatus
from app.models.tenant import Branch
from app.models.user import User
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_QUALIFICATION_PROMPT = """\
Analiza esta conversación y extrae en JSON los datos de calificación para una \
clínica de endocrinología pediátrica. Responde ÚNICAMENTE con JSON válido:
{
  "child_age": número o null,
  "child_age_in_range": true si está entre 3 y 15, false si no, null si no se mencionó,
  "consultation_reason": texto del motivo o null,
  "reason_qualifies": true si es talla baja/crecimiento lento/déficit hormonal, false si no, null si no se mencionó,
  "parent_name": nombre del padre/madre o null,
  "parent_city": ciudad mencionada o null,
  "branch_suggested": "Monterrey" o "Santa Fe CDMX" o "Condesa CDMX" o "fuera_cobertura" o null,
  "qualification_status": "calificado" si tiene los 3 criterios, "no_calificado" si explícitamente no cumple, "incompleto" si falta info, "escalar" si hay urgencia médica,
  "qualification_score": float 0.0 a 1.0 según qué tan completa está la calificación,
  "missing_fields": lista de strings con qué falta,
  "escalation_reason": razón de escalado o null
}
CONVERSACIÓN:
{conversation}"""

_STATUS_MAP: dict[str, LeadStatus] = {
    "calificado": LeadStatus.CALIFICADO,
    "no_calificado": LeadStatus.PERDIDO,
    "incompleto": LeadStatus.EN_CALIFICACION,
    "escalar": LeadStatus.ESCALADO,
}

_SENTIMENT_MAP: dict[str, LeadSentiment] = {
    "calificado": LeadSentiment.INTERESADO,
    "no_calificado": LeadSentiment.NEGATIVO,
    "incompleto": LeadSentiment.NEUTRAL,
    "escalar": LeadSentiment.URGENTE,
}

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_whatsapp = WhatsAppService()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_history(history: list[dict]) -> str:
    lines = []
    for msg in history:
        role = "Padre/Madre" if msg["role"] == "user" else "Wali (bot)"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extracts the first JSON object from a Claude response string."""
    # Strip possible markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    return json.loads(match.group())


# ── Core functions ─────────────────────────────────────────────────────────────

async def qualify_lead(
    conversation_history: list[dict],
    lead_id: uuid.UUID,
    branch_id: uuid.UUID,
) -> dict:
    """Evaluates qualification criteria and updates the lead record.

    Creates its own DB session — safe to call via asyncio.create_task().
    Returns the parsed qualification dict, or {} on failure.
    """
    if not conversation_history:
        return {}

    # 1. Ask Claude to extract qualification data
    formatted = _format_history(conversation_history)
    prompt = _QUALIFICATION_PROMPT.format(conversation=formatted)

    try:
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_json(response.content[0].text)
    except Exception:
        logger.exception("qualify_lead: Claude call or JSON parse failed for lead %s", lead_id)
        return {}

    # 2. Persist updates in a fresh session
    async with AsyncSessionLocal() as db:
        lead = await db.get(Lead, lead_id)
        if lead is None:
            logger.warning("qualify_lead: lead %s not found", lead_id)
            return result

        # Merge structured data into qualification_data (JSONB)
        qdata = dict(lead.qualification_data or {})
        for field in ("child_age", "consultation_reason", "parent_name", "parent_city"):
            value = result.get(field)
            if value is not None:
                qdata[field] = value
        lead.qualification_data = qdata

        # Always sync lead.name from the extracted parent_name
        if result.get("parent_name"):
            lead.name = result["parent_name"]

        lead.qualification_score = result.get("qualification_score")

        if result.get("escalation_reason"):
            lead.qualification_notes = result["escalation_reason"]

        q_status_str = result.get("qualification_status", "")

        new_status = _STATUS_MAP.get(q_status_str)
        if new_status:
            lead.status = new_status

        new_sentiment = _SENTIMENT_MAP.get(q_status_str)
        if new_sentiment:
            lead.sentiment = new_sentiment

        await db.commit()
        await db.refresh(lead)

        if q_status_str == "calificado":
            await notify_assistant(lead, db)
        elif q_status_str == "escalar":
            await escalate_to_human(lead, db)

    logger.info(
        "qualify_lead: lead=%s status=%s score=%.2f",
        lead_id,
        result.get("qualification_status"),
        result.get("qualification_score") or 0.0,
    )
    return result


async def notify_assistant(lead: Lead, db: AsyncSession) -> None:
    """Sends a WhatsApp notification to the assigned user (or first branch user)."""
    # Find the recipient user
    if lead.assigned_to:
        user = await db.get(User, lead.assigned_to)
    else:
        result = await db.execute(
            select(User)
            .where(User.branch_id == lead.branch_id, User.is_active.is_(True))
            .order_by(User.id)
            .limit(1)
        )
        user = result.scalar_one_or_none()

    if user is None:
        logger.info("notify_assistant: no active user for branch %s — skipping", lead.branch_id)
        return

    # Assign lead to this user so it's visible in the dashboard
    if lead.assigned_to is None:
        lead.assigned_to = user.id
        await db.commit()

    if not user.wa_phone:
        logger.info("notify_assistant: user %s has no wa_phone — skipping WA message", user.id)
        return

    # Load branch credentials
    branch = await db.get(Branch, lead.branch_id)
    if branch is None or not branch.wa_phone_number_id or not branch.wa_token:
        logger.warning("notify_assistant: branch %s missing WA credentials", lead.branch_id)
        return

    qdata = lead.qualification_data or {}
    parent_name = qdata.get("parent_name") or lead.name or "—"
    child_age = qdata.get("child_age")
    age_str = f"{child_age} años" if child_age is not None else "—"
    motivo = qdata.get("consultation_reason") or "—"
    ciudad = qdata.get("parent_city") or "—"

    message = (
        f"🔔 Nuevo lead calificado\n"
        f"Nombre: {parent_name}\n"
        f"Edad del niño: {age_str}\n"
        f"Motivo: {motivo}\n"
        f"Ciudad: {ciudad}\n"
        f"Ver en dashboard: {settings.FRONTEND_URL}/dashboard/leads/{lead.id}"
    )

    try:
        await _whatsapp.send_text_message(
            to_phone=user.wa_phone,
            message=message,
            phone_number_id=branch.wa_phone_number_id,
            token=branch.wa_token,
        )
        logger.info("notify_assistant: notified user %s for lead %s", user.id, lead.id)
    except Exception:
        logger.exception("notify_assistant: failed to send WA message for lead %s", lead.id)


async def escalate_to_human(lead: Lead, db: AsyncSession) -> None:
    """Marks the active conversation as HANDOFF and the lead as ESCALADO."""
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead.id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.started_at.desc())
    )
    conversation = result.scalars().first()
    if conversation is not None:
        conversation.handled_by = ConversationHandler.HUMAN
        conversation.status = ConversationStatus.HANDOFF

    lead.status = LeadStatus.ESCALADO
    await db.commit()
    logger.info("escalate_to_human: lead %s escalated via qualifier", lead.id)
