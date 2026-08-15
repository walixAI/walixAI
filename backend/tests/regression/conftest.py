"""
Fixtures compartidos — suite de regresión general de Walix.

Reexporta los fixtures base de tests/sprint7/conftest.py (engine, db, client,
tenant, company, branch, owner_user/manager_user/asesor_user + tokens/headers,
contact) vía `import *`, y añade fixtures propios de Deals, Pipeline y
multi-tenant necesarios para las pruebas de Sprint 13-14 y la consolidación
del dashboard.

Uso:
    pytest tests/regression/ -v
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# Reexporta engine/db/client/tenant/company/branch/*_user/*_token/auth_*/contact
from tests.sprint7.conftest import *  # noqa: F401,F403

from app.core.security import create_access_token, hash_password
from app.models.deal import Deal
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


# ── Pipeline / Deal fixtures ──────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def pipeline(db: AsyncSession, tenant: Tenant, branch: Branch) -> Pipeline:
    p = Pipeline(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Pipeline Test",
        is_default=True,
        position=0,
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture()
async def stages(db: AsyncSession, tenant: Tenant, branch: Branch, pipeline: Pipeline) -> list[PipelineStage]:
    """3 etapas: Nuevo (0) -> Negociación (1, pre-ganado) -> Ganado (2, is_won)."""
    defs = [
        ("Nuevo", "nuevo", 0, False, False, 10),
        ("Negociación", "negociacion", 1, False, False, 60),
        ("Ganado", "ganado", 2, True, False, 100),
    ]
    created = []
    for name, slug, order_index, is_won, is_lost, prob_default in defs:
        s = PipelineStage(
            tenant_id=tenant.id,
            branch_id=branch.id,
            pipeline_id=pipeline.id,
            name=name,
            slug=slug,
            order_index=order_index,
            is_won=is_won,
            is_lost=is_lost,
            probability_default=prob_default,
        )
        db.add(s)
        created.append(s)
    await db.flush()
    return created


@pytest_asyncio.fixture()
async def lost_stage(db: AsyncSession, tenant: Tenant, branch: Branch, pipeline: Pipeline) -> PipelineStage:
    s = PipelineStage(
        tenant_id=tenant.id,
        branch_id=branch.id,
        pipeline_id=pipeline.id,
        name="Perdido",
        slug="perdido",
        order_index=3,
        is_won=False,
        is_lost=True,
        probability_default=0,
    )
    db.add(s)
    await db.flush()
    return s


@pytest_asyncio.fixture()
async def deal(
    db: AsyncSession,
    tenant: Tenant,
    contact,
    stages: list[PipelineStage],
    owner_user: User,
) -> Deal:
    d = Deal(
        tenant_id=tenant.id,
        lead_id=contact.id,
        pipeline_stage_id=stages[0].id,
        title="Deal de prueba",
        amount=10_000,
        probability=stages[0].probability_default,
        owner_id=owner_user.id,
    )
    db.add(d)
    await db.flush()
    return d


# ── Tenant ajeno (multi-tenant / RLS) ─────────────────────────────────────────

@pytest_asyncio.fixture()
async def other_tenant_ctx(db: AsyncSession) -> dict:
    """Tenant B completo (tenant/company/branch/owner) — aislado del tenant principal."""
    t = Tenant(
        name=f"Tenant Externo {uuid.uuid4().hex[:6]}",
        email=f"ext-{uuid.uuid4().hex[:6]}@walix.test",
        plan=TenantPlan.STARTER,
        is_active=True,
    )
    db.add(t)
    await db.flush()

    company = Company(tenant_id=t.id, name="Empresa Externa S.A.")
    db.add(company)
    await db.flush()

    branch_ext = Branch(company_id=company.id, tenant_id=t.id, name="Sucursal Externa", is_active=True)
    db.add(branch_ext)
    await db.flush()

    user = User(
        tenant_id=t.id,
        branch_id=branch_ext.id,
        email=f"ext-{uuid.uuid4().hex[:8]}@walix.test",
        name="Usuario Externo",
        hashed_password=hash_password("test1234"),
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    return {
        "tenant": t,
        "company": company,
        "branch": branch_ext,
        "user": user,
        "token": create_access_token({"sub": str(user.id)}),
    }


@pytest_asyncio.fixture()
def auth_other_tenant(other_tenant_ctx: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {other_tenant_ctx['token']}"}
