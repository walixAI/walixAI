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
    from app.services.alert_generator import send_daily_summary
    from app.tasks._helpers import get_active_alert_rules

    MX_TZ = ZoneInfo("America/Mexico_City")

    async def _run() -> dict:
        current_hour = datetime.now(MX_TZ).hour
        results = {"hour": current_hour, "sent": 0, "errors": 0}

        # get_active_alert_rules() cruza tenants a propósito (SECURITY
        # DEFINER) — el filtro por hora se hace acá, en Python, no en la
        # función SQL (una sola función sirve a este task y a
        # detect_unresponded_leads, que necesita TODAS las reglas).
        rules = [r for r in await get_active_alert_rules() if r.schedule_hour == current_hour]

        for rule in rules:
            try:
                await send_daily_summary(rule.branch_id, rule.tenant_id)
                results["sent"] += 1
            except Exception:
                logger.exception("daily_summary failed for branch=%s", rule.branch_id)
                results["errors"] += 1
        return results

    return asyncio.run(_run())


async def _async_detect_unresponded() -> dict:
    """Async core of detect_unresponded_leads — importable for tests/scripts."""
    from sqlalchemy import or_, select
    from app.core.database import AsyncSessionLocal, set_tenant_context
    from app.models.lead import Lead, LeadStatus
    from app.services.alert_generator import _in_silence_window, send_no_response_alert
    from app.tasks._helpers import get_active_alert_rules

    now = datetime.now(timezone.utc)
    alert_cooldown = now - timedelta(hours=4)
    results = {"alerts_sent": 0, "errors": 0}

    rules = await get_active_alert_rules()

    for rule in rules:
        if _in_silence_window(rule.silence_start, rule.silence_end):
            continue
        threshold_time = now - timedelta(hours=rule.threshold_hours)
        try:
            async with AsyncSessionLocal() as db:
                # Sesión nueva por rule — leads tiene RLS, y branch_id por sí
                # solo no alcanza para leerla sin tenant_id (que acá SÍ
                # tenemos, vía get_active_alert_rules()).
                await set_tenant_context(db, rule.tenant_id)
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
                    await send_no_response_alert(lead_id, rule.id, rule.tenant_id)
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
    from app.services.alert_generator import send_monthly_summary
    from app.tasks._helpers import get_active_branch_tenant_pairs

    async def _run() -> dict:
        pairs = await get_active_branch_tenant_pairs()
        results = {"branches": len(pairs), "sent": 0, "errors": 0}
        for bid, tid in pairs:
            try:
                await send_monthly_summary(bid, tid)
                results["sent"] += 1
            except Exception:
                logger.exception("monthly_summary failed for branch=%s", bid)
                results["errors"] += 1
        return results

    return asyncio.run(_run())
