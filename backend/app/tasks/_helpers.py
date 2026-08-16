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

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch

logger = logging.getLogger(__name__)


# ── Branch / tenant queries ───────────────────────────────────────────────────
#
# get_active_branch_ids()/get_active_tenant_ids() alimentan los barridos
# periódicos de Celery beat: necesitan ver branches de TODOS los tenants a la
# vez, por diseño — no es un caso "pre-tenant" (una entidad ambigua que se
# resuelve una vez), es cross-tenant PERMANENTE. Por eso usan
# fn_list_active_branch_tenant_pairs() (SECURITY DEFINER, migración
# m8n9o0p1q2r3) en vez de un SELECT directo sobre `branches` (que RLS
# bloquearía por completo bajo walix_app, sin importar qué tenant esté
# seteado — porque necesitan ver MÁS de uno).
#
# IMPORTANTE: esto solo resuelve "quién existe". Cada llamador sigue
# necesitando set_tenant_context(db, tenant_id) antes de leer cualquier otro
# dato de un branch/tenant específico — ver app/tasks/agent_tasks.py y
# app/tasks/metrics_tasks.py.

async def get_active_branch_tenant_pairs() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Returns (branch_id, tenant_id) for every active branch, across ALL tenants."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("SELECT branch_id, tenant_id FROM fn_list_active_branch_tenant_pairs()")
        )
        return [(r.branch_id, r.tenant_id) for r in rows]


async def get_active_branches(db: AsyncSession) -> list[Branch]:
    """Return all active Branch rows (full objects) using an existing session.

    NOTA: sin llamador activo en el repo (verificado 2026-08-15) — si se usa
    en el futuro, el caller debe llamar set_tenant_context(db, tenant_id)
    antes si `db` está scopeada a un tenant (walix_app); esta función en sí
    no filtra por tenant, así que devuelve cross-tenant SOLO si `db` está
    corriendo con un rol que bypassea RLS (ej. la conexión admin).
    """
    result = await db.execute(
        select(Branch).where(Branch.is_active.is_(True))
    )
    return list(result.scalars().all())


async def get_active_branch_ids() -> list[uuid.UUID]:
    """Return IDs of all active branches, opening its own session.

    Use this inside asyncio.run() task bodies where no session exists yet.
    """
    pairs = await get_active_branch_tenant_pairs()
    return [branch_id for branch_id, _ in pairs]


async def get_active_tenant_ids() -> list[uuid.UUID]:
    """Return distinct tenant IDs that have at least one active branch."""
    pairs = await get_active_branch_tenant_pairs()
    return list({tenant_id for _, tenant_id in pairs})


# ── Alert rule queries ─────────────────────────────────────────────────────────
#
# Mismo motivo que arriba: app/tasks/alerts_tasks.py necesita ver alert_rules
# de TODOS los tenants a la vez (run_daily_summaries filtra por hora en
# Python; _async_detect_unresponded las usa todas). alert_rules SÍ tiene RLS
# (a diferencia de ai_memory_events/ai_entity_context/expenses, que no
# tienen ninguna — hallazgo aparte). Usa fn_list_active_alert_rules()
# (SECURITY DEFINER, migración n9o0p1q2r3s4).

class ActiveAlertRule:
    """Plain data holder — evita depender del modelo AlertRule (ORM) para
    algo que ya viene resuelto de una función SQL, no de una query ORM."""

    __slots__ = (
        "id", "branch_id", "tenant_id", "schedule_hour",
        "silence_start", "silence_end", "threshold_hours",
    )

    def __init__(
        self, id, branch_id, tenant_id, schedule_hour,
        silence_start, silence_end, threshold_hours,
    ) -> None:
        self.id = id
        self.branch_id = branch_id
        self.tenant_id = tenant_id
        self.schedule_hour = schedule_hour
        self.silence_start = silence_start
        self.silence_end = silence_end
        self.threshold_hours = threshold_hours


async def get_active_alert_rules() -> list[ActiveAlertRule]:
    """Returns every active AlertRule, across ALL tenants, via the
    SECURITY DEFINER enumeration function."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text("SELECT * FROM fn_list_active_alert_rules()"))
        return [
            ActiveAlertRule(
                id=r.id, branch_id=r.branch_id, tenant_id=r.tenant_id,
                schedule_hour=r.schedule_hour, silence_start=r.silence_start,
                silence_end=r.silence_end, threshold_hours=r.threshold_hours,
            )
            for r in rows
        ]


# ── Async bridge ──────────────────────────────────────────────────────────────

def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a synchronous Celery task.

    Each call creates a fresh event loop via asyncio.run(), which is required
    because the worker uses NullPool — connections are not shared across loops.
    """
    return asyncio.run(coro)
