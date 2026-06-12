"""Celery tasks for metrics aggregation."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, timedelta

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _get_active_branch_ids() -> list[uuid.UUID]:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Branch

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Branch.id).where(Branch.is_active.is_(True)))
        return list(result.scalars().all())


@celery_app.task(
    name="app.tasks.metrics_tasks.aggregate_all_metrics",
    max_retries=3,
    default_retry_delay=60,
)
def aggregate_all_metrics() -> dict:
    """Aggregate daily metrics for yesterday across all active branches."""
    from app.services.metrics_engine import aggregate_daily_metrics
    from app.core.database import AsyncSessionLocal

    target_date = date.today() - timedelta(days=1)

    async def _run() -> dict:
        branch_ids = await _get_active_branch_ids()
        results = {"branches": len(branch_ids), "target_date": str(target_date), "errors": 0}
        for bid in branch_ids:
            try:
                async with AsyncSessionLocal() as db:
                    await aggregate_daily_metrics(bid, target_date, db)
                    await db.commit()
            except Exception:
                logger.exception("aggregate_daily_metrics failed for branch=%s", bid)
                results["errors"] += 1
        return results

    return asyncio.run(_run())


@celery_app.task(
    name="app.tasks.metrics_tasks.calculate_all_sentiment",
    max_retries=3,
    default_retry_delay=120,
)
def calculate_all_sentiment() -> dict:
    """Compute sentiment snapshots for all active branches."""
    from app.services.sentiment_aggregator import calculate_sentiment_snapshot
    from app.core.database import AsyncSessionLocal

    async def _run() -> dict:
        branch_ids = await _get_active_branch_ids()
        results = {"branches": len(branch_ids), "errors": 0}
        for bid in branch_ids:
            try:
                async with AsyncSessionLocal() as db:
                    await calculate_sentiment_snapshot(bid, db)
                    await db.commit()
            except Exception:
                logger.exception("calculate_sentiment_snapshot failed for branch=%s", bid)
                results["errors"] += 1
        return results

    return asyncio.run(_run())
