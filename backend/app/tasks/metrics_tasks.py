"""Celery tasks for metrics aggregation and sentiment snapshots.

Both services (metrics_engine, sentiment_aggregator) flush internally but do
NOT commit — the caller must commit. Each branch runs in its own session so a
failure on one branch never rolls back another.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.celery_app import celery_app
from app.core import database as _database
from app.core.database import set_tenant_context
from app.tasks._helpers import get_active_branch_tenant_pairs, run_async

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.metrics_tasks.aggregate_all_metrics",
    max_retries=3,
    default_retry_delay=60,
)
def aggregate_all_metrics() -> dict:
    """Aggregate daily KPIs for yesterday across all active branches.

    Targets yesterday (not today) because metrics are only meaningful for
    completed calendar days. Signature:
      aggregate_daily_metrics(branch_id, target_date, db) -> DailyMetric
    """
    from app.services.metrics_engine import aggregate_daily_metrics

    target_date = date.today() - timedelta(days=1)

    async def _run() -> dict:
        pairs = await get_active_branch_tenant_pairs()
        results = {
            "branches": len(pairs),
            "target_date": str(target_date),
            "errors": 0,
        }
        logger.info("[metrics] aggregating for %d branches, date=%s", len(pairs), target_date)

        for bid, tid in pairs:
            try:
                async with _database.AsyncSessionLocal() as db:
                    # daily_metrics tiene RLS desde h4i5j6k7l8m9.
                    await set_tenant_context(db, tid)
                    await aggregate_daily_metrics(bid, target_date, db)
                    await db.commit()
            except Exception:
                logger.exception("[metrics] branch %s failed", bid)
                results["errors"] += 1

        return results

    return run_async(_run())


@celery_app.task(
    name="app.tasks.metrics_tasks.calculate_all_sentiment",
    max_retries=3,
    default_retry_delay=120,
)
def calculate_all_sentiment() -> dict:
    """Compute daily sentiment snapshots for all active branches.

    Signature: calculate_sentiment_snapshot(branch_id, db) -> SentimentSnapshot
    Does NOT commit internally — committed here after each branch.
    """
    from app.services.sentiment_aggregator import calculate_sentiment_snapshot

    async def _run() -> dict:
        pairs = await get_active_branch_tenant_pairs()
        results = {"branches": len(pairs), "errors": 0}
        logger.info("[sentiment] computing for %d branches", len(pairs))

        for bid, tid in pairs:
            try:
                async with _database.AsyncSessionLocal() as db:
                    # sentiment_snapshots tiene RLS desde h4i5j6k7l8m9.
                    await set_tenant_context(db, tid)
                    await calculate_sentiment_snapshot(bid, db)
                    await db.commit()
            except Exception:
                logger.exception("[sentiment] branch %s failed", bid)
                results["errors"] += 1

        return results

    return run_async(_run())
