"""Aprendiz agent: deterministic pattern mining over AIOutcomeFeedback.

No LLM — patterns are pure arithmetic aggregations; Claude adds no value
here and introduces numeric error risk.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_memory import AIOutcomeFeedback, AITenantPattern
from app.models.deal import Deal

import logging

logger = logging.getLogger(__name__)

MX_TZ = ZoneInfo("America/Mexico_City")
_LOOKBACK_DAYS = 7
_MIN_SAMPLE = 20
_HIGH_CONF_THRESHOLD = 50
_HIGH_CONF = 0.9
_LOW_CONF = 0.6

_DOW_NAMES = {
    0: "domingo", 1: "lunes", 2: "martes", 3: "miércoles",
    4: "jueves", 5: "viernes", 6: "sábado",
}


def _confidence(sample_size: int) -> float:
    return _HIGH_CONF if sample_size >= _HIGH_CONF_THRESHOLD else _LOW_CONF


async def _upsert_pattern(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    pattern_type: str,
    pattern_data: dict[str, Any],
    confidence_score: float,
    sample_size: int,
    now: datetime,
) -> None:
    values = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "pattern_type": pattern_type,
        "pattern_data": pattern_data,
        "confidence_score": confidence_score,
        "sample_size": sample_size,
        "created_at": now,
        "updated_at": now,
    }
    stmt = (
        pg_insert(AITenantPattern)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_ai_tenant_patterns_tenant_type",
            set_={
                "pattern_data": values["pattern_data"],
                "confidence_score": values["confidence_score"],
                "sample_size": values["sample_size"],
                "updated_at": values["updated_at"],
            },
        )
    )
    await db.execute(stmt)


async def run_aprendiz_agent(tenant_id: uuid.UUID, db: AsyncSession) -> int:
    """Mine business patterns from the last 7 days of outcome feedback.

    Returns the number of patterns upserted.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=_LOOKBACK_DAYS)
    patterns_upserted = 0

    # ── a) contact_responded: best_followup_day + peak_response_hours ─────────

    responded_rows = (await db.execute(
        select(AIOutcomeFeedback.created_at)
        .where(
            AIOutcomeFeedback.tenant_id == tenant_id,
            AIOutcomeFeedback.outcome == "contact_responded",
            AIOutcomeFeedback.created_at >= cutoff,
        )
    )).scalars().all()

    total_responded = len(responded_rows)

    if total_responded >= _MIN_SAMPLE:
        dow_counts_sun: Counter[int] = Counter()
        hour_counts: Counter[int] = Counter()
        for ts in responded_rows:
            local = ts.astimezone(MX_TZ)
            isoday = local.isoweekday()  # 1=Mon … 7=Sun
            dow_counts_sun[0 if isoday == 7 else isoday] += 1  # 0=Sun, 1=Mon … 6=Sat
            hour_counts[local.hour] += 1

        best_dow = dow_counts_sun.most_common(1)[0][0]
        top3_hours = [h for h, _ in hour_counts.most_common(3)]
        conf = _confidence(total_responded)

        await _upsert_pattern(
            db, tenant_id,
            pattern_type="best_followup_day",
            pattern_data={
                "day": _DOW_NAMES.get(best_dow, str(best_dow)),
                "counts_by_day": {_DOW_NAMES.get(k, str(k)): v for k, v in dow_counts_sun.items()},
            },
            confidence_score=conf,
            sample_size=total_responded,
            now=now,
        )
        patterns_upserted += 1

        await _upsert_pattern(
            db, tenant_id,
            pattern_type="peak_response_hours",
            pattern_data={
                "hours": top3_hours,
                "counts_by_hour": {str(h): c for h, c in hour_counts.items()},
            },
            confidence_score=conf,
            sample_size=total_responded,
            now=now,
        )
        patterns_upserted += 1

    # ── b) deal_closed: avg_close_days ────────────────────────────────────────

    closed_rows = (await db.execute(
        select(AIOutcomeFeedback.days_to_outcome)
        .where(
            AIOutcomeFeedback.tenant_id == tenant_id,
            AIOutcomeFeedback.outcome == "deal_closed",
            AIOutcomeFeedback.created_at >= cutoff,
            AIOutcomeFeedback.days_to_outcome.is_not(None),
        )
    )).scalars().all()

    total_closed = len(closed_rows)

    if total_closed >= _MIN_SAMPLE:
        avg_days = round(sum(closed_rows) / total_closed, 1)
        await _upsert_pattern(
            db, tenant_id,
            pattern_type="avg_close_days",
            pattern_data={"avg_days": avg_days},
            confidence_score=_confidence(total_closed),
            sample_size=total_closed,
            now=now,
        )
        patterns_upserted += 1

    # ── c) top_objections ─────────────────────────────────────────────────────

    lost_rows = (await db.execute(
        select(Deal.lost_reason)
        .where(
            Deal.tenant_id == tenant_id,
            Deal.is_lost.is_(True),
            Deal.updated_at >= cutoff,
            Deal.lost_reason.is_not(None),
        )
    )).scalars().all()

    total_lost = len(lost_rows)

    if total_lost >= _MIN_SAMPLE:
        reason_counts: Counter[str] = Counter(lost_rows)
        top3 = [{"reason": r, "count": c} for r, c in reason_counts.most_common(3)]
        await _upsert_pattern(
            db, tenant_id,
            pattern_type="top_objections",
            pattern_data={"top_reasons": top3},
            confidence_score=_confidence(total_lost),
            sample_size=total_lost,
            now=now,
        )
        patterns_upserted += 1

    logger.info(
        "[aprendiz] tenant=%s patterns_upserted=%d (responded=%d, closed=%d, lost=%d)",
        tenant_id, patterns_upserted, total_responded, total_closed, total_lost,
    )
    return patterns_upserted
