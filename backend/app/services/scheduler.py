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
    logger.info("scheduler: 3 jobs registered")


@asynccontextmanager
async def lifespan_scheduler(_app):
    """FastAPI lifespan context that starts and stops APScheduler."""
    _register_jobs()
    scheduler.start()
    logger.info("scheduler: APScheduler started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("scheduler: APScheduler stopped")
