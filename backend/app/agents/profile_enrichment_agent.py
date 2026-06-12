"""Profile enrichment agent: detects leads without company and suggests filling it from conversation."""
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
from app.models.lead import Lead
from app.models.user import User

logger = logging.getLogger(__name__)
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = (
    "Eres un extractor de datos. Analiza esta conversación y extrae la empresa o negocio "
    "del contacto si se menciona. Responde SOLO en JSON: "
    '{"company": "nombre o null", "confidence": "high|medium|low"}'
)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in response: {text[:200]}")
    return json.loads(match.group())


async def run_profile_enrichment_agent(
    tenant_id: uuid.UUID, db: AsyncSession
) -> int:
    """Scan tenant leads without company and create enrichment suggestions. Returns count created."""
    try:
        return await _run_enrichment(tenant_id, db)
    except Exception:
        logger.exception("profile_enrichment_agent: unhandled error tenant=%s", tenant_id)
        return 0


async def _run_enrichment(tenant_id: uuid.UUID, db: AsyncSession) -> int:
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(hours=72)

    # Correlated subquery: message count across all conversations for each lead
    msg_count_subq = (
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.lead_id == Lead.id)
        .correlate(Lead)
        .scalar_subquery()
    )

    # Correlated EXISTS: a recent enrichment suggestion already targets this lead
    has_recent_suggestion = (
        select(AgentSuggestion.id)
        .where(
            AgentSuggestion.agent_type == "profile_enrichment",
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
                Lead.company.is_(None),
                msg_count_subq >= 3,
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
            logger.exception("profile_enrichment_agent: failed for lead=%s", lead.id)

    logger.info(
        "profile_enrichment_agent: tenant=%s suggestions_created=%d", tenant_id, created
    )
    return created


async def _process_lead(lead: Lead, db: AsyncSession) -> bool:
    # Last 10 messages across all conversations for this lead
    msgs = (
        await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.lead_id == lead.id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    if not msgs:
        return False

    msgs = list(reversed(msgs))  # chronological order
    history_text = "\n".join(
        f"[{getattr(m.role, 'value', m.role)}]: {m.content}" for m in msgs
    )

    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=150,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Conversación:\n{history_text}"}],
    )
    parsed = _extract_json(response.content[0].text)

    company = parsed.get("company")
    confidence = parsed.get("confidence", "low")

    if not company or company == "null" or confidence == "low":
        return False

    # Total message count for the suggestion text
    msg_count = len(msgs)

    target_user: User | None = None
    if lead.assigned_to:
        target_user = await db.get(User, lead.assigned_to)

    db.add(
        AgentSuggestion(
            tenant_id=lead.tenant_id,
            branch_id=lead.branch_id,
            agent_type="profile_enrichment",
            trigger_description="Contacto sin empresa con 3+ conversaciones",
            suggestion_text=(
                f'El contacto {lead.name or lead.wa_phone} tiene {msg_count} mensajes '
                f'pero sin empresa registrada. Walix detectó que podría ser de "{company}". '
                f"¿Actualizo el perfil?"
            ),
            action_payload={"lead_id": str(lead.id), "company": company},
            target_role="asesor",
            target_user_id=target_user.id if target_user else None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
    )
    await db.flush()

    logger.info(
        "profile_enrichment_agent: suggestion created lead=%s company=%s confidence=%s",
        lead.id, company, confidence,
    )
    return True
