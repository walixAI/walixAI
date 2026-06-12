"""Celery tasks for Walix proactive agents.

Each task wraps an async agent function with asyncio.run(). The NullPool
session factory (patched in by celery_app.worker_process_init) ensures fresh
DB connections are created inside each asyncio.run() invocation.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_active_branch_ids() -> list[uuid.UUID]:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Branch

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Branch.id).where(Branch.is_active.is_(True)))
        return list(result.scalars().all())


async def _get_active_tenant_ids() -> list[uuid.UUID]:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Branch

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Branch.tenant_id).where(Branch.is_active.is_(True)).distinct()
        )
        return list(result.scalars().all())


# ── Agent tasks ───────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_follow_up_all_branches",
    max_retries=3,
    default_retry_delay=60,
)
def run_follow_up_all_branches(self) -> dict:
    """Run the follow-up agent for every active branch."""
    from app.agents.follow_up_agent import run_follow_up_agent

    async def _run() -> dict:
        branch_ids = await _get_active_branch_ids()
        results = {"branches": len(branch_ids), "suggestions_created": 0, "errors": 0}
        for bid in branch_ids:
            try:
                count = await run_follow_up_agent(bid)
                results["suggestions_created"] += count or 0
            except Exception:
                logger.exception("follow_up_agent failed for branch=%s", bid)
                results["errors"] += 1
        return results

    try:
        return asyncio.run(_run())
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
        branch_ids = await _get_active_branch_ids()
        results = {"branches": len(branch_ids), "errors": 0}
        for bid in branch_ids:
            try:
                await run_pipeline_agent(bid)
            except Exception:
                logger.exception("pipeline_agent failed for branch=%s", bid)
                results["errors"] += 1
        return results

    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_config_all_branches",
    max_retries=3,
    default_retry_delay=300,
)
def run_config_all_branches(self) -> dict:
    """Run the pipeline config agent for every active branch (weekly)."""
    from app.agents.config_agent import run_config_agent

    async def _run() -> dict:
        branch_ids = await _get_active_branch_ids()
        results = {"branches": len(branch_ids), "errors": 0}
        for bid in branch_ids:
            try:
                await run_config_agent(bid)
            except Exception:
                logger.exception("config_agent failed for branch=%s", bid)
                results["errors"] += 1
        return results

    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_reactivation_all_tenants",
    max_retries=3,
    default_retry_delay=300,
)
def run_reactivation_all_tenants(self) -> dict:
    """Run the reactivation agent for all tenants (weekly)."""
    from app.agents.reactivation_agent import run_reactivation_agent
    from app.core.database import AsyncSessionLocal

    async def _run() -> dict:
        tenant_ids = await _get_active_tenant_ids()
        results = {"tenants": len(tenant_ids), "suggestions_created": 0, "errors": 0}
        for tid in tenant_ids:
            try:
                async with AsyncSessionLocal() as db:
                    count = await run_reactivation_agent(tid, db)
                    await db.commit()
                    results["suggestions_created"] += count or 0
            except Exception:
                logger.exception("reactivation_agent failed for tenant=%s", tid)
                results["errors"] += 1
        return results

    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.agent_tasks.run_profile_enrichment_all_tenants",
    max_retries=3,
    default_retry_delay=300,
)
def run_profile_enrichment_all_tenants(self) -> dict:
    """Run the profile enrichment agent for all tenants (every 72 h)."""
    from app.agents.profile_enrichment_agent import run_profile_enrichment_agent
    from app.core.database import AsyncSessionLocal

    async def _run() -> dict:
        tenant_ids = await _get_active_tenant_ids()
        results = {"tenants": len(tenant_ids), "suggestions_created": 0, "errors": 0}
        for tid in tenant_ids:
            try:
                async with AsyncSessionLocal() as db:
                    count = await run_profile_enrichment_agent(tid, db)
                    await db.commit()
                    results["suggestions_created"] += count or 0
            except Exception:
                logger.exception("profile_enrichment_agent failed for tenant=%s", tid)
                results["errors"] += 1
        return results

    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ── On-demand execution ───────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.agent_tasks.execute_suggestion_task",
    max_retries=2,
    default_retry_delay=30,
)
def execute_suggestion_task(suggestion_id: str) -> dict:
    """Execute a confirmed AgentSuggestion by ID (enqueued from the /confirm endpoint)."""
    from app.agents.executor import execute_suggestion
    from app.core.database import AsyncSessionLocal

    async def _run() -> dict:
        sid = uuid.UUID(suggestion_id)
        async with AsyncSessionLocal() as db:
            return await execute_suggestion(sid, db)

    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("execute_suggestion_task failed for suggestion=%s", suggestion_id)
        raise
