import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from langfuse import Langfuse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import config_loader
from app.ai.qualifier import qualify_lead
from app.ai.retrieval import format_rag_context, retrieve_context
from app.core.config import settings
from app.core.database import AsyncSessionLocal, set_tenant_context
from app.core.redis import redis_client
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.agent import AgentSuggestion
from app.models.ai_memory import AIMemoryEvent, AIOutcomeFeedback
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.tenant import Branch
from app.services.whatsapp import WhatsAppService, _normalize_mx_phone

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_MAX_TOKENS = 300

CONV_HISTORY_TTL_SECONDS = 86_400  # 24h
CONV_HISTORY_MAX_MESSAGES = 8


anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
whatsapp_service = WhatsAppService()

langfuse_client = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST,
)


async def _get_or_create_lead(
    db: AsyncSession,
    wa_phone: str,
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Lead:
    # Always work with the canonical format (52XXXXXXXXXX for MX mobiles).
    # Meta delivers 521XXXXXXXXXX; searching both variants covers existing rows
    # that were saved before this normalization was enforced.
    canonical = _normalize_mx_phone(wa_phone)
    phones = list({wa_phone, canonical})

    # 1. Same branch — most recent lead wins when duplicates exist.
    result = await db.execute(
        select(Lead).where(
            Lead.wa_phone.in_(phones),
            Lead.branch_id == branch_id,
            Lead.deleted_at.is_(None),
        ).order_by(Lead.created_at.desc()).limit(1)
    )
    lead = result.scalar_one_or_none()
    if lead is not None:
        return lead

    # 2. Any other branch of the same tenant — recognize returning contacts.
    result = await db.execute(
        select(Lead).where(
            Lead.wa_phone.in_(phones),
            Lead.tenant_id == tenant_id,
            Lead.deleted_at.is_(None),
        ).order_by(Lead.created_at.desc()).limit(1)
    )
    lead = result.scalar_one_or_none()
    if lead is not None:
        return lead

    # 3. New contact — always store the canonical phone format.
    lead = Lead(
        wa_phone=canonical,
        branch_id=branch_id,
        tenant_id=tenant_id,
        source=LeadSource.WHATSAPP_INBOUND,
        prospection_source="whatsapp_inbound",
    )
    db.add(lead)
    await db.flush()
    return lead


async def _get_or_create_active_conversation(
    db: AsyncSession,
    lead: Lead,
    branch_id: uuid.UUID,
) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead.id,
            Conversation.branch_id == branch_id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.started_at.desc())
    )
    conv = result.scalars().first()
    if conv is None:
        conv = Conversation(lead_id=lead.id, branch_id=branch_id)
        db.add(conv)
        await db.flush()
    return conv



def get_lead_profile(lead: Lead, config: dict[str, Any]) -> str:
    """Returns a formatted string of already-collected lead data to inject into the prompt."""
    qdata = lead.qualification_data or {}
    required_fields: list[dict] = config["qualification"]["required_fields"]

    collected = [
        (f["name"], qdata[f["name"]])
        for f in required_fields
        if qdata.get(f["name"]) is not None
    ]

    if not collected:
        return "DATOS YA RECOPILADOS (no volver a preguntar):\n- (ninguno aún)"

    lines = ["DATOS YA RECOPILADOS (no volver a preguntar):"]
    for name, value in collected:
        lines.append(f"- {name}: {value}")
    return "\n".join(lines)


async def get_conversation_context(
    conversation_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict[str, str]]:
    """Returns conversation history as [{role, content}] list.

    Reads from Redis first; falls back to the last N DB messages when the
    Redis key has expired or is missing (e.g. after a Railway redeploy).
    """
    try:
        raw = await redis_client.get(f"conv:{conversation_id}")
        if raw:
            return json.loads(raw)
    except Exception:
        logger.warning("get_conversation_context: Redis unavailable, falling back to DB")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(CONV_HISTORY_MAX_MESSAGES)
    )
    messages = result.scalars().all()
    return [{"role": getattr(m.role, "value", m.role), "content": m.content} for m in reversed(messages)]


async def process_message(
    wa_phone: str,
    message_body: str,
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
    message_id: str,
) -> None:
    logger.info("process_message: start wa=%s branch=%s msg=%s", wa_phone, branch_id, message_id)
    try:
        await _process_message_inner(wa_phone, message_body, branch_id, tenant_id, message_id)
    except Exception:
        logger.exception(
            "process_message: unhandled exception wa=%s branch=%s msg=%s",
            wa_phone, branch_id, message_id,
        )


