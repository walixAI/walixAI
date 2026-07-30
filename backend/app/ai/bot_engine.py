import asyncio
import json
import logging
import time
import uuid
from typing import Any

from anthropic import AsyncAnthropic
from langfuse import Langfuse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import config_loader
from app.ai.qualifier import qualify_lead
from app.ai.retrieval import format_rag_context, retrieve_context
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.ai_memory import AIMemoryEvent
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_MAX_TOKENS = 300

CONV_HISTORY_TTL_SECONDS = 86_400  # 24h
CONV_HISTORY_MAX_MESSAGES = 8

ESCALATION_PHRASES: tuple[str, ...] = (
    "te voy a conectar con",
    "voy a conectarte con",
    "conectarte con un asesor",
    "un asesor te contactará",
    "un especialista te contactará",
    "te contactará en breve",
    "escalando tu caso",
)

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
    result = await db.execute(
        select(Lead).where(Lead.wa_phone == wa_phone, Lead.branch_id == branch_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        lead = Lead(wa_phone=wa_phone, branch_id=branch_id, tenant_id=tenant_id)
        db.add(lead)
        await db.flush()
    return lead


async def _get_or_create_active_conversation(
    db: AsyncSession,
    lead: Lead,
) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead.id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.started_at.desc())
    )
    conv = result.scalars().first()
    if conv is None:
        conv = Conversation(lead_id=lead.id, branch_id=lead.branch_id)
        db.add(conv)
        await db.flush()
    return conv


def _needs_escalation(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in ESCALATION_PHRASES)


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
    raw = await redis_client.get(f"conv:{conversation_id}")
    if raw:
        return json.loads(raw)

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
        # 1. Load branch AI config (custom or industry default)
        cfg = await config_loader.get_branch_config(branch_id, db)
        logger.info("process_message: config loaded for branch=%s", branch_id)

        # 2. Lead
        lead = await _get_or_create_lead(db, wa_phone, branch_id, tenant_id)
        logger.info("process_message: lead=%s", lead.id)

        # 3. Conversation
        conversation = await _get_or_create_active_conversation(db, lead)
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

            from app.tasks.ai_memory_tasks import update_entity_context_task
            update_entity_context_task.delay(event_id)
        except Exception:
            logger.exception(
                "[ai_memory] failed to create memory event for inbound msg from lead %s", lead.id
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
        rag_chunks: list[dict] = []
        try:
            rag_chunks = await retrieve_context(message_body, str(tenant_id))
            if rag_chunks:
                lead.last_rag_context = {
                    "query": message_body,
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

        # 11. Escalation check on the assistant's reply.
        if _needs_escalation(assistant_text):
            conversation.status = ConversationStatus.HANDOFF
            conversation.current_handler = ConversationHandler.HUMAN
            lead.status = LeadStatus.ESCALADO
            logger.info(
                "Escalating conversation %s (lead %s) to human",
                conversation.id,
                lead.id,
            )

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

        # 13. Persist history in Redis, 24h TTL.
        await redis_client.set(
            history_key,
            json.dumps(updated_history),
            ex=CONV_HISTORY_TTL_SECONDS,
        )

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
        await qualify_lead(updated_history, lead.id, branch_id, config=cfg)
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
