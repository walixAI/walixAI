"""
Finance module pytest fixtures — async, per-test SAVEPOINT rollback isolation.

Reuses the event_loop + engine from Sprint 7 conftest; redefines db/client
with the identical SAVEPOINT pattern used in Sprint 8A.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Re-use session-scoped infrastructure from Sprint 7
from tests.sprint7.conftest import engine, event_loop  # noqa: F401

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.finance import FinancePermission
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


# ── Per-test SAVEPOINT isolation ──────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    async with engine.connect() as conn:
        await conn.begin()
        factory = async_sessionmaker(
            bind=conn,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture()
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


async def _make_tenant(db: AsyncSession, suffix: str = "") -> Tenant:
    tag = suffix or uuid.uuid4().hex[:6]
    t = Tenant(
        name=f"Clínica {tag}",
        email=f"clinica-{tag}@walix.test",
        plan=TenantPlan.STARTER,
        is_active=True,
    )
    db.add(t)
    await db.flush()
    return t


async def _make_company(db: AsyncSession, tenant: Tenant) -> Company:
    c = Company(tenant_id=tenant.id, name=f"Empresa {tenant.name}")
    db.add(c)
    await db.flush()
    return c


async def _make_branch(db: AsyncSession, tenant: Tenant, company: Company, name: str = "Sucursal Central") -> Branch:
    b = Branch(
        company_id=company.id,
        tenant_id=tenant.id,
        name=name,
        is_active=True,
    )
    db.add(b)
    await db.flush()
    return b


async def _make_user(
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    role: UserRole,
    *,
    name: str | None = None,
) -> User:
    tag = uuid.uuid4().hex[:6]
    u = User(
        tenant_id=tenant.id,
        branch_id=branch.id,
        email=f"{role.value}-{tag}@walix.test",
        name=name or f"Usuario {role.value.title()}",
        hashed_password=hash_password("test1234"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


# ── Core org fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def tenant(db: AsyncSession) -> Tenant:
    return await _make_tenant(db, "main")


@pytest_asyncio.fixture()
async def company(db: AsyncSession, tenant: Tenant) -> Company:
    return await _make_company(db, tenant)


@pytest_asyncio.fixture()
async def branch(db: AsyncSession, tenant: Tenant, company: Company) -> Branch:
    return await _make_branch(db, tenant, company)


@pytest_asyncio.fixture()
async def branch_b(db: AsyncSession, tenant: Tenant, company: Company) -> Branch:
    """Second branch on the same tenant — used for cross-branch access tests."""
    return await _make_branch(db, tenant, company, name="Sucursal Norte")


# ── User fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def user_owner(db: AsyncSession, tenant: Tenant, branch: Branch) -> User:
    return await _make_user(db, tenant, branch, UserRole.OWNER, name="Owner Principal")


@pytest_asyncio.fixture()
async def user_asesor(db: AsyncSession, tenant: Tenant, branch: Branch) -> User:
    return await _make_user(db, tenant, branch, UserRole.ASESOR, name="Asesor Uno")


@pytest_asyncio.fixture()
async def user_asesor2(db: AsyncSession, tenant: Tenant, branch: Branch) -> User:
    return await _make_user(db, tenant, branch, UserRole.ASESOR, name="Asesor Dos")


# ── Auth header fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def auth_owner(user_owner: User) -> dict[str, str]:
    return _auth(user_owner)


@pytest.fixture()
def auth_asesor(user_asesor: User) -> dict[str, str]:
    return _auth(user_asesor)


# ── Finance permission helpers ─────────────────────────────────────────────────


async def grant_finance_access(
    db: AsyncSession,
    tenant: Tenant,
    user: User,
    granted_by: User,
    *,
    branch_id: uuid.UUID | None = None,
) -> FinancePermission:
    """Grant a user finance access (all-tenant if branch_id is None)."""
    perm = FinancePermission(
        tenant_id=tenant.id,
        user_id=user.id,
        branch_id=branch_id,
        granted_by=granted_by.id,
    )
    db.add(perm)
    await db.flush()
    return perm


# ── Lead / Pipeline / Deal helpers ────────────────────────────────────────────


async def make_lead(db: AsyncSession, tenant: Tenant, branch: Branch, *, phone: str | None = None) -> Lead:
    lead = Lead(
        branch_id=branch.id,
        tenant_id=tenant.id,
        wa_phone=phone or f"+521{uuid.uuid4().int % 10**10:010d}",
        name="Cliente Test",
        status=LeadStatus.NUEVO,
        source=LeadSource.MANUAL,
        sentiment=LeadSentiment.NEUTRAL,
    )
    db.add(lead)
    await db.flush()
    return lead


async def make_pipeline_and_stage(
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    *,
    stage_name: str = "Cotización",
) -> tuple[Pipeline, PipelineStage]:
    # Use a unique suffix to avoid UniqueConstraint(branch_id, name) conflicts
    # when multiple tests or fixtures create pipelines for the same branch.
    suffix = uuid.uuid4().hex[:6]
    pl = Pipeline(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name=f"Pipeline {suffix}",
        is_default=False,
    )
    db.add(pl)
    await db.flush()

    stage = PipelineStage(
        branch_id=branch.id,
        tenant_id=tenant.id,
        pipeline_id=pl.id,
        name=stage_name,
        slug=f"{stage_name.lower().replace(' ', '_')}_{suffix}",
        order_index=0,
    )
    db.add(stage)
    await db.flush()
    return pl, stage