async def _process_message_inner(
    wa_phone: str,
    message_body: str,
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
    message_id: str,
) -> None:
    async with AsyncSessionLocal() as db:
        # tenant_id ya llega como parámetro (branch.tenant_id, columna NOT
        # NULL — el único caller es app/api/webhooks.py) pero esta sesión es
        # nueva (AsyncSessionLocal() directo, no pasa por get_db()/el
        # middleware HTTP) y arranca sin contexto de tenant seteado. Bajo el
        # rol admin (bypass de RLS) esto era inofensivo; bajo walix_app real,
        # CUALQUIER query de acá en adelante contra una tabla con RLS
        # (branches, leads, conversations, agent_suggestions...) fallaba o no
        # veía filas — confirmado en vivo: "invalid input syntax for type
        # uuid" en el SELECT de Branch del paso 14.
        #
        # is_local=FALSE (no TRUE): esta función hace varios db.commit()
        # dentro del mismo `async with` (pasos 4a, 4b, 5, 11) — con
        # is_local=TRUE el contexto se borraría en el primer commit y el
        # resto de las queries de la función volverían a fallar. FALSE
        # persiste a nivel sesión, que es exactamente lo que dura este
        # `async with` — mismo criterio que ya usa get_db() en
        # app/core/database.py.
        await set_tenant_context(db, tenant_id)

        # 1. Load branch AI config (custom or industry default)
        cfg = await config_loader.get_branch_config(branch_id, db)
        logger.info("process_message: config loaded for branch=%s", branch_id)

        # 2. Lead
        lead = await _get_or_create_lead(db, wa_phone, branch_id, tenant_id)
        logger.info("process_message: lead=%s", lead.id)

        # 3. Conversation
        conversation = await _get_or_create_active_conversation(db, lead, branch_id)
        logger.info("process_message: conversation=%s", conversation.id)

        # 4. Persist the user message regardless of handler so the agent can
        #    see it in the dashboard even when in human control mode.
        inbound_msg = Message(
            conversation_id=conversation.id,
            wa_message_id=message_id,
            role=MessageRole.USER,
            content=message_body,
        )
        db.add(inbound_msg)

        # 4a. AI memory event — flushed here, committed by existing commits below.
        try:
            await db.flush()  # assign inbound_msg.id
            memory_event = AIMemoryEvent(
                tenant_id=tenant_id,
                entity_type="conversation",
                entity_id=conversation.id,
                event_type="wa_message_received",
                event_data={
                    "message_id": message_id,
                    "text": message_body[:500],
                    "lead_id": str(lead.id),
                },
                actor_id=None,
            )
            db.add(memory_event)
            await db.flush()  # assign memory_event.id
            event_id = str(memory_event.id)
            await db.commit()

            from app.tasks.ai_memory_tasks import update_entity_context_task
            update_entity_context_task.delay(event_id)
        except Exception:
            logger.exception(
                "[ai_memory] failed to create memory event for inbound msg from lead %s", lead.id
            )

        # 4b. Outcome feedback — detect contact_responded when lead replies after outbound message.
        try:
            now = datetime.now(timezone.utc)
            last_outbound = (await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.role == MessageRole.ASSISTANT,
                    Message.created_at >= now - timedelta(hours=24),
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()

            if last_outbound is not None:
                sug = (await db.execute(
                    select(AgentSuggestion)
                    .where(
                        AgentSuggestion.tenant_id == tenant_id,
                        AgentSuggestion.entity_type == "contact",
                        AgentSuggestion.entity_id == lead.id,
                        AgentSuggestion.status.in_(["confirmed", "executed"]),
                        AgentSuggestion.created_at >= now - timedelta(days=7),
                    )
                    .order_by(AgentSuggestion.created_at.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if sug is not None:
                    hours_elapsed = (now - last_outbound.created_at).total_seconds() / 3600
                    days_to_outcome = max(0, int(hours_elapsed / 24))
                    db.add(AIOutcomeFeedback(
                        tenant_id=tenant_id,
                        suggestion_id=sug.id,
                        action_taken="whatsapp_reply",
                        entity_type="contact",
                        entity_id=lead.id,
                        outcome="contact_responded",
                        outcome_value=0,
                        days_to_outcome=days_to_outcome,
                        context_at_action={"conversation_id": str(conversation.id)},
                    ))
                    await db.commit()
        except Exception:
            logger.exception(
                "[ai_outcome] failed to create outcome feedback for contact response from lead %s", lead.id
            )

        # 5. Human in control — save the message but let bot stay silent.
        if conversation.current_handler == ConversationHandler.HUMAN:
            await db.commit()
            logger.info(
                "Conversation %s under human control — bot silent", conversation.id
            )
            return

        await db.commit()

        # 6. Pull conversation history (Redis first, DB fallback).
        history_key = f"conv:{conversation.id}"
        history = await get_conversation_context(conversation.id, db)

        # 7. Build messages payload: history + current user turn.
        anthropic_messages = history + [{"role": "user", "content": message_body}]

        # 8. RAG: retrieve relevant KB chunks.
        # Build query from last 3 user turns so short follow-ups like "hola"
        # still carry prior topic context into the vector search.
        recent_user_msgs = [m["content"] for m in history[-4:] if m.get("role") == "user"]
        rag_query = " ".join(recent_user_msgs + [message_body])
        rag_chunks: list[dict] = []
        try:
            rag_chunks = await retrieve_context(rag_query, str(tenant_id))
            if rag_chunks:
                lead.last_rag_context = {
                    "query": rag_query,
                    "chunks": [
                        {
                            "id": c["id"],
                            "filename": c["filename"],
                            "rrf_score": c["rrf_score"],
                        }
                        for c in rag_chunks
                    ],
                }
                logger.info(
                    "RAG: %d chunks retrieved for conversation %s",
                    len(rag_chunks),
                    conversation.id,
                )
        except Exception:
            logger.exception("RAG retrieval failed — continuing without context")

        # 9. Build 4-layer system prompt: persona + channel rules + RAG + lead profile.
        lead_profile = get_lead_profile(lead, cfg)
        base_prompt = config_loader.build_system_prompt(cfg)
        parts = [base_prompt]
        rag_ctx = format_rag_context(rag_chunks)
        if rag_ctx:
            parts.append(rag_ctx)
        if lead_profile:
            parts.append(lead_profile)
        system_prompt = "\n\n".join(parts)

        # 10. Call Claude and measure latency.
        logger.info("process_message: calling Claude for lead=%s", lead.id)
        start = time.monotonic()
        response = await anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=system_prompt,
            messages=anthropic_messages,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        assistant_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        total_tokens = input_tokens + output_tokens

        # 10b. Persist the assistant message.
        db.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=assistant_text,
                tokens_used=total_tokens,
                latency_ms=latency_ms,
            )
        )

        # 11. Escalation is handled exclusively by qualify_lead (step 15).
        #     Phrase-based detection removed — it was too eager and escalated on
        #     informational responses that happened to mention connecting to an advisor.
        await db.commit()

        # 11b. Trigger prediction scoring as a non-blocking background task.
        # Uses its own DB session; never delays the WhatsApp reply.
        from app.services.prediction_service import calculate_lead_score
        asyncio.create_task(
            calculate_lead_score(lead.id, lead.tenant_id),
            name=f"score:{lead.id}",
        )

        # 12. Build full history (user + assistant) for Redis and qualifier.
        updated_history = anthropic_messages + [
            {"role": "assistant", "content": assistant_text}
        ]
        updated_history = updated_history[-CONV_HISTORY_MAX_MESSAGES:]

        # 13. Persist history in Redis, 24h TTL (best-effort; DB is the source of truth).
        try:
            await redis_client.set(
                history_key,
                json.dumps(updated_history),
                ex=CONV_HISTORY_TTL_SECONDS,
            )
        except Exception:
            logger.warning("bot_engine: Redis unavailable, conversation history not cached")

        # 14. Send the reply via WhatsApp using the branch's credentials.
        branch = await db.get(Branch, branch_id)
        if branch is None or not branch.wa_phone_number_id or not branch.wa_token:
            logger.error(
                "Branch %s missing wa credentials — cannot send reply", branch_id
            )
        else:
            await whatsapp_service.send_text_message(
                to_phone=wa_phone,
                message=assistant_text,
                phone_number_id=branch.wa_phone_number_id,
                token=branch.wa_token,
            )

    # 15. Run qualifier after the session is closed and the WA reply is sent.
    #     process_message is already a background task, so awaiting here is safe.
    logger.info("process_message: calling qualify_lead for lead=%s", lead.id)
    try:
        await qualify_lead(updated_history, lead.id, branch_id, tenant_id, config=cfg)
        logger.info("process_message: qualify_lead done for lead=%s", lead.id)
    except Exception:
        logger.exception("process_message: qualify_lead raised for lead %s", lead.id)

    # 16. Langfuse trace. Observability must not break message processing,
    #     so failures here are logged and swallowed.
    try:
        with langfuse_client.start_as_current_observation(
            as_type="generation",
            name="bot_response",
            model=CLAUDE_MODEL,
            input=message_body,
            output=assistant_text,
            usage_details={"input": input_tokens, "output": output_tokens},
            metadata={
                "tokens": total_tokens,
                "latency_ms": latency_ms,
                "lead_id": str(lead.id),
                "branch_id": str(branch_id),
                "tenant_id": str(tenant_id),
                "conversation_id": str(conversation.id),
                "rag_chunks_count": len(rag_chunks),
                "rag_chunks_sources": [c["filename"] for c in rag_chunks],
                "qualification_score": lead.qualification_score,
            },
        ):
            pass
        # flush() is sync/blocking — run in executor to avoid blocking the event loop
        await asyncio.get_event_loop().run_in_executor(None, langfuse_client.flush)
    except Exception:
        logger.exception("Failed to send trace to Langfuse")
