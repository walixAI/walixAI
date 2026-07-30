"""Aprendiz agent: deterministic pattern mining over AIOutcomeFeedback.

No LLM — patterns are pure arithmetic aggregations; Claude adds no value
here and introduces numeric error risk.
"""
from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_memory import AIDraftEdit, AIOutcomeFeedback, AITenantPattern, AIUserProfile
from app.models.deal import Deal
from app.models.pipeline import PipelineStage
from app.models.user import User

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


async def update_user_profiles(tenant_id: uuid.UUID, db: AsyncSession) -> int:
    """Compute per-user closing statistics and upsert AIUserProfile rows.

    Operates over the full historical record (no time window) — same
    criterion as Lovable for seller performance metrics.
    Returns the number of profiles upserted.
    """
    now = datetime.now(timezone.utc)

    users = (await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
        )
    )).scalars().all()

    profiles_upserted = 0

    for user in users:
        deals = (await db.execute(
            select(Deal).where(
                Deal.owner_id == user.id,
                Deal.tenant_id == tenant_id,
            )
        )).scalars().all()

        if not deals:
            continue

        won_deals = [d for d in deals if d.is_won]
        lost_deals = [d for d in deals if d.is_lost]
        total_won = len(won_deals)
        total_lost = len(lost_deals)
        denom = total_won + total_lost
        close_rate = total_won / denom if denom > 0 else 0.0

        # best_close_day and best_close_hour — only when enough signal
        best_close_day: str | None = None
        best_close_hour: int | None = None

        if total_won >= 3:
            dow_counts: Counter[int] = Counter()
            hour_counts_u: Counter[int] = Counter()
            for d in won_deals:
                local = d.updated_at.astimezone(MX_TZ)
                isoday = local.isoweekday()  # 1=Mon … 7=Sun
                dow_counts[0 if isoday == 7 else isoday] += 1  # 0=Sun, 1=Mon … 6=Sat
                hour_counts_u[local.hour] += 1
            best_dow = dow_counts.most_common(1)[0][0]
            best_close_day = _DOW_NAMES.get(best_dow, str(best_dow))
            best_close_hour = hour_counts_u.most_common(1)[0][0]

        # top_performing_stage — stage name with most won deals
        top_performing_stage: str | None = None
        if won_deals:
            stage_counts: Counter[uuid.UUID] = Counter(
                d.pipeline_stage_id for d in won_deals if d.pipeline_stage_id
            )
            if stage_counts:
                top_stage_id = stage_counts.most_common(1)[0][0]
                stage = await db.get(PipelineStage, top_stage_id)
                if stage:
                    top_performing_stage = stage.name

        # communication_style + preferred_message_length — from AIDraftEdit (>= 5 edits)
        communication_style: str | None = None
        preferred_message_length: str | None = None

        draft_edits = (await db.execute(
            select(AIDraftEdit).where(
                AIDraftEdit.user_id == user.id,
                AIDraftEdit.tenant_id == tenant_id,
            )
        )).scalars().all()

        if len(draft_edits) >= 5:
            avg_len = sum(len(d.edited) for d in draft_edits) / len(draft_edits)
            if avg_len < 120:
                preferred_message_length = "short"
            elif avg_len < 300:
                preferred_message_length = "medium"
            else:
                preferred_message_length = "long"

            corpus = " ".join(d.edited for d in draft_edits).lower()
            has_emoji = bool(re.search("[\U0001F300-\U0001FAFF☀-➿]", corpus))
            has_tuteo = bool(re.search(r"\btu\b|\btú\b|\btuyo\b|\bte\b", corpus))
            has_usted = bool(re.search(r"\busted\b|\bsuyo\b|\ble\b", corpus))
            if has_emoji:
                communication_style = "muy_casual"
            elif has_tuteo and not has_usted:
                communication_style = "casual"
            else:
                communication_style = "formal"

        values: dict[str, Any] = {
            "id": uuid.uuid4(),
            "user_id": user.id,
            "tenant_id": tenant_id,
            "total_deals_closed": total_won,
            "total_deals_lost": total_lost,
            "close_rate": close_rate,
            "best_close_day": best_close_day,
            "best_close_hour": best_close_hour,
            "top_performing_stage": top_performing_stage,
            "created_at": now,
            "updated_at": now,
        }
        set_update: dict[str, Any] = {
            "total_deals_closed": values["total_deals_closed"],
            "total_deals_lost": values["total_deals_lost"],
            "close_rate": values["close_rate"],
            "best_close_day": values["best_close_day"],
            "best_close_hour": values["best_close_hour"],
            "top_performing_stage": values["top_performing_stage"],
            "updated_at": values["updated_at"],
        }
        if communication_style is not None:
            values["communication_style"] = communication_style
            set_update["communication_style"] = communication_style
        if preferred_message_length is not None:
            values["preferred_message_length"] = preferred_message_length
            set_update["preferred_message_length"] = preferred_message_length

        stmt = (
            pg_insert(AIUserProfile)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_ai_user_profiles_user_id",
                set_=set_update,
            )
        )
        await db.execute(stmt)
        profiles_upserted += 1

    logger.info("[aprendiz] tenant=%s profiles_upserted=%d", tenant_id, profiles_upserted)
    return profiles_upserted
