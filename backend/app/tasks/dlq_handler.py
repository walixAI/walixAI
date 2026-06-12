"""Dead-letter queue: persists failed tasks to the DB for manual review.

Wired via the task_failure Celery signal so every task failure (not just those
with explicit link_error) is captured. The table is:

    failed_tasks(id, task_id, task_name, error, created_at)

Use SELECT * FROM failed_tasks ORDER BY created_at DESC in Railway SQL console
to monitor production failures.
"""
from __future__ import annotations

import asyncio
import logging

from celery import signals

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.dlq_handler.handle_failed_task")
def handle_failed_task(task_id: str, task_name: str, error: str) -> None:
    """Persist a task failure record to the DB."""
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO failed_tasks (task_id, task_name, error)"
                    " VALUES (:tid, :name, :err)"
                    " ON CONFLICT (task_id) DO UPDATE SET error = EXCLUDED.error"
                ),
                {"tid": task_id, "name": task_name, "err": error},
            )
            await db.commit()

    try:
        asyncio.run(_run())
    except Exception:
        logger.exception("dlq: could not persist failure for task_id=%s", task_id)


@signals.task_failure.connect
def _on_task_failure(
    task_id: str,
    exception: Exception,
    args: tuple,
    kwargs: dict,
    traceback: object,
    einfo: object,
    sender: object = None,
    **kw: object,
) -> None:
    """Forward every task failure to the DLQ handler."""
    task_name = getattr(sender, "name", "unknown") if sender else "unknown"
    handle_failed_task.apply_async(
        args=[task_id, task_name, f"{type(exception).__name__}: {exception}"],
        # Low priority — don't block the worker
        countdown=0,
    )
