"""Celery tasks for Walix proactive agents.

Each task wraps an async agent function with asyncio.run(). The NullPool
session factory (patched in by celery_app.worker_process_init) ensures fresh
DB connections per asyncio.run() call.

Session ownership rules (derived from agent signatures):
  run_follow_up_agent(branch_id, tenant_id)   — agent opens its own session
  run_pipeline_agent(branch_id, tenant_id)    — agent opens its own session
  run_config_agent(branch_id, tenant_id)      — agent opens its own session
  run_closing_agent(lead_id, tenant_id)       — agent opens its own session
  run_reactivation_agent(tenant_id, db)    — caller must supply session
  run_profile_enrichment_agent(tenant_id, db) — caller must supply session
  execute_suggestion(suggestion_id: UUID, db) — caller must supply session

tenant_id ahora es obligatorio en los agentes por-branch porque cada uno
abre su propia sesión con AsyncSessionLocal() y necesita
set_tenant_context(db, tenant_id) antes de la primera query — bajo RLS real
(walix_app, sin BYPASSRLS) ninguna query contra una tabla protegida ve filas
sin ese contexto. branch_id/tenant_id se obtienen juntos de
get_active_branch_tenant_pairs() (app/tasks/_helpers.py), que a su vez usa
fn_list_active_branch_tenant_pairs() (SECURITY DEFINER, migración
m8n9o0p1q2r3) porque enumerar branches activas cruza tenants a propósito —
ningún set_tenant_context() de un solo tenant puede resolver esa query.
"""

from __future__ import annotations

import logging
import uuid

from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.tasks._helpers import (
    get_active_branch_tenant_pairs,
    get_active_tenant_ids,
    run_async,
)

logger = logging.getLogger(__name__)


# ── Per-branch agents (each manages its own DB session) ───────────────────────

@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_follow_up_all_branches",
    max_retries=3,
    default_retry_delay=120,
)
def run_follow_up_all_branches(self) -> dict:
    """Run the follow-up agent for every active branch."""
    from app.agents.follow_up_agent import run_follow_up_agent

    async def _run() -> dict:
        pairs = await get_active_branch_tenant_pairs()
        results = {"branches": len(pairs), "suggestions_created": 0, "errors": 0}
        logger.info("[follow_up] running for %d branches", len(pairs))
        for bid, tid in pairs:
            try:
                count = await run_follow_up_agent(bid, tid)
                results["suggestions_created"] += count or 0
            except Exception:
                logger.exception("[follow_up] branch %s failed", bid)
                results["errors"] += 1
        return results

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_pipeline_all_branches",
    max_retries=3,
    default_retry_delay=120,
)
def run_pipeline_all_branches(self) -> dict:
    """Run the pipeline health agent for every active branch."""
    from app.agents.pipeline_agent import run_pipeline_agent

    async def _run() -> dict:
        pairs = await get_active_branch_tenant_pairs()
        results = {"branches": len(pairs), "suggestions_created": 0, "errors": 0}
        logger.info("[pipeline] running for %d branches", len(pairs))
        for bid, tid in pairs:
            try:
                created = await run_pipeline_agent(bid, tid)
                results["suggestions_created"] += int(bool(created))
            except Exception:
                logger.exception("[pipeline] branch %s failed", bid)
                results["errors"] += 1
        return results

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_config_all_branches",
    max_retries=3,
    default_retry_delay=120,
)
def run_config_all_branches(self) -> dict:
    """Run the pipeline config agent for every active branch (weekly)."""
    from app.agents.config_agent import run_config_agent

    async def _run() -> dict:
        pairs = await get_active_branch_tenant_pairs()
        results = {"branches": len(pairs), "suggestions_created": 0, "errors": 0}
        logger.info("[config] running for %d branches", len(pairs))
        for bid, tid in pairs:
            try:
                created = await run_config_agent(bid, tid)
                results["suggestions_created"] += int(bool(created))
            except Exception:
                logger.exception("[config] branch %s failed", bid)
                results["errors"] += 1
        return results

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_closing_all_branches",
    max_retries=3,
    default_retry_delay=120,
)
def run_closing_all_branches(self) -> dict:
    """Scan high-score leads (>=70) across all branches and generate closing proposals.

    run_closing_agent(lead_id, tenant_id) opens its own session — we only use
    a short-lived session here to query candidate leads, then close it before
    calling the agent.
    """
    from sqlalchemy import select
    from app.agents.closing_agent import run_closing_agent
    from app.core.database import set_tenant_context
    from app.models.lead import Lead, LeadStatus

    _TERMINAL = [LeadStatus.PERDIDO, LeadStatus.CALIFICADO]
    _MIN_SCORE = 70

    async def _run() -> dict:
        pairs = await get_active_branch_tenant_pairs()
        results = {"branches": len(pairs), "suggestions_created": 0, "errors": 0}
        logger.info("[closing] running for %d branches", len(pairs))

        for bid, tid in pairs:
            # Short-lived session only for the candidate query. tenant_id ya
            # viene de get_active_branch_tenant_pairs() — antes esta query
            # intentaba DESCUBRIR tenant_id vía SELECT Lead.tenant_id sin
            # contexto todavía seteado, lo cual RLS bloquea (mismo problema
            # que branch_id-only en los otros agentes, solo que acá se
            # camuflaba como "seleccionar una columna" en vez de "no ver
            # filas").
            try:
                async with AsyncSessionLocal() as db:
                    await set_tenant_context(db, tid)
                    rows = await db.execute(
                        select(Lead.id).where(
                            Lead.branch_id == bid,
                            Lead.deleted_at.is_(None),
                            Lead.status.notin_(_TERMINAL),
                            Lead.current_score >= _MIN_SCORE,
                        ).limit(10)
                    )
                    candidate_ids = rows.scalars().all()
            except Exception:
                logger.exception("[closing] candidate query failed for branch=%s", bid)
                results["errors"] += 1
                continue

            # Agent opens its own session per lead
            for lead_id in candidate_ids:
                try:
                    created = await run_closing_agent(lead_id, tid)
                    results["suggestions_created"] += int(bool(created))
                except Exception:
                    logger.exception("[closing] lead %s failed", lead_id)
                    results["errors"] += 1

        return results

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ── Per-tenant agents (caller supplies the DB session) ────────────────────────

