"""Celery tasks for alert delivery (daily summaries, unresponded leads, monthly)."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.alerts_tasks.run_daily_summaries")
def run_daily_summaries() -> dict:
    """Send daily summary to branches whose alert rule schedule_hour matches the current MX hour."""
    from zoneinfo import ZoneInfo
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.alert import AlertRule
    from app.services.alert_generator import send_daily_summary

    MX_TZ = ZoneInfo("America/Mexico_City")

    async def _run() -> dict:
        current_hour = datetime.now(MX_TZ).hour
        results = {"hour": current_hour, "sent": 0, "errors": 0}
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
                results["sent"] += 1
            except Exception:
                logger.exception("daily_summary failed for branch=%s", rule.branch_id)
                results["errors"] += 1
        return results

    return asyncio.run(_run())


async def _async_detect_unresponded() -> dict:
    """Async core of detect_unresponded_leads — importable for tests/scripts."""
    from sqlalchemy import or_, select
    from app.core.database import AsyncSessionLocal
    from app.models.alert import AlertRule
    from app.models.lead import Lead, LeadStatus
    from app.services.alert_generator import _in_silence_window, send_no_response_alert

    now = datetime.now(timezone.utc)
    alert_cooldown = now - timedelta(hours=4)
    results = {"alerts_sent": 0, "errors": 0}

    async with AsyncSessionLocal() as db:
        rules_result = await db.execute(
            select(AlertRule).where(AlertRule.is_active.is_(True))
        )
        rules = rules_result.scalars().all()

    for rule in rules:
        if _in_silence_window(rule.silence_start, rule.silence_end):
            continue
        threshold_time = now - timedelta(hours=rule.threshold_hours)
        try:
            async with AsyncSessionLocal() as db:
                leads_result = await db.execute(
                    select(Lead).where(
                        Lead.branch_id == rule.branch_id,
                        Lead.status.notin_([LeadStatus.PERDIDO, LeadStatus.CALIFICADO]),
                        Lead.updated_at < threshold_time,
                        or_(
                            Lead.last_alert_at.is_(None),
                            Lead.last_alert_at < alert_cooldown,
                        ),
                    ).limit(10)
                )
                lead_ids = [lead.id for lead in leads_result.scalars().all()]

            for lead_id in lead_ids:
                try:
                    await send_no_response_alert(lead_id, rule.id)
                    results["alerts_sent"] += 1
                except Exception:
                    logger.exception("no_response_alert failed lead=%s", lead_id)
                    results["errors"] += 1
        except Exception:
            logger.exception("detect_unresponded failed for rule=%s", rule.id)
            results["errors"] += 1
    return results


@celery_app.task(name="app.tasks.alerts_tasks.detect_unresponded_leads")
def detect_unresponded_leads() -> dict:
    """Alert assigned users about leads that have exceeded their no-response threshold."""
    return asyncio.run(_async_detect_unresponded())


@celery_app.task(name="app.tasks.alerts_tasks.run_monthly_summaries")
def run_monthly_summaries() -> dict:
    """Send monthly summaries to all active branches (runs on 1st of each month)."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Branch
    from app.services.alert_generator import send_monthly_summary

    async def _run() -> dict:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Branch).where(Branch.is_active.is_(True)))
            branch_ids = [b.id for b in result.scalars().all()]

        results = {"branches": len(branch_ids), "sent": 0, "errors": 0}
        for bid in branch_ids:
            try:
                await send_monthly_summary(bid)
                results["sent"] += 1
            except Exception:
                logger.exception("monthly_summary failed for branch=%s", bid)
                results["errors"] += 1
        return results

    return asyncio.run(_run())
