"""
Sprint 8A pytest fixtures — SavedViews + WalixAIBar CRUD.

Inherits the core DB/HTTP infrastructure from Sprint 7 (engine, db, client)
and defines Sprint 8A-specific fixtures with the canonical naming convention.

Usage:
    pytest tests/sprint8a/ -v
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ── Re-export Sprint 7 infrastructure ────────────────────────────────────────
# event_loop, engine, and db/client factories stay identical.

from tests.sprint7.conftest import (  # noqa: F401
    event_loop,
    engine,
)

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.saved_view import SavedView
from app.models.tag import Tag
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


# ── Core session fixtures ─────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


# ── Tenant fixtures ───────────────────────────────────────────────────────────


async def _make_tenant(db: AsyncSession, *, suffix: str = "") -> Tenant:
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


async def _make_branch(db: AsyncSession, tenant: Tenant, company: Company) -> Branch:
    b = Branch(
        company_id=company.id,
        tenant_id=tenant.id,
        name="Sucursal Central",
        is_active=True,
    )
    db.add(b)
    await db.flush()
    return b


@pytest_asyncio.fixture()
async def tenant_a(db: AsyncSession) -> Tenant:
    return await _make_tenant(db, suffix="A")


@pytest_asyncio.fixture()
async def tenant_b(db: AsyncSession) -> Tenant:
    return await _make_tenant(db, suffix="B")


@pytest_asyncio.fixture()
async def branch_a(db: AsyncSession, tenant_a: Tenant) -> Branch:
    company = await _make_company(db, tenant_a)
    return await _make_branch(db, tenant_a, company)


@pytest_asyncio.fixture()
async def branch_b(db: AsyncSession, tenant_b: Tenant) -> Branch:
    company = await _make_company(db, tenant_b)
    return await _make_branch(db, tenant_b, company)


# ── User fixtures ─────────────────────────────────────────────────────────────


def _token(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


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


@pytest_asyncio.fixture()
async def user_asesor(db: AsyncSession, tenant_a: Tenant, branch_a: Branch) -> User:
    return await _make_user(db, tenant_a, branch_a, UserRole.ASESOR)


@pytest_asyncio.fixture()
async def user_gerente(db: AsyncSession, tenant_a: Tenant, branch_a: Branch) -> User:
    return await _make_user(db, tenant_a, branch_a, UserRole.GERENTE)


@pytest_asyncio.fixture()
async def user_owner(db: AsyncSession, tenant_a: Tenant, branch_a: Branch) -> User:
    return await _make_user(db, tenant_a, branch_a, UserRole.OWNER)


@pytest_asyncio.fixture()
async def user_other_tenant(db: AsyncSession, tenant_b: Tenant, branch_b: Branch) -> User:
    return await _make_user(db, tenant_b, branch_b, UserRole.ASESOR)


# ── Auth header shortcuts ─────────────────────────────────────────────────────


@pytest.fixture()
def auth_asesor(user_asesor: User) -> dict[str, str]:
    return _auth(user_asesor)


@pytest.fixture()
def auth_gerente(user_gerente: User) -> dict[str, str]:
    return _auth(user_gerente)


@pytest.fixture()
def auth_owner(user_owner: User) -> dict[str, str]:
    return _auth(user_owner)


@pytest.fixture()
def auth_other(user_other_tenant: User) -> dict[str, str]:
    return _auth(user_other_tenant)


# ── Contact (Lead) fixtures ───────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def contact_minimal(
    db: AsyncSession, tenant_a: Tenant, branch_a: Branch, user_asesor: User
) -> Lead:
    """Contact with the minimum required fields."""
    lead = Lead(
        branch_id=branch_a.id,
        tenant_id=tenant_a.id,
        wa_phone="+5215512345001",
        name="Ana",
        status=LeadStatus.NUEVO,
        source=LeadSource.MANUAL,
        sentiment=LeadSentiment.NEUTRAL,
        assigned_to=user_asesor.id,
    )
    db.add(lead)
    await db.flush()
    return lead


@pytest_asyncio.fixture()
async def contact_full(
    db: AsyncSession, tenant_a: Tenant, branch_a: Branch, user_asesor: User
) -> Lead:
    """Fully populated contact."""
    lead = Lead(
        branch_id=branch_a.id,
        tenant_id=tenant_a.id,
        wa_phone="+5215512345002",
        name="Carlos",
        last_name="García",
        company="Farmacia San Juan",
        prospection_source="whatsapp_inbound",
        status=LeadStatus.CALIFICADO,
        source=LeadSource.WHATSAPP_INBOUND,
        sentiment=LeadSentiment.INTERESADO,
        assigned_to=user_asesor.id,
        last_activity_summary="Interesado en plan premium",
    )
    db.add(lead)
    await db.flush()
    return lead


@pytest_asyncio.fixture()
async def contacts_list(
    db: AsyncSession, tenant_a: Tenant, branch_a: Branch, user_asesor: User
) -> list[Lead]:
    """12 contacts with varied statuses and companies for list/filter tests."""
    statuses = list(LeadStatus)
    leads = []
    for i in range(12):
        lead = Lead(
            branch_id=branch_a.id,
            tenant_id=tenant_a.id,
            wa_phone=f"+52155123{i:05d}",
            name=f"Contacto{i:02d}",
            last_name="Prueba",
            company=f"Empresa {chr(65 + i % 5)}",
            status=statuses[i % len(statuses)],
            source=LeadSource.MANUAL,
            sentiment=LeadSentiment.NEUTRAL,
        )
        db.add(lead)
        leads.append(lead)
    await db.flush()
    return leads


# ── Tag fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def tag_vip(db: AsyncSession, tenant_a: Tenant) -> Tag:
    t = Tag(tenant_id=tenant_a.id, name="VIP", color="#7C3AED")
    db.add(t)
    await db.flush()
    return t


# ── SavedView fixtures (Sprint 8A new) ────────────────────────────────────────


@pytest_asyncio.fixture()
async def saved_view_basic(
    db: AsyncSession, user_asesor: User, tenant_a: Tenant
) -> SavedView:
    """Basic saved view — not default, list mode, status filter."""
    view = SavedView(
        user_id=user_asesor.id,
        tenant_id=tenant_a.id,
        name="Mis calificados",
        filters={"status": ["calificado"]},
        view_mode="list",
        is_default=False,
    )
    db.add(view)
    await db.flush()
    return view


@pytest_asyncio.fixture()
async def saved_view_default(
    db: AsyncSession, user_asesor: User, tenant_a: Tenant
) -> SavedView:
    """Default saved view — kanban mode, no filters."""
    view = SavedView(
        user_id=user_asesor.id,
        tenant_id=tenant_a.id,
        name="Vista principal",
        filters={},
        view_mode="kanban",
        is_default=True,
    )
    db.add(view)
    await db.flush()
    return view


@pytest_asyncio.fixture()
async def multiple_views(
    db: AsyncSession, user_asesor: User, tenant_a: Tenant
) -> list[SavedView]:
    """10 saved views for the asesor user — exercises the plan limit."""
    views = []
    for i in range(1, 11):
        view = SavedView(
            user_id=user_asesor.id,
            tenant_id=tenant_a.id,
            name=f"Vista {i}",
            filters={"status": ["nuevo"]} if i % 2 == 0 else {},
            view_mode="list",
            is_default=(i == 1),
        )
        db.add(view)
        views.append(view)
    await db.flush()
    return views


# ── Claude Haiku mock ─────────────────────────────────────────────────────────


class ClaudeMock:
    """
    Wrapper around the patched Anthropic client.

    Provides convenience helpers so each test can express intent clearly:

        def test_create(client, mock_claude_haiku, auth_asesor):
            mock_claude_haiku.returns_contact_create("María", phone="+5215512340001")
            ...
    """

    def __init__(self, mock_client: MagicMock) -> None:
        self._client = mock_client

    # ── Low-level builder ─────────────────────────────────────────────────────

    def returns_json(self, payload: dict[str, Any]) -> None:
        """Configure the mock to return an arbitrary JSON payload as Claude response."""
        text = json.dumps(payload, ensure_ascii=False)
        resp = MagicMock()
        resp.content = [MagicMock(text=text)]
        resp.usage.input_tokens = 80
        resp.usage.output_tokens = 40
        self._client.messages.create = AsyncMock(return_value=resp)

    # ── Domain-specific helpers ───────────────────────────────────────────────

    def returns_contact_create(
        self,
        name: str = "Test Usuario",
        *,
        last_name: str | None = None,
        phone: str | None = None,
        company: str | None = None,
        prospection_source: str = "manual",
    ) -> None:
        self.returns_json({
            "intent_type": "accion",
            "response_text": f"Creando contacto {name}.",
            "requires_confirmation": False,
            "actions": [{
                "type": "contact_create",
                "params": {
                    "name": name,
                    "last_name": last_name,
                    "phone": phone,
                    "company": company,
                    "prospection_source": prospection_source,
                },
            }],
            "data_query": None,
            "suggested_actions": [],
        })

    def returns_contact_read(
        self,
        *,
        q: str | None = None,
        status: list[str] | None = None,
        company: str | None = None,
        date_range: str | None = None,
    ) -> None:
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        if status:
            params["status"] = status
        if company:
            params["company"] = company
        if date_range:
            params["date_range"] = date_range
        self.returns_json({
            "intent_type": "consulta",
            "response_text": "Buscando contactos.",
            "requires_confirmation": False,
            "actions": [{"type": "contact_read", "params": params}],
            "data_query": None,
            "suggested_actions": [],
        })

    def returns_contact_update(
        self,
        contact_ref: str,
        field: str,
        new_value: str,
    ) -> None:
        self.returns_json({
            "intent_type": "accion",
            "response_text": f"Actualizando {field} de {contact_ref}.",
            "requires_confirmation": False,
            "actions": [{
                "type": "contact_update",
                "params": {
                    "contact_ref": contact_ref,
                    "field": field,
                    "new_value": new_value,
                },
            }],
            "data_query": None,
            "suggested_actions": [],
        })

    def returns_contact_activity(
        self,
        contact_ref: str,
        activity_type: str = "note",
        body: str = "Actividad de prueba",
        *,
        title: str | None = None,
    ) -> None:
        self.returns_json({
            "intent_type": "accion",
            "response_text": f"Registrando {activity_type} para {contact_ref}.",
            "requires_confirmation": False,
            "actions": [{
                "type": "contact_activity",
                "params": {
                    "contact_ref": contact_ref,
                    "activity_type": activity_type,
                    "title": title,
                    "body": body,
                    "due_date": None,
                },
            }],
            "data_query": None,
            "suggested_actions": [],
        })

    def returns_contact_delete(
        self,
        contact_ref: str,
        *,
        requires_confirmation: bool = True,
    ) -> None:
        self.returns_json({
            "intent_type": "accion",
            "response_text": f"Solicitando confirmación para archivar {contact_ref}.",
            "requires_confirmation": requires_confirmation,
            "actions": [{
                "type": "contact_delete",
                "params": {"contact_ref": contact_ref, "bulk": False},
            }],
            "data_query": None,
            "suggested_actions": [],
        })

    def returns_ambiguous(self, response_text: str = "No entendí tu instrucción.") -> None:
        self.returns_json({
            "intent_type": "consulta",
            "response_text": response_text,
            "requires_confirmation": False,
            "actions": [],
            "data_query": None,
            "suggested_actions": [],
        })

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def call_count(self) -> int:
        return self._client.messages.create.call_count

    @property
    def last_system_prompt(self) -> str:
        """Returns the system prompt from the last Claude call."""
        call_args = self._client.messages.create.call_args
        if call_args is None:
            return ""
        return call_args.kwargs.get("system", call_args.args[0] if call_args.args else "")

    @property
    def last_user_message(self) -> str:
        """Returns the last user message sent to Claude."""
        call_args = self._client.messages.create.call_args
        if call_args is None:
            return ""
        messages = call_args.kwargs.get("messages", [])
        user_msgs = [m for m in messages if m.get("role") == "user"]
        return user_msgs[-1]["content"] if user_msgs else ""


@pytest.fixture()
def mock_claude_haiku() -> ClaudeMock:
    """
    Patches the Anthropic client used by the AI Bar endpoint.

    Yields a ``ClaudeMock`` instance. Use its helper methods to configure
    the expected Claude response before calling the endpoint under test:

        mock_claude_haiku.returns_contact_create("Juan", phone="+5215512340001")
        resp = await client.post("/api/ai/command", ...)
    """
    with patch("app.api.ai._anthropic") as mock_client:
        mock_client.messages.create = AsyncMock()
        wrapper = ClaudeMock(mock_client)
        # Sensible default — won't trigger any action
        wrapper.returns_ambiguous("¿En qué puedo ayudarte?")
        yield wrapper
