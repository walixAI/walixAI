"""Celery application and Beat schedule for Walix background jobs.

Replaces APScheduler (which ran inside the FastAPI process and lost in-flight
jobs on restarts/deploys). Celery+Redis persists job state across process
restarts and supports retries with acknowledgement.

Processes (see Procfile):
  web    — uvicorn (FastAPI, HTTP only, no scheduler)
  worker — celery worker (executes tasks)
  beat   — celery beat (triggers periodic tasks)

Connection pool note:
  Each Celery task calls asyncio.run(), which creates a new event loop.
  asyncpg connections are tied to the event loop that created them, so the
  shared connection pool from app/core/database.py is not safe to reuse
  across asyncio.run() boundaries. The worker_process_init signal below
  replaces AsyncSessionLocal with a NullPool version on worker startup so
  that each asyncio.run() call creates fresh connections.
"""

from __future__ import annotations

from celery import Celery, signals
from celery.schedules import crontab
from datetime import timedelta

from app.core.config import settings


def _async_url(url: str) -> str:
    for old, new in [
        ("postgresql+asyncpg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
    ]:
        if url.startswith(old):
            return new + url[len(old):]
    return url


_redis_url = settings.REDIS_URL

celery_app = Celery(
    "walix",
    broker=_redis_url,
    backend=_redis_url,
    include=[
        "app.tasks.agent_tasks",
        "app.tasks.metrics_tasks",
        "app.tasks.alerts_tasks",
        "app.tasks.dlq_handler",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Mexico_City",
    enable_utc=True,
    task_acks_late=True,            # ACK only after task completes — never lost on restart
    task_reject_on_worker_lost=True,  # Re-queue if the worker process dies mid-task
    worker_prefetch_multiplier=1,   # One task at a time per worker (AI tasks are heavy)
    task_soft_time_limit=300,       # SoftTimeLimitExceeded at 5 min → clean shutdown
    task_time_limit=360,            # Hard kill at 6 min
    result_expires=3600,            # Results in Redis for 1 h
)

# ── Periodic schedule (replaces APScheduler) ──────────────────────────────────

celery_app.conf.beat_schedule = {
    # Proactive agents
    "follow-up-agent-every-2h": {
        "task": "app.tasks.agent_tasks.run_follow_up_all_branches",
        "schedule": crontab(hour="8-20/2", minute=0),
    },
    "pipeline-agent-daily": {
        "task": "app.tasks.agent_tasks.run_pipeline_all_branches",
        "schedule": crontab(hour=7, minute=0),
    },
    "config-agent-weekly": {
        "task": "app.tasks.agent_tasks.run_config_all_branches",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
    "reactivation-agent-weekly": {
        "task": "app.tasks.agent_tasks.run_reactivation_all_tenants",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
    "profile-enrichment-every-72h": {
        "task": "app.tasks.agent_tasks.run_profile_enrichment_all_tenants",
        "schedule": timedelta(hours=72),
    },
    # Metrics
    "aggregate-metrics-hourly": {
        "task": "app.tasks.metrics_tasks.aggregate_all_metrics",
        "schedule": crontab(minute=5),  # :05 past the hour to avoid spike at :00
    },
    "sentiment-daily": {
        "task": "app.tasks.metrics_tasks.calculate_all_sentiment",
        "schedule": crontab(hour=23, minute=0),
    },
    # Alerts
    "daily-summaries-hourly": {
        "task": "app.tasks.alerts_tasks.run_daily_summaries",
        "schedule": crontab(minute=0),
    },
    "detect-unresponded-every-30m": {
        "task": "app.tasks.alerts_tasks.detect_unresponded_leads",
        "schedule": crontab(minute="*/30"),
    },
    "monthly-summaries": {
        "task": "app.tasks.alerts_tasks.run_monthly_summaries",
        "schedule": crontab(day_of_month=1, hour=9, minute=0),
    },
}


# ── Worker process initialization ─────────────────────────────────────────────

@signals.worker_process_init.connect
def _configure_worker_db(**kwargs: object) -> None:
    """Replace AsyncSessionLocal with a NullPool version on each worker process.

    NullPool ensures that each asyncio.run() invocation in a task creates fresh
    DB connections in the new event loop instead of reusing pool connections that
    were bound to a previous (closed) event loop.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.core.database as _db
    from app.core.config import settings

    engine = create_async_engine(
        _async_url(settings.effective_database_url),
        poolclass=NullPool,
    )
    _db.AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
