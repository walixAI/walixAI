"""APScheduler setup for Walix proactive alerts.

Jobs:
  daily_summaries    — every hour; fires send_daily_summary for branches whose
                       alert_rule.schedule_hour matches the current MX hour
  detect_unresponded — every 30 minutes; finds leads exceeding threshold_hours
                       with no recent alert and sends send_no_response_alert
  monthly_summaries  — 1st of each month at 9 AM MX time
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import or_, select
from zoneinfo import ZoneInfo

from app.core.database import AsyncSessionLocal
from app.models.alert import AlertRule
from app.models.lead import Lead, LeadStatus
from app.models.tenant import Branch
from app.agents.config_agent import run_config_agent
from app.agents.follow_up_agent import run_follow_up_agent
from app.agents.pipeline_agent import run_pipeline_agent
from app.services.metrics_engine import aggregate_daily_metrics
from app.services.sentiment_aggregator import calculate_sentiment_snapshot
from app.services.alert_generator import (
    _in_silence_window,
    send_daily_summary,
    send_monthly_summary,
    send_no_response_alert,
)

logger = logging.getLogger(__name__)

MX_TZ = ZoneInfo("America/Mexico_City")

scheduler = AsyncIOScheduler(timezone=MX_TZ)

# ── Job implementations ───────────────────────────────────────────────────────


async def _job_daily_summaries() -> None:
    """Hourly: send daily summary to branches whose schedule_hour matches now."""
    current_hour = datetime.now(MX_TZ).hour
    logger.info("scheduler: daily_summaries tick — hour=%d", current_hour)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AlertRule).where(
                    AlertRule.is_active.is_(True),
                    AlertRule.schedule_hour == current_hour,
                )
            )
            rules = result.scalars().all()

        for rule in rules:
            try:
                await send_daily_summary(rule.branch_id)
            except Exception:
                logger.exception(
                    "scheduler: daily_summaries failed for branch=%s", rule.branch_id
                )
    except Exception:
        logger.exception("scheduler: daily_summaries job error")


async def _job_detect_unresponded() -> None:
    """Every 30 min: alert assigned users about leads that exceed threshold_hours."""
    now = datetime.now(timezone.utc)
    alert_cooldown = now - timedelta(hours=4)
    logger.info("scheduler: detect_unresponded tick — now=%s", now.isoformat())
    try:
        async with AsyncSessionLocal() as db:
            rules_result = await db.execute(
                select(AlertRule).where(AlertRule.is_active.is_(True))
            )
            rules = rules_result.scalars().all()

        for rule in rules:
            # Skip if inside silence window
            if _in_silence_window(rule.silence_start, rule.silence_end):
                continue

            threshold_time = now - timedelta(hours=rule.threshold_hours)

            try:
                async with AsyncSessionLocal() as db:
                    leads_result = await db.execute(
                        select(Lead).where(
                            Lead.branch_id == rule.branch_id,
                            # Exclude terminal statuses
                            Lead.status.notin_(
                                [LeadStatus.PERDIDO, LeadStatus.CALIFICADO]
                            ),
                            # Last activity older than threshold
                            Lead.updated_at < threshold_time,
                            # Alert cooldown: not alerted recently
                            or_(
                                Lead.last_alert_at.is_(None),
                                Lead.last_alert_at < alert_cooldown,
                            ),
                        ).limit(10)  # cap to avoid thundering-herd
                    )
                    leads = leads_result.scalars().all()
                    lead_ids = [lead.id for lead in leads]

                for lead_id in lead_ids:
                    try:
                        await send_no_response_alert(lead_id, rule.id)
                    except Exception:
                        logger.exception(
                            "scheduler: no_response_alert failed lead=%s", lead_id
                        )
            except Exception:
                logger.exception(
                    "scheduler: detect_unresponded failed for rule=%s", rule.id
                )
    except Exception:
        logger.exception("scheduler: detect_unresponded job error")


async def _job_follow_up_agent() -> None:
    """Every 2h (8–20): suggest follow-ups for leads inactive >24h across all active branches."""
    logger.info("scheduler: follow_up_agent tick")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Branch).where(Branch.is_active.is_(True)))
            branch_ids = [b.id for b in result.scalars().all()]
        for branch_id in branch_ids:
            try:
                await run_follow_up_agent(branch_id)
            except Exception:
                logger.exception("scheduler: follow_up_agent failed branch=%s", branch_id)
    except Exception:
        logger.exception("scheduler: follow_up_agent job error")


async def _job_pipeline_agent() -> None:
    """Daily at 7 AM MX: analyze pipeline health and suggest corrective actions."""
    logger.info("scheduler: pipeline_agent tick")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Branch).where(Branch.is_active.is_(True)))
            branch_ids = [b.id for b in result.scalars().all()]
        for branch_id in branch_ids:
            try:
                await run_pipeline_agent(branch_id)
            except Exception:
                logger.exception("scheduler: pipeline_agent failed branch=%s", branch_id)
    except Exception:
        logger.exception("scheduler: pipeline_agent job error")


async def _job_config_agent() -> None:
    """Every Monday at 8 AM MX: detect inactive stages and suggest pipeline cleanup."""
    logger.info("scheduler: config_agent tick")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Branch).where(Branch.is_active.is_(True)))
            branch_ids = [b.id for b in result.scalars().all()]
        for branch_id in branch_ids:
            try:
                await run_config_agent(branch_id)
            except Exception:
                logger.exception("scheduler: config_agent failed branch=%s", branch_id)
    except Exception:
        logger.exception("scheduler: config_agent job error")


async def _job_aggregate_metrics() -> None:
    """Hourly: aggregate daily metrics for yesterday across all active branches."""
    from datetime import date, timedelta
    target_date = date.today() - timedelta(days=1)
    logger.info("scheduler: aggregate_metrics tick — target_date=%s", target_date)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Branch).where(Branch.is_active.is_(True)))
            branch_ids = [b.id for b in result.scalars().all()]
        for branch_id in branch_ids:
            try:
                async with AsyncSessionLocal() as db:
                    await aggregate_daily_metrics(branch_id, target_date, db)
                    await db.commit()
            except Exception:
                logger.exception("scheduler: aggregate_metrics failed branch=%s", branch_id)
    except Exception:
        logger.exception("scheduler: aggregate_metrics job error")


async def _job_calculate_sentiment() -> None:
    """Daily at 23:00 MX: compute sentiment snapshots for all active branches."""
    logger.info("scheduler: calculate_sentiment tick")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Branch).where(Branch.is_active.is_(True)))
            branch_ids = [b.id for b in result.scalars().all()]
        for branch_id in branch_ids:
            try:
                async with AsyncSessionLocal() as db:
                    await calculate_sentiment_snapshot(branch_id, db)
                    await db.commit()
            except Exception:
                logger.exception("scheduler: calculate_sentiment failed branch=%s", branch_id)
    except Exception:
        logger.exception("scheduler: calculate_sentiment job error")


async def _job_monthly_summaries() -> None:
    """1st of each month at 9 AM MX: send monthly summary to all active branches."""
    logger.info("scheduler: monthly_summaries tick")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Branch).where(Branch.is_active.is_(True))
            )
            branches = result.scalars().all()
            branch_ids = [b.id for b in branches]

        for branch_id in branch_ids:
            try:
                await send_monthly_summary(branch_id)
            except Exception:
                logger.exception(
                    "scheduler: monthly_summaries failed for branch=%s", branch_id
                )
    except Exception:
        logger.exception("scheduler: monthly_summaries job error")


# ── Scheduler setup ───────────────────────────────────────────────────────────


def _register_jobs() -> None:
    """Registers all APScheduler jobs (idempotent)."""
    scheduler.add_job(
        _job_daily_summaries,
        IntervalTrigger(hours=1),
        id="daily_summaries",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _job_detect_unresponded,
        IntervalTrigger(minutes=30),
        id="detect_unresponded",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.add_job(
        _job_monthly_summaries,
        CronTrigger(day=1, hour=9, minute=0, timezone=MX_TZ),
        id="monthly_summaries",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Sprint 6: metrics aggregation
    scheduler.add_job(
        _job_aggregate_metrics,
        CronTrigger(minute=0),
        id="aggregate_metrics",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _job_calculate_sentiment,
        CronTrigger(hour=23, minute=0, timezone=MX_TZ),
        id="calculate_sentiment",
        replace_existing=True,
        misfire_grace_time=600,
    )
    # Sprint 6: proactive agents
    scheduler.add_job(
        _job_follow_up_agent,
        CronTrigger(hour="8-20", minute=0, timezone=MX_TZ),
        id="follow_up_agent",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _job_pipeline_agent,
        CronTrigger(hour=7, minute=0, timezone=MX_TZ),
        id="pipeline_agent",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _job_config_agent,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=MX_TZ),
        id="config_agent",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("scheduler: 8 jobs registered")


@asynccontextmanager
async def lifespan_scheduler(_app):
    """FastAPI lifespan context that starts and stops APScheduler."""
    _register_jobs()
    scheduler.start()
    logger.info("scheduler: APScheduler started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("scheduler: APScheduler stopped")
