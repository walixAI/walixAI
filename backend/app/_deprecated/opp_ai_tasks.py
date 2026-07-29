"""Celery tasks for AI-powered opportunity suggestions."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from anthropic import AsyncAnthropic
from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.opportunity import Opportunity
from app.models.opportunity_activity import OpportunityActivity
from app.models.pipeline import PipelineStage

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 5  # opps per Haiku call batch to respect rate limits


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found: {text[:200]}")
    return json.loads(match.group())


@celery_app.task(
    bind=True,
    name="app.tasks.opp_ai_tasks.generate_bulk_suggestions",
    max_retries=2,
    default_retry_delay=60,
)
def generate_bulk_suggestions(self, branch_id_str: str) -> dict:
    """Generate AI next-step suggestions for all open opportunities in a branch."""
    async def _run() -> dict:
        branch_id = uuid.UUID(branch_id_str)
        anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        processed = 0
        errors = 0

        async with AsyncSessionLocal() as db:
            # Load all open, non-deleted opps for this branch
            result = await db.execute(
                select(Opportunity).where(
                    Opportunity.branch_id == branch_id,
                    Opportunity.status == "open",
                    Opportunity.deleted_at.is_(None),
                )
            )
            opps = result.scalars().all()
            logger.info("[bulk_suggestions] branch=%s opps=%d", branch_id_str, len(opps))

            # Process in batches
            for i in range(0, len(opps), BATCH_SIZE):
                batch = opps[i:i + BATCH_SIZE]
                for opp in batch:
                    try:
                        stage = await db.get(PipelineStage, opp.stage_id) if opp.stage_id else None
                        from datetime import datetime, timezone

                        def _days_since(dt):
                            if dt is None:
                                return 0
                            now = datetime.now(timezone.utc)
                            aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                            return max(0, (now - aware).days)

                        prompt = (
                            f"Eres un asistente de CRM de ventas. Analiza esta oportunidad y sugiere el siguiente paso concreto.\n\n"
                            f"Oportunidad: {opp.title}\n"
                            f"Monto: {opp.amount} {opp.currency}\n"
                            f"Etapa: {stage.name if stage else 'Sin etapa'}\n"
                            f"Días en etapa: {_days_since(opp.stage_entered_at)}\n"
                            f"Última actividad: hace {_days_since(opp.last_activity_at)} días\n"
                            f"Notas: {opp.notes or '—'}\n\n"
                            f'Devuelve ÚNICAMENTE un JSON: {{"text": "<acción concreta ≤120 chars>", "reasoning": "<≤200 chars>", "urgency": "<high|medium|low>"}}'
                        )
                        resp = await anthropic.messages.create(
                            model=CLAUDE_MODEL,
                            max_tokens=400,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        data = _extract_json(resp.content[0].text)
                        text = data.get("text") or ""
                        urgency = data.get("urgency", "medium")

                        opp.ai_suggestion = text[:500] if text else None
                        opp.ai_suggestion_urgency = urgency
                        opp.urgency_score = {"high": 85, "medium": 55, "low": 25}.get(urgency, 55)

                        db.add(OpportunityActivity(
                            opportunity_id=opp.id,
                            tenant_id=opp.tenant_id,
                            type="ai_suggestion",
                            description=(text[:200] if text else "Sugerencia IA generada"),
                        ))
                        processed += 1
                    except Exception:
                        logger.exception("[bulk_suggestions] opp=%s failed", opp.id)
                        errors += 1

                await db.commit()

        return {"processed": processed, "errors": errors}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)
