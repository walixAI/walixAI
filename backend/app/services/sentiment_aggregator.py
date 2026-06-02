"""Sentiment snapshot aggregator for Walix.

calculate_sentiment_snapshot(branch_id, db) computes sentiment averages
across active leads and UPSERTS the result into sentiment_snapshots.
"""
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadSentiment, LeadStatus
from app.models.metrics import SentimentSnapshot
from app.models.tenant import Branch

logger = logging.getLogger(__name__)

SENTIMENT_SCORE: dict[str, float] = {
    LeadSentiment.INTERESADO.value: 1.0,
    LeadSentiment.URGENTE.value: 0.8,
    LeadSentiment.NEUTRAL.value: 0.5,
    LeadSentiment.NEGATIVO.value: 0.0,
}

_TERMINAL = [LeadStatus.PERDIDO, LeadStatus.CALIFICADO]


async def calculate_sentiment_snapshot(
    branch_id: uuid.UUID,
    db: AsyncSession,
) -> SentimentSnapshot:
    """Compute sentiment aggregates for active leads and UPSERT into sentiment_snapshots.

    Does NOT commit — caller is responsible for committing.
    """
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")

    # Load all active leads with a non-null sentiment
    leads_result = await db.execute(
        select(Lead).where(
            Lead.branch_id == branch_id,
            Lead.status.notin_(_TERMINAL),
            Lead.sentiment.isnot(None),
        )
    )
    leads = leads_result.scalars().all()

    if not leads:
        overall_score = 0.5
        distribution: dict[str, Any] = {}
        by_stage: dict[str, Any] = {}
        by_agent: dict[str, Any] = {}
    else:
        scores = [
            SENTIMENT_SCORE.get(
                getattr(lead.sentiment, "value", str(lead.sentiment)), 0.5
            )
            for lead in leads
        ]
        overall_score = round(sum(scores) / len(scores), 4)

        # distribution: count + percentage per sentiment value
        distribution = _build_distribution(leads, len(leads))

        # by_stage: average score per pipeline_stage_id
        by_stage = _group_average(
            leads,
            key_fn=lambda l: str(l.pipeline_stage_id) if l.pipeline_stage_id else None,
        )

        # by_agent: average score per assigned_to
        by_agent = _group_average(
            leads,
            key_fn=lambda l: str(l.assigned_to) if l.assigned_to else None,
        )

    # UPSERT for today's snapshot
    today = datetime.now(timezone.utc).date()
    existing = await db.execute(
        select(SentimentSnapshot).where(
            SentimentSnapshot.branch_id == branch_id,
            SentimentSnapshot.snapshot_date == today,
        )
    )
    snapshot = existing.scalar_one_or_none()
    if snapshot is None:
        snapshot = SentimentSnapshot(
            branch_id=branch_id,
            tenant_id=branch.tenant_id,
            snapshot_date=today,
        )
        db.add(snapshot)

    snapshot.overall_score = overall_score
    snapshot.distribution = distribution
    snapshot.by_stage = by_stage
    snapshot.by_agent = by_agent

    await db.flush()
    logger.info(
        "sentiment_aggregator: branch=%s overall=%.3f leads=%d",
        branch_id, overall_score, len(leads),
    )
    return snapshot


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_distribution(leads: list[Lead], total: int) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for lead in leads:
        val = getattr(lead.sentiment, "value", str(lead.sentiment))
        counts[val] = counts.get(val, 0) + 1
    return {
        val: {"count": cnt, "pct": round(cnt / total * 100, 1)}
        for val, cnt in counts.items()
    }


def _group_average(
    leads: list[Lead],
    key_fn,
) -> dict[str, float]:
    groups: dict[str, list[float]] = {}
    for lead in leads:
        key = key_fn(lead)
        if key is None:
            continue
        score = SENTIMENT_SCORE.get(
            getattr(lead.sentiment, "value", str(lead.sentiment)), 0.5
        )
        groups.setdefault(key, []).append(score)
    return {k: round(sum(v) / len(v), 4) for k, v in groups.items() if v}
