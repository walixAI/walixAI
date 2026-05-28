import json
import logging
import time
import uuid

from anthropic import AsyncAnthropic
from langfuse import Langfuse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import build_system_prompt
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.services.rag import retrieve_context
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_MAX_TOKENS = 300

CONV_HISTORY_TTL_SECONDS = 86_400  # 24h
CONV_HISTORY_MAX_MESSAGES = 10

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


async def process_message(
    wa_phone: str,
    message_body: str,
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID,
    message_id: str,
) -> None:
    async with AsyncSessionLocal() as db:
        # 1. Lead
        lead = await _get_or_create_lead(db, wa_phone, branch_id, tenant_id)

        # 2. Conversation
        conversation = await _get_or_create_active_conversation(db, lead)

        # 3. Persist the user message regardless of handler so the agent can
        #    see it in the dashboard even when in human control mode.
        db.add(
            Message(
                conversation_id=conversation.id,
                wa_message_id=message_id,
                role=MessageRole.USER,
                content=message_body,
            )
        )

        # 4. Human in control — save the message but let bot stay silent.
        if conversation.handled_by == ConversationHandler.HUMAN:
            await db.commit()
            logger.info(
                "Conversation %s under human control — bot silent", conversation.id
            )
            return

        await db.commit()

        # 5. Pull conversation history from Redis (chronological list of
        #    {role, content} dicts).
        history_key = f"conv:{conversation.id}"
        raw_history = await redis_client.get(history_key)
        history: list[dict[str, str]] = json.loads(raw_history) if raw_history else []

        # 6. Build messages payload for Anthropic: history + current user turn.
        anthropic_messages = history + [{"role": "user", "content": message_body}]

        # 6.5 RAG: retrieve relevant KB chunks and inject into system prompt.
        rag_chunks: list[dict] = []
        try:
            rag_chunks = await retrieve_context(message_body, tenant_id, db)
            if rag_chunks:
                lead.last_rag_context = {
                    "query": message_body,
                    "chunks": [
                        {
                            "title": c["document_title"],
                            "section": c["section"],
                            "similarity": c["similarity"],
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

        system_prompt = build_system_prompt(rag_chunks)

        # 7 & 8. Call Claude and measure latency.
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

        # 9. Persist the assistant message.
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
            conversation.handled_by = ConversationHandler.HUMAN
            lead.status = LeadStatus.ESCALADO
            logger.info(
                "Escalating conversation %s (lead %s) to human",
                conversation.id,
                lead.id,
            )

        await db.commit()

        # 10. Update Redis with both turns, keep only the most recent N, 24h TTL.
        updated_history = anthropic_messages + [
            {"role": "assistant", "content": assistant_text}
        ]
        updated_history = updated_history[-CONV_HISTORY_MAX_MESSAGES:]
        await redis_client.set(
            history_key,
            json.dumps(updated_history),
            ex=CONV_HISTORY_TTL_SECONDS,
        )

        # 12. Send the reply via WhatsApp using the branch's credentials.
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

    # 13. Langfuse trace. Observability must not break message processing,
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
            },
        ):
            pass
        langfuse_client.flush()
    except Exception:
        logger.exception("Failed to send trace to Langfuse")
