"""Celery tasks for finance automation (recurring expense generation)."""
from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.finance_tasks.run_generate_recurring_expenses")
def run_generate_recurring_expenses() -> dict:
    """Generate this month's recurring expenses for all tenants (runs on day 1)."""
    from app.core.database import AsyncSessionLocal
    from app.services.expense_generation import generate_recurring_expenses

    async def _run() -> dict:
        async with AsyncSessionLocal() as db:
            count = await generate_recurring_expenses(tenant_id=None, db=db)
        return {"generated": count}

    return asyncio.run(_run())
