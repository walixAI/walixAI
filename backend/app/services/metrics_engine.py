"""Daily metrics aggregation engine for Walix.

aggregate_daily_metrics(branch_id, target_date, db) computes all KPIs for a
single branch/day and UPSERTS the result into daily_metrics.
"""
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityType, LeadActivity
from app.models.conversation import Conversation, Message, MessageRole
from app.models.lead import Lead, LeadStatus
from app.models.metrics import DailyMetric
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch

logger = logging.getLogger(__name__)

_TERMINAL = [LeadStatus.PERDIDO, LeadStatus.CALIFICADO]


async def aggregate_daily_metrics(
    branch_id: uuid.UUID,
    target_date: date,
    db: AsyncSession,
) -> DailyMetric:
    """Compute KPIs for branch on target_date and UPSERT into daily_metrics.

    Does NOT commit — caller is responsible for committing.
    """
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")

    day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    # ── 1. leads_created ─────────────────────────────────────────────────────
    leads_created = await _count(
        db,
        select(func.count(Lead.id)).where(
            Lead.branch_id == branch_id,
            Lead.created_at >= day_start,
            Lead.created_at < day_end,
        ),
    )

    # ── 2. leads_qualified (STATUS_CHANGE → CALIFICADO) ───────────────────────
    qualified_result = await db.execute(
        select(func.count(LeadActivity.id))
        .join(Lead, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            LeadActivity.activity_type == ActivityType.STATUS_CHANGE.value,
            LeadActivity.created_at >= day_start,
            LeadActivity.created_at < day_end,
            LeadActivity.payload["to"].astext == LeadStatus.CALIFICADO.value,
        )
    )
    leads_qualified = qualified_result.scalar_one() or 0

    # ── 3. leads_won / leads_lost (STAGE_CHANGE to terminal stages) ───────────
    stage_payloads_result = await db.execute(
        select(LeadActivity.payload)
        .join(Lead, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            LeadActivity.activity_type == ActivityType.STAGE_CHANGE.value,
            LeadActivity.created_at >= day_start,
            LeadActivity.created_at < day_end,
            LeadActivity.payload.isnot(None),
        )
    )
    to_stage_ids: list[str] = []
    for (payload,) in stage_payloads_result.fetchall():
        sid = (payload or {}).get("to_stage_id")
        if sid:
            to_stage_ids.append(sid)

    leads_won = 0
    leads_lost = 0
    if to_stage_ids:
        stages_result = await db.execute(
            select(PipelineStage).where(
                PipelineStage.id.in_([uuid.UUID(s) for s in to_stage_ids])
            )
        )
        stage_by_id = {str(s.id): s for s in stages_result.scalars().all()}
        for sid in to_stage_ids:
            s = stage_by_id.get(sid)
            if s:
                if s.is_won:
                    leads_won += 1
                elif s.is_lost:
                    leads_lost += 1

    # ── 4. messages_sent / messages_received ─────────────────────────────────
    messages_sent = await _count(
        db,
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.branch_id == branch_id,
            Message.role == MessageRole.ASSISTANT.value,
            Message.created_at >= day_start,
            Message.created_at < day_end,
        ),
    )
    messages_received = await _count(
        db,
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.branch_id == branch_id,
            Message.role == MessageRole.USER.value,
            Message.created_at >= day_start,
            Message.created_at < day_end,
        ),
    )

    # ── 5. calls_logged ───────────────────────────────────────────────────────
    calls_logged = await _count(
        db,
        select(func.count(LeadActivity.id))
        .join(Lead, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            LeadActivity.activity_type == ActivityType.CALL.value,
            LeadActivity.created_at >= day_start,
            LeadActivity.created_at < day_end,
        ),
    )

    # ── 6. tasks_completed (payload->>'completed' = 'true') ──────────────────
    tasks_completed = await _count(
        db,
        select(func.count(LeadActivity.id))
        .join(Lead, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            LeadActivity.activity_type == ActivityType.TASK.value,
            LeadActivity.created_at >= day_start,
            LeadActivity.created_at < day_end,
            LeadActivity.payload["completed"].astext == "true",
        ),
    )

    # ── 7. quotes_sent ────────────────────────────────────────────────────────
    quotes_sent = await _count(
        db,
        select(func.count(LeadActivity.id))
        .join(Lead, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            LeadActivity.activity_type == ActivityType.QUOTE.value,
            LeadActivity.created_at >= day_start,
            LeadActivity.created_at < day_end,
        ),
    )

    # ── 8. avg_first_response_sec ─────────────────────────────────────────────
    avg_first_response = await _compute_avg_first_response(
        db, branch_id, day_start, day_end
    )

    # ── 9. metrics_by_agent ───────────────────────────────────────────────────
    metrics_by_agent = await _compute_by_agent(db, branch_id, day_start, day_end)

    # ── 10. UPSERT ────────────────────────────────────────────────────────────
    existing = await db.execute(
        select(DailyMetric).where(
            DailyMetric.branch_id == branch_id,
            DailyMetric.metric_date == target_date,
        )
    )
    metric = existing.scalar_one_or_none()
    if metric is None:
        metric = DailyMetric(
            branch_id=branch_id,
            tenant_id=branch.tenant_id,
            metric_date=target_date,
        )
        db.add(metric)

    metric.leads_created = leads_created
    metric.leads_qualified = leads_qualified
    metric.leads_won = leads_won
    metric.leads_lost = leads_lost
    metric.messages_sent = messages_sent
    metric.messages_received = messages_received
    metric.calls_logged = calls_logged
    metric.tasks_completed = tasks_completed
    metric.quotes_sent = quotes_sent
    metric.avg_first_response_sec = avg_first_response
    metric.metrics_by_agent = metrics_by_agent

    await db.flush()
    logger.info(
        "metrics_engine: branch=%s date=%s leads_created=%d messages_sent=%d",
        branch_id, target_date, leads_created, messages_sent,
    )
    return metric


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _count(db: AsyncSession, query) -> int:
    result = await db.execute(query)
    return result.scalar_one() or 0