@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_reactivation_all_tenants",
    max_retries=3,
    default_retry_delay=120,
)
def run_reactivation_all_tenants(self) -> dict:
    """Run the reactivation agent for every tenant with an active branch."""
    from app.agents.reactivation_agent import run_reactivation_agent

    async def _run() -> dict:
        tenant_ids = await get_active_tenant_ids()
        results = {"tenants": len(tenant_ids), "suggestions_created": 0, "errors": 0}
        logger.info("[reactivation] running for %d tenants", len(tenant_ids))
        for tid in tenant_ids:
            try:
                async with AsyncSessionLocal() as db:
                    count = await run_reactivation_agent(tid, db)
                    await db.commit()
                    results["suggestions_created"] += count or 0
            except Exception:
                logger.exception("[reactivation] tenant %s failed", tid)
                results["errors"] += 1
        return results

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_profile_enrichment_all_tenants",
    max_retries=3,
    default_retry_delay=120,
)
def run_profile_enrichment_all_tenants(self) -> dict:
    """Run the profile enrichment agent for every tenant (every 72 h)."""
    from app.agents.profile_enrichment_agent import run_profile_enrichment_agent

    async def _run() -> dict:
        tenant_ids = await get_active_tenant_ids()
        results = {"tenants": len(tenant_ids), "suggestions_created": 0, "errors": 0}
        logger.info("[enrichment] running for %d tenants", len(tenant_ids))
        for tid in tenant_ids:
            try:
                async with AsyncSessionLocal() as db:
                    count = await run_profile_enrichment_agent(tid, db)
                    await db.commit()
                    results["suggestions_created"] += count or 0
            except Exception:
                logger.exception("[enrichment] tenant %s failed", tid)
                results["errors"] += 1
        return results

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_aprendiz_all_tenants",
    max_retries=3,
    default_retry_delay=120,
)
def run_aprendiz_all_tenants(self) -> dict:
    """Run the Aprendiz pattern-mining agent for every active tenant (weekly)."""
    from app.agents.aprendiz_agent import run_aprendiz_agent, update_user_profiles

    async def _run() -> dict:
        tenant_ids = await get_active_tenant_ids()
        results = {"tenants": len(tenant_ids), "patterns_upserted": 0, "profiles_updated": 0, "errors": 0}
        logger.info("[aprendiz] running for %d tenants", len(tenant_ids))
        for tid in tenant_ids:
            try:
                async with AsyncSessionLocal() as db:
                    count = await run_aprendiz_agent(tid, db)
                    profiles_updated = await update_user_profiles(tid, db)
                    await db.commit()
                    results["patterns_upserted"] += count or 0
                    results["profiles_updated"] += profiles_updated or 0
            except Exception:
                logger.exception("[aprendiz] tenant %s failed", tid)
                results["errors"] += 1
        return results

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ── On-demand execution ───────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.agent_tasks.execute_suggestion_task",
    max_retries=2,
    default_retry_delay=30,
)
def execute_suggestion_task(suggestion_id: str, tenant_id: str) -> dict:
    """Execute a confirmed AgentSuggestion by ID (enqueued from the /confirm endpoint).

    suggestion_id/tenant_id arrive as str (Celery args must be
    JSON-serializable); converted to UUID before passing to
    execute_suggestion(suggestion_id, tenant_id, db).
    """
    from app.agents.executor import execute_suggestion

    async def _run() -> dict:
        sid = uuid.UUID(suggestion_id)
        tid = uuid.UUID(tenant_id)
        async with AsyncSessionLocal() as db:
            return await execute_suggestion(sid, tid, db)

    try:
        return run_async(_run())
    except Exception:
        logger.exception("[execute_suggestion] failed for suggestion=%s", suggestion_id)
        raise
