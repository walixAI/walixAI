"""
Sprint 7 pytest fixtures — async, per-test SAVEPOINT rollback isolation.

Each test gets its own savepoint; the outer transaction is never committed,
so the database stays clean without truncation between tests.

Usage:
    pytest tests/sprint7/ -v
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.activity import Activity
from app.models.base import Base
from app.models.lead import Lead, LeadStatus
from app.models.tag import Tag, lead_tags_table
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


# ── Engine (uses the same DATABASE_URL as the app) ───────────────────────────


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    return url


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the full test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        _async_url(settings.effective_database_url),
        echo=False,
        pool_pre_ping=True,
    )
    yield eng
    await eng.dispose()


# ── Per-test SAVEPOINT isolation ─────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Opens a connection, starts a transaction, creates a SAVEPOINT, yields the
    session, then rolls back to the SAVEPOINT — keeping the DB pristine.
    """
    async with engine.connect() as conn:
        await conn.begin()
        # join_transaction_mode forces SQLAlchemy to use SAVEPOINT instead of
        # a real BEGIN, so our outer transaction controls the rollback.
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
    """AsyncClient with get_db overridden to use the test session."""

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


# ── Tenant / org fixtures ─────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def tenant(db: AsyncSession) -> Tenant:
    t = Tenant(
        name="Test Clínica",
        email=f"test-{uuid.uuid4().hex[:8]}@walix.test",
        plan=TenantPlan.STARTER,
        is_active=True,
    )
    db.add(t)
    await db.flush()
    return t


@pytest_asyncio.fixture()
async def company(db: AsyncSession, tenant: Tenant) -> Company:
    c = Company(tenant_id=tenant.id, name="Test Company S.A.")
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture()
async def branch(db: AsyncSession, company: Company, tenant: Tenant) -> Branch:
    b = Branch(
        company_id=company.id,
        tenant_id=tenant.id,
        name="Sucursal Central",
        is_active=True,
    )
    db.add(b)
    await db.flush()
    return b


# ── User fixtures (one per relevant role) ────────────────────────────────────


def _make_token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


async def _create_user(
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    role: UserRole,
    *,
    suffix: str = "",
) -> User:
    tag = suffix or role.value
    u = User(
        tenant_id=tenant.id,
        branch_id=branch.id,
        email=f"{tag}-{uuid.uuid4().hex[:6]}@walix.test",
        name=f"Usuario {tag.title()}",
        hashed_password=hash_password("test1234"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture()
async def owner_user(db: AsyncSession, tenant: Tenant, branch: Branch) -> User:
    return await _create_user(db, tenant, branch, UserRole.OWNER)


@pytest_asyncio.fixture()
async def manager_user(db: AsyncSession, tenant: Tenant, branch: Branch) -> User:
    return await _create_user(db, tenant, branch, UserRole.GERENTE)


@pytest_asyncio.fixture()
async def asesor_user(db: AsyncSession, tenant: Tenant, branch: Branch) -> User:
    return await _create_user(db, tenant, branch, UserRole.ASESOR)


@pytest_asyncio.fixture()
async def owner_token(owner_user: User) -> str:
    return _make_token(owner_user)


@pytest_asyncio.fixture()
async def manager_token(manager_user: User) -> str:
    return _make_token(manager_user)


@pytest_asyncio.fixture()
async def asesor_token(asesor_user: User) -> str:
    return _make_token(asesor_user)


# ── Auth header helpers ───────────────────────────────────────────────────────


@pytest.fixture()
def auth_owner(owner_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture()
def auth_manager(manager_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {manager_token}"}


@pytest.fixture()
def auth_asesor(asesor_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {asesor_token}"}


# ── Contact (Lead) fixtures ───────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def contact(
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    owner_user: User,
) -> Lead:
    lead = Lead(
        branch_id=branch.id,
        tenant_id=tenant.id,
        wa_phone="+5215512345678",
        name="María",
        last_name="López",
        company="Farmacia Guadalupe",
        status=LeadStatus.NUEVO,
        assigned_to=owner_user.id,
    )
    db.add(lead)
    await db.flush()
    return lead


@pytest_asyncio.fixture()
async def contacts_batch(
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
) -> list[Lead]:
    """10 contacts with varying statuses for list/filter tests."""
    statuses = list(LeadStatus)
    leads = []
    for i in range(10):
        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            wa_phone=f"+521551234{i:04d}",
            name=f"Contacto{i:02d}",
            last_name="Prueba",
            status=statuses[i % len(statuses)],
        )
        db.add(lead)
        leads.append(lead)
    await db.flush()
    return leads


# ── Tag fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def tag(db: AsyncSession, tenant: Tenant) -> Tag:
    t = Tag(tenant_id=tenant.id, name="VIP", color="#7C3AED")
    db.add(t)
    await db.flush()
    return t


@pytest_asyncio.fixture()
async def tags_batch(db: AsyncSession, tenant: Tenant) -> list[Tag]:
    names = ["VIP", "Recurrente", "Demo", "Frío", "Caliente"]
    result = []
    for i, name in enumerate(names):
        t = Tag(tenant_id=tenant.id, name=name, color=f"#{i*20:02X}3AED")
        db.add(t)
        result.append(t)
    await db.flush()
    return result


# ── Activity fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def activity(
    db: AsyncSession,
    contact: Lead,
    tenant: Tenant,
    owner_user: User,
) -> Activity:
    act = Activity(
        lead_id=contact.id,
        tenant_id=tenant.id,
        activity_type="note",
        title="Nota de prueba",
        body="El cliente mostró interés en el plan premium.",
        created_by=owner_user.id,
    )
    db.add(act)
    await db.flush()
    return act