async def _compute_avg_first_response(
    db: AsyncSession,
    branch_id: uuid.UUID,
    day_start: datetime,
    day_end: datetime,
) -> int:
    # First user message per conversation (batch)
    first_user_q = await db.execute(
        select(Message.conversation_id, func.min(Message.created_at).label("ts"))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.branch_id == branch_id,
            Conversation.started_at >= day_start,
            Conversation.started_at < day_end,
            Message.role == MessageRole.USER.value,
        )
        .group_by(Message.conversation_id)
    )
    first_user: dict[uuid.UUID, datetime] = {r[0]: r[1] for r in first_user_q.fetchall()}
    if not first_user:
        return 0

    # First assistant message per conversation (batch)
    first_assist_q = await db.execute(
        select(Message.conversation_id, func.min(Message.created_at).label("ts"))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.branch_id == branch_id,
            Conversation.started_at >= day_start,
            Conversation.started_at < day_end,
            Message.role == MessageRole.ASSISTANT.value,
        )
        .group_by(Message.conversation_id)
    )
    first_assist: dict[uuid.UUID, datetime] = {r[0]: r[1] for r in first_assist_q.fetchall()}

    deltas: list[float] = []
    for conv_id, user_ts in first_user.items():
        assist_ts = first_assist.get(conv_id)
        if assist_ts:
            u = user_ts if user_ts.tzinfo else user_ts.replace(tzinfo=timezone.utc)
            a = assist_ts if assist_ts.tzinfo else assist_ts.replace(tzinfo=timezone.utc)
            if a > u:
                diff = (a - u).total_seconds()
                if 0 < diff < 3600:  # ignore outliers > 1h
                    deltas.append(diff)

    return int(sum(deltas) / len(deltas)) if deltas else 0


async def _compute_by_agent(
    db: AsyncSession,
    branch_id: uuid.UUID,
    day_start: datetime,
    day_end: datetime,
) -> dict[str, Any]:
    # leads_created per agent
    leads_by_agent_q = await db.execute(
        select(Lead.assigned_to, func.count(Lead.id))
        .where(
            Lead.branch_id == branch_id,
            Lead.created_at >= day_start,
            Lead.created_at < day_end,
            Lead.assigned_to.isnot(None),
        )
        .group_by(Lead.assigned_to)
    )
    result: dict[str, Any] = {}
    for assigned_to, count in leads_by_agent_q.fetchall():
        result[str(assigned_to)] = {"leads_created": count}

    # calls per agent
    calls_q = await db.execute(
        select(Lead.assigned_to, func.count(LeadActivity.id))
        .join(LeadActivity, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            Lead.assigned_to.isnot(None),
            LeadActivity.activity_type == ActivityType.CALL.value,
            LeadActivity.created_at >= day_start,
            LeadActivity.created_at < day_end,
        )
        .group_by(Lead.assigned_to)
    )
    for assigned_to, count in calls_q.fetchall():
        result.setdefault(str(assigned_to), {})["calls_logged"] = count

    # tasks_completed per agent
    tasks_q = await db.execute(
        select(Lead.assigned_to, func.count(LeadActivity.id))
        .join(LeadActivity, LeadActivity.lead_id == Lead.id)
        .where(
            Lead.branch_id == branch_id,
            Lead.assigned_to.isnot(None),
            LeadActivity.activity_type == ActivityType.TASK.value,
            LeadActivity.payload["completed"].astext == "true",
            LeadActivity.created_at >= day_start,
            LeadActivity.created_at < day_end,
        )
        .group_by(Lead.assigned_to)
    )
    for assigned_to, count in tasks_q.fetchall():
        result.setdefault(str(assigned_to), {})["tasks_completed"] = count

    return result
