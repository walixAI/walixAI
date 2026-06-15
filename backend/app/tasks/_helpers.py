"""Shared helpers for Celery task modules.

Centralizes repeated async DB helpers and the asyncio.run() wrapper so
agent_tasks, metrics_tasks, and alerts_tasks don't duplicate them.

Import note:
  Branch lives in app.models.tenant (not app.models.branch).
  Use .is_(True) for boolean SQLAlchemy filters — avoids the "== True"
  ambiguity warning and matches the project's existing style.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Coroutine

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch

logger = logging.getLogger(__name__)


# ── Branch / tenant queries ───────────────────────────────────────────────────

async def get_active_branches(db: AsyncSession) -> list[Branch]:
    """Return all active Branch rows (full objects) using an existing session."""
    result = await db.execute(
        select(Branch).where(Branch.is_active.is_(True))
    )
    return list(result.scalars().all())


async def get_active_branch_ids() -> list[uuid.UUID]:
    """Return IDs of all active branches, opening its own session.

    Use this inside asyncio.run() task bodies where no session exists yet.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Branch.id).where(Branch.is_active.is_(True))
        )
        return list(result.scalars().all())


async def get_active_tenant_ids() -> list[uuid.UUID]:
    """Return distinct tenant IDs that have at least one active branch."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Branch.tenant_id)
            .where(Branch.is_active.is_(True))
            .distinct()
        )
        return list(result.scalars().all())


# ── Async bridge ──────────────────────────────────────────────────────────────

def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a synchronous Celery task.

    Each call creates a fresh event loop via asyncio.run(), which is required
    because the worker uses NullPool — connections are not shared across loops.
    """
    return asyncio.run(coro)
