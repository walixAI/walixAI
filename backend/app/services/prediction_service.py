"""Lead scoring / prediction service for Walix.

calculate_lead_score() is designed to run as a fire-and-forget asyncio task
(called via asyncio.create_task from bot_engine) OR awaited directly from API
endpoints.  It always opens its own DB session so it is safe in both contexts.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from anthropic import AsyncAnthropic
from langfuse import Langfuse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import SCORING_SYSTEM_PROMPT
from app.core.config import settings
from app.core.database import AsyncSessionLocal, set_tenant_context
from app.models.activity import ActivityType, LeadActivity
from app.models.conversation import Conversation, Message
from app.models.lead import Lead
from app.models.pipeline import PipelineStage
from app.models.scoring import LeadScore

logger = logging.getLogger(__name__)

# See app/ai/bot_engine.py's _background_tasks for why this is needed: an
# asyncio.create_task() result with no strong reference can be cancelled by
# the GC before it completes, silently (CancelledError bypasses `except
# Exception`). _maybe_trigger_closing_agent had the same unreferenced-task
# bug as the scoring trigger it's called from.
_background_tasks: set[asyncio.Task] = set()

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
SCORE_HIGH_THRESHOLD = 70  # triggers closing agent

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_langfuse = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST,
)


# ── JSON extractor ─────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in Claude response: {text[:200]}")
    return json.loads(match.group())


# ── Public entry point ─────────────────────────────────────────────────────────

async def calculate_lead_score(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: AsyncSession | None = None,  # accepted for API compat; always uses own session
) -> dict[str, Any]:
    """Compute a 0-100 prediction score for a lead and persist it.

    Returns the full score dict. Returns empty dict on unrecoverable error so
    callers never need to handle exceptions from this background task.
    """
    try:
        result = await _score_inner(lead_id, tenant_id)
        logger.info(
            "calculate_lead_score: done for lead=%s score=%s trend=%s",
            lead_id, result.get("score"), result.get("current_score_trend"),
        )
        return result
    except Exception:
        logger.exception("calculate_lead_score: failed for lead=%s", lead_id)
        return {}


# ── Core implementation ────────────────────────────────────────────────────────

async def _score_inner(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> dict[str, Any]:
    # ── 1-9. All DB work in a single session ──────────────────────────────────
    score: int
    trend: str
    main_reason: str
    positive_factors: list[str]
    negative_factors: list[str]
    calculated_at: datetime
    score_record_id: uuid.UUID
    input_tokens: int = 0
    output_tokens: int = 0

    async with AsyncSessionLocal() as db:
        await set_tenant_context(db, tenant_id)
        # 1. Load lead
        lead = await db.get(Lead, lead_id)
        if lead is None:
            raise ValueError(f"Lead {lead_id} not found")

        # 2. Last 20 messages across all conversations for this lead
        msgs_q = (
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.lead_id == lead_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        msgs_rows = await db.execute(msgs_q)
        messages = list(reversed(msgs_rows.scalars().all()))

        # 3. Pipeline context
        stage_name: str | None = None
        days_in_stage: int = 0
        if lead.pipeline_stage_id:
            stage = await db.get(PipelineStage, lead.pipeline_stage_id)
            stage_name = stage.name if stage else None

            last_change_row = await db.execute(
                select(LeadActivity)
                .where(
                    LeadActivity.lead_id == lead_id,
                    LeadActivity.activity_type == ActivityType.STAGE_CHANGE,
                )
                .order_by(LeadActivity.created_at.desc())
                .limit(1)
            )
            last_change = last_change_row.scalar_one_or_none()
            if last_change:
                changed_at = last_change.created_at
                if changed_at.tzinfo is None:
                    changed_at = changed_at.replace(tzinfo=timezone.utc)
                days_in_stage = (datetime.now(timezone.utc) - changed_at).days

        # 4. Format interactions for the prompt
        interactions = "\n".join(
            f"[{getattr(m.role, 'value', m.role)}]: {m.content}"
            for m in messages
        ) or "(Sin interacciones registradas)"

        qual_pct = (
            f"{lead.qualification_score * 100:.0f}%"
            if lead.qualification_score is not None
            else "Sin calificar"
        )

        user_message = (
            f"LEAD INFO:\n"
            f"- Nombre: {lead.name or 'Desconocido'}\n"
            f"- Teléfono: {lead.wa_phone}\n"
            f"- Status: {getattr(lead.status, 'value', str(lead.status))}\n"
            f"- Sentiment: {getattr(lead.sentiment, 'value', str(lead.sentiment))}\n"
            f"- Etapa pipeline: {stage_name or 'Sin etapa'}\n"
            f"- Días en etapa: {days_in_stage}\n"
            f"- Score de calificación: {qual_pct}\n\n"
            f"ÚLTIMAS INTERACCIONES ({len(messages)} mensajes):\n"
            f"{interactions}\n\n"
            f"Analiza este lead y devuelve el JSON de predicción."
        )

        # 5. Call Claude Haiku
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            system=SCORING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # 6. Parse response
        parsed = _extract_json(raw_text)
        score = max(0, min(100, int(parsed.get("score", 50))))
        main_reason = str(parsed.get("main_reason", ""))[:120]
        raw_pos = parsed.get("positive_factors", [])
        raw_neg = parsed.get("negative_factors", [])
        positive_factors = raw_pos if isinstance(raw_pos, list) else list(raw_pos.values())
        negative_factors = raw_neg if isinstance(raw_neg, list) else list(raw_neg.values())

        # 7. Trend vs previous score
        prev_row = await db.execute(
            select(LeadScore)
            .where(LeadScore.lead_id == lead_id)
            .order_by(LeadScore.calculated_at.desc())
            .limit(1)
        )
        prev = prev_row.scalar_one_or_none()
        if prev is None:
            trend = "flat"
        elif score > prev.score:
            trend = "up"
        elif score < prev.score:
            trend = "down"
        else:
            trend = "flat"

        # 8. Persist new LeadScore record
        calculated_at = datetime.now(timezone.utc)
        new_score_rec = LeadScore(
            lead_id=lead_id,
            tenant_id=tenant_id,
            score=score,
            positive_factors={"items": positive_factors},
            negative_factors={"items": negative_factors},
            main_reason=main_reason,
            calculated_at=calculated_at,
        )
        db.add(new_score_rec)

        # 9. Update lead denormalized columns
        lead.current_score = score
        lead.current_score_trend = trend

        await db.commit()
        await db.refresh(new_score_rec)
        score_record_id = new_score_rec.id

    # ── 10. Trigger closing agent when score is high (separate session) ────────
    if score >= SCORE_HIGH_THRESHOLD:
        _maybe_trigger_closing_agent(lead_id, tenant_id)

    # ── 11. Langfuse trace ─────────────────────────────────────────────────────
    _trace_scoring(
        lead_id=lead_id,
        tenant_id=tenant_id,
        score=score,
        trend=trend,
        main_reason=main_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    return {
        "id": str(score_record_id),
        "lead_id": str(lead_id),
        "score": score,
        "current_score_trend": trend,
        "main_reason": main_reason,
        "positive_factors": positive_factors,
        "negative_factors": negative_factors,
        "calculated_at": calculated_at.isoformat(),
    }


# ── Closing agent trigger ──────────────────────────────────────────────────────

def _maybe_trigger_closing_agent(lead_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    try:
        from app.agents.closing_agent import run_closing_agent
        task = asyncio.create_task(
            run_closing_agent(lead_id, tenant_id), name=f"closing_agent:{lead_id}"
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info("prediction_service: closing agent queued for lead=%s score>=70", lead_id)
    except ImportError:
        logger.debug("prediction_service: closing agent not available — skipped")


# ── Langfuse tracing ───────────────────────────────────────────────────────────

def _trace_scoring(
    *,
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID,
    score: int,
    trend: str,
    main_reason: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    try:
        with _langfuse.start_as_current_observation(
            as_type="generation",
            name="lead_scoring",
            model=CLAUDE_MODEL,
            usage_details={"input": input_tokens, "output": output_tokens},
            metadata={
                "lead_id": str(lead_id),
                "tenant_id": str(tenant_id),
                "score": score,
                "trend": trend,
                "main_reason": main_reason,
                "sprint": "6",
                "agent_type": "scoring",
            },
        ):
            pass
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            loop.run_in_executor(None, _langfuse.flush)
    except Exception:
        logger.exception("prediction_service: Langfuse trace failed for lead=%s", lead_id)
