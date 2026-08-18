"""Dead-letter queue: persists exhausted-retry tasks to the DB for manual review.

Wired via the task_failure Celery signal. No explicit retry-count check is
needed because Celery only fires task_failure when:
  - A task raises an exception directly (no self.retry())
  - A task calls self.retry() but has exhausted all retries (MaxRetriesExceededError)
Intermediate retries raise celery.exceptions.Retry, which the worker catches
and re-enqueues without firing task_failure.

The signal stays here (not in celery_app.py) to avoid a circular import:
  celery_app.py → dlq_handler → celery_app.py

Monitor failures:
  SELECT * FROM failed_tasks ORDER BY created_at DESC;
"""

from __future__ import annotations

import logging

from celery import signals
from sqlalchemy import text

from app.celery_app import celery_app
from app.core import database as _database
from app.tasks._helpers import run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.dlq_handler.handle_failed_task")
def handle_failed_task(task_id: str, task_name: str, error: str) -> None:
    """Persist a task failure record to failed_tasks for manual review.

    Uses ON CONFLICT DO NOTHING to preserve the first error seen for a given
    task_id and avoid overwriting it with a duplicate DLQ entry.
    created_at is omitted — the column has server_default=now().
    """
    async def _run() -> None:
        async with _database.AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO failed_tasks (id, task_id, task_name, error)"
                    " VALUES (gen_random_uuid(), :tid, :name, :err)"
                    " ON CONFLICT (task_id) DO NOTHING"
                ),
                {"tid": task_id, "name": task_name, "err": error},
            )
            await db.commit()

    try:
        run_async(_run())
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
    """Forward task failures to the DLQ handler.

    Fires after all retries are exhausted (or immediately for non-retried tasks).
    No manual retry-count check needed — Celery's task_failure signal already
    excludes intermediate retries.
    """
    task_name = getattr(sender, "name", "unknown") if sender else "unknown"
    error_msg = f"{type(exception).__name__}: {exception}"

    logger.warning("dlq: queueing failed task task_id=%s task_name=%s", task_id, task_name)

    handle_failed_task.apply_async(
        args=[task_id, task_name, error_msg],
        countdown=0,
    )
