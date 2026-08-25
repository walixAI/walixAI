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
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config_loader import build_qualification_json_schema, get_default_config
from app.core.config import settings
from app.core.database import AsyncSessionLocal, set_tenant_context
from app.services.alert_generator import detect_risk
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
)
from app.models.lead import Lead, LeadSentiment, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch
from app.models.user import User
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_whatsapp = WhatsAppService()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_history(history: list[dict], bot_name: str = "Bot") -> str:
    lines = []
    for msg in history:
        role = "Usuario" if msg["role"] == "user" else f"{bot_name} (bot)"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extracts the first JSON object from a Claude response string."""
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
    tenant_id: uuid.UUID,
    config: dict[str, Any] | None = None,
) -> dict:
    """Evaluates qualification criteria and updates the lead record.

    Creates its own DB session — safe to call via asyncio.create_task().
    Returns the parsed qualification dict, or {} on failure.

    tenant_id: el único caller (bot_engine.py::_process_message_inner) ya lo
    tiene disponible como parámetro — se agregó explícitamente en vez de
    resolverlo acá para no necesitar un lookup "pre-tenant" adicional.
    """
    if not conversation_history:
        return {}

    if config is None:
        config = get_default_config("salud")

    logger.info("qualify_lead: starting for lead %s", lead_id)

    # 1. Build prompt and ask Claude to extract qualification data
    try:
        qual = config["qualification"]
        required_fields: list[dict] = qual["required_fields"]
        bot_name: str = config["bot_persona"]["name"]

        fields_schema = build_qualification_json_schema(required_fields)
        formatted = _format_history(conversation_history, bot_name=bot_name)

        prompt = qual["prompt_template"].format(
            objective=qual.get("objective", ""),
            criteria=qual.get("criteria", ""),
            disqualifiers=qual.get("disqualifiers", ""),
            escalation_triggers=qual.get("escalation_triggers", ""),
            fields_schema=fields_schema,
            conversation=formatted,
        )
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_json(response.content[0].text)
        logger.info(
            "qualify_lead: Claude returned status=%r score=%s for lead %s",
            result.get("qualification_status"),
            result.get("qualification_score"),
            lead_id,
        )
    except Exception:
        logger.exception("qualify_lead: prompt/Claude/parse failed for lead %s", lead_id)
        return {}

    # 2. Persist updates in a fresh session
    async with AsyncSessionLocal() as db:
        # Sesión nueva (AsyncSessionLocal directo, no pasa por get_db()) — sin
        # esto, bajo walix_app real (sin BYPASSRLS) ninguna query de acá en
        # adelante ve filas de leads/pipeline_stages/users/branches/
        # conversations. is_local=FALSE: esta función hace varios db.commit()
        # más abajo (líneas ~164, ~222, ~247, ~297 en advance_lead_stage/
        # notify_assistant/escalate_to_human) dentro de la MISMA sesión.
        await set_tenant_context(db, tenant_id)

        lead = await db.get(Lead, lead_id)
        if lead is None:
            logger.warning("qualify_lead: lead %s not found", lead_id)
            return result

        # Merge all industry-specific fields into qualification_data (JSONB)
        qdata = dict(lead.qualification_data or {})
        for field in required_fields:
            value = result.get(field["name"])
            if value is not None:
                qdata[field["name"]] = value
        lead.qualification_data = qdata

        # Sync lead.name from the configured name field.
        # Only overwrite if the extracted value is a real name (not a placeholder).
        _PLACEHOLDERS = {"no especificado", "desconocido", "sin nombre", "n/a", "none", "null", ""}
        name_field = qual.get("name_field")
        extracted_name = (result.get(name_field) or "").strip()
        if name_field and extracted_name and extracted_name.lower() not in _PLACEHOLDERS:
            lead.name = extracted_name

        # Sync lead.contact_phone from the configured phone field (if any).
        # Same guard: skip placeholders so existing numbers aren't erased.
        phone_field = qual.get("phone_field")
        extracted_phone = (result.get(phone_field) or "").strip()
        if phone_field and extracted_phone and extracted_phone.lower() not in _PLACEHOLDERS:
            lead.contact_phone = extracted_phone

        lead.qualification_score = result.get("qualification_score")

        if result.get("escalation_reason"):
            lead.qualification_notes = result["escalation_reason"]

        q_status_str = result.get("qualification_status", "")

        status_map = {k: LeadStatus(v) for k, v in qual["status_map"].items()}
        sentiment_map = {k: LeadSentiment(v) for k, v in qual["sentiment_map"].items()}

        new_status = status_map.get(q_status_str)
        if new_status:
            lead.status = new_status

        new_sentiment = sentiment_map.get(q_status_str)
        if new_sentiment:
            lead.sentiment = new_sentiment

        await db.commit()
        # MITIGACIÓN 2026-08-25 (no el fix definitivo — ver hallazgo de fuga
        # de contexto de tenant entre sesiones concurrentes del pool de
        # conexiones): commit() puede devolver la conexión física al pool;
        # db.refresh() de acá abajo puede recibir una conexión distinta sin
        # este contexto (o con el de otro tenant). Confirmado en producción
        # 2026-08-25 17:31:56 UTC — invalid input syntax for type uuid: ""
        # justo en este db.refresh(lead).
        await set_tenant_context(db, tenant_id)
        await db.refresh(lead)

        await advance_lead_stage(lead, q_status_str, db)
        await detect_risk(lead, result, db)

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


async def advance_lead_stage(lead: Lead, q_status: str, db: AsyncSession) -> None:
    """Advances lead.pipeline_stage_id based on qualification result.

    For "calificado": finds the stage with slug "calificado" (or closest match).
    For "no_calificado": finds the stage with is_lost=True.
    No-ops if the branch has no pipeline stages (backward compat with Sprints 1-3).
    """
    rows = await db.execute(
        select(PipelineStage).where(
            PipelineStage.branch_id == lead.branch_id,
            PipelineStage.is_active.is_(True),
        )
    )
    stages = rows.scalars().all()
    if not stages:
        return

    target: PipelineStage | None = None

    if q_status == "calificado":
        # Prefer exact slug "calificado", fall back to any slug containing "calificad"
        for s in stages:
            if s.slug == "calificado":
                target = s
                break
        if target is None:
            for s in stages:
                if "califica" in s.slug:
                    target = s
                    break
    elif q_status == "no_calificado":
        for s in stages:
            if s.is_lost:
                target = s
                break

    if target is not None:
        lead.pipeline_stage_id = target.id
        await db.commit()
        logger.info(
            "advance_lead_stage: lead=%s → stage=%s (%s)", lead.id, target.name, target.slug
        )


async def notify_assistant(lead: Lead, db: AsyncSession) -> None:
    """Sends a WhatsApp notification to the assigned user (or first branch user)."""
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

    if lead.assigned_to is None:
        lead.assigned_to = user.id
        await db.commit()

    if not user.wa_phone:
        logger.info("notify_assistant: user %s has no wa_phone — skipping WA message", user.id)
        return

    branch = await db.get(Branch, lead.branch_id)
    if branch is None or not branch.wa_phone_number_id or not branch.wa_token:
        logger.warning("notify_assistant: branch %s missing WA credentials", lead.branch_id)
        return

    qdata = lead.qualification_data or {}
    name = lead.name or "—"
    fields_summary = "\n".join(f"  {k}: {v}" for k, v in qdata.items()) or "  —"

    message = (
        f"🔔 Nuevo lead calificado\n"
        f"Nombre: {name}\n"
        f"Datos:\n{fields_summary}\n"
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
        conversation.current_handler = ConversationHandler.HUMAN
        conversation.status = ConversationStatus.HANDOFF

    lead.status = LeadStatus.ESCALADO
    await db.commit()
    logger.info("escalate_to_human: lead %s escalated via qualifier", lead.id)
