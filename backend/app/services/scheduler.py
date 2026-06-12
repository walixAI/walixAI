"""FastAPI lifespan — APScheduler removed; jobs run in the Celery worker process.

Periodic tasks are defined in app/celery_app.py (beat_schedule) and executed by
the Celery worker. Start the worker and beat processes separately (see Procfile).

The lifespan_scheduler function is kept so app/main.py needs no changes.
"""

from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan_scheduler(_app):
    # Jobs periódicos corren en proceso Celery separado. Ver app/celery_app.py
    logger.info("scheduler: Celery mode — no in-process scheduler (see Procfile)")
    yield
