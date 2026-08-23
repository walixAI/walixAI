"""
Regresión — PLATFORM_OWNER ahora tiene acceso cross-branch en leads.py,
pipeline.py, pipelines.py, users.py y metrics.py (hallazgo #1,
docs/PERMISSIONS_DRIFT_BACKLOG.md).

Código auditado:
  - app/core/roles.py::MULTI_BRANCH_ROLES (única fuente de verdad, incluye
    PLATFORM_OWNER) — reemplaza las 4 definiciones locales sin
    PLATFORM_OWNER en leads.py/pipeline.py/pipelines.py/users.py.
  - app/api/leads.py::_get_lead_accessible
  - app/api/metrics.py::_resolve_branch
  - app/api/pipeline.py::get_pipeline_board (GET /api/pipeline/board)
  - app/api/pipelines.py::list_pipelines (GET /api/pipelines)
  - app/api/users.py::list_tenant_users (GET /api/users)

No se probaba antes esta ampliación de acceso para PLATFORM_OWNER en estos
5 módulos porque no existía — ver búsqueda documentada en el mensaje del
PR: no había ningún test previo que asumiera lo contrario, así que nada se
ajustó, solo se agregó cobertura nueva.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.leads import _get_lead_accessible
from app.api.metrics import _resolve_branch
from app.core.security import create_access_token, hash_password
from app.models.lead import Lead, LeadStatus
from app.models.pipeline_group import Pipeline
from app.models.tenant import Branch, Company, Tenant
from app.models.user import User, UserRole


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_platform_owner(db: AsyncSession, tenant: Tenant, branch: Branch) -> tuple[User, str]:
    u = User(
        tenant_id=tenant.id, branch_id=branch.id,
        email=f"po-{uuid.uuid4().hex[:6]}@walix.test", name="Platform Owner",
        hashed_password=hash_password("test1234"),
        role=UserRole.PLATFORM_OWNER, is_active=True,
    )
    db.add(u)
    await db.flush()
    return u, create_access_token({"sub": str(u.id)})


async def _make_second_branch(db: AsyncSession, tenant: Tenant, company: Company) -> Branch:
    b = Branch(company_id=company.id, tenant_id=tenant.id, name="Sucursal B", is_active=True)
    db.add(b)
    await db.flush()
    return b


# ── leads.py::_get_lead_accessible ──────────────────────────────────────────────

async def test_platform_owner_can_access_lead_in_other_branch(
    db: AsyncSession, tenant: Tenant, branch: Branch, company: Company,
) -> None:
    other_branch = await _make_second_branch(db, tenant, company)
    platform_owner, _ = await _make_platform_owner(db, tenant, branch)

    lead = Lead(
        tenant_id=tenant.id, branch_id=other_branch.id,
        wa_phone="+5215500000000", name="Lead Otra Sucursal", status=LeadStatus.NUEVO,
    )
    db.add(lead)
    await db.flush()

    accessed = await _get_lead_accessible(db, lead.id, platform_owner)
    assert accessed.id == lead.id


async def test_asesor_still_denied_lead_in_other_branch(
    db: AsyncSession, tenant: Tenant, branch: Branch, company: Company, asesor_user: User,
) -> None:
    other_branch = await _make_second_branch(db, tenant, company)
    lead = Lead(
        tenant_id=tenant.id, branch_id=other_branch.id,
        wa_phone="+5215500000001", name="Lead Otra Sucursal", status=LeadStatus.NUEVO,
    )
    db.add(lead)
    await db.flush()

    with pytest.raises(Exception) as exc_info:
        await _get_lead_accessible(db, lead.id, asesor_user)
    assert getattr(exc_info.value, "status_code", None) == 404


# ── metrics.py::_resolve_branch ──────────────────────────────────────────────────

async def test_resolve_branch_allows_platform_owner_cross_branch(
    tenant: Tenant, branch: Branch,
) -> None:
    other_branch_id = uuid.uuid4()
    platform_owner = User(
        tenant_id=tenant.id, branch_id=branch.id, email="po@walix.test",
        name="Platform Owner", hashed_password="x", role=UserRole.PLATFORM_OWNER,
        is_active=True,
    )
    resolved = _resolve_branch(other_branch_id, platform_owner)
    assert resolved == other_branch_id


async def test_resolve_branch_still_denies_asesor_cross_branch(
    tenant: Tenant, branch: Branch, asesor_user: User,
) -> None:
    other_branch_id = uuid.uuid4()
    with pytest.raises(Exception) as exc_info:
        _resolve_branch(other_branch_id, asesor_user)
    assert getattr(exc_info.value, "status_code", None) == 403


# ── pipelines.py::list_pipelines (GET /api/pipelines) ───────────────────────────

async def test_platform_owner_lists_pipelines_across_all_branches(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, company: Company,
) -> None:
    other_branch = await _make_second_branch(db, tenant, company)
    _, po_token = await _make_platform_owner(db, tenant, branch)

    db.add(Pipeline(tenant_id=tenant.id, branch_id=branch.id, name="Pipeline A", is_default=True, position=0))
    db.add(Pipeline(tenant_id=tenant.id, branch_id=other_branch.id, name="Pipeline B", is_default=True, position=0))
    await db.flush()

    r = await client.get("/api/pipelines", headers=auth(po_token))
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert {"Pipeline A", "Pipeline B"} <= names


async def test_asesor_only_lists_own_branch_pipelines(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, company: Company,
    asesor_user: User, asesor_token: str,
) -> None:
    other_branch = await _make_second_branch(db, tenant, company)
    asesor_user.branch_id = branch.id
    db.add(Pipeline(tenant_id=tenant.id, branch_id=branch.id, name="Pipeline A", is_default=True, position=0))
    db.add(Pipeline(tenant_id=tenant.id, branch_id=other_branch.id, name="Pipeline B", is_default=True, position=0))
    await db.flush()

    r = await client.get("/api/pipelines", headers=auth(asesor_token))
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert names == {"Pipeline A"}


# ── pipeline.py::get_pipeline_board (GET /api/pipeline/board) ──────────────────

async def test_platform_owner_can_view_board_of_other_branch(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, company: Company,
) -> None:
    other_branch = await _make_second_branch(db, tenant, company)
    _, po_token = await _make_platform_owner(db, tenant, branch)

    r = await client.get(
        "/api/pipeline/board", params={"branch_id": str(other_branch.id)}, headers=auth(po_token),
    )
    assert r.status_code == 200


async def test_asesor_denied_board_of_other_branch(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, company: Company,
    asesor_user: User, asesor_token: str,
) -> None:
    other_branch = await _make_second_branch(db, tenant, company)
    asesor_user.branch_id = branch.id
    await db.flush()

    r = await client.get(
        "/api/pipeline/board", params={"branch_id": str(other_branch.id)}, headers=auth(asesor_token),
    )
    assert r.status_code == 403


# ── users.py::list_tenant_users (GET /api/users) ────────────────────────────────

async def test_platform_owner_sees_users_from_all_branches(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, company: Company,
    asesor_user: User,
) -> None:
    other_branch = await _make_second_branch(db, tenant, company)
    _, po_token = await _make_platform_owner(db, tenant, branch)

    other_branch_user = User(
        tenant_id=tenant.id, branch_id=other_branch.id,
        email=f"otro-{uuid.uuid4().hex[:6]}@walix.test", name="Usuario Otra Sucursal",
        hashed_password=hash_password("test1234"), role=UserRole.ASESOR, is_active=True,
    )
    db.add(other_branch_user)
    await db.flush()

    r = await client.get("/api/users", headers=auth(po_token))
    assert r.status_code == 200
    names = {u["name"] for u in r.json()}
    assert "Usuario Otra Sucursal" in names


async def test_asesor_only_sees_own_branch_users(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, company: Company,
    asesor_user: User, asesor_token: str,
) -> None:
    asesor_user.branch_id = branch.id
    other_branch = await _make_second_branch(db, tenant, company)
    other_branch_user = User(
        tenant_id=tenant.id, branch_id=other_branch.id,
        email=f"otro-{uuid.uuid4().hex[:6]}@walix.test", name="Usuario Otra Sucursal",
        hashed_password=hash_password("test1234"), role=UserRole.ASESOR, is_active=True,
    )
    db.add(other_branch_user)
    await db.flush()

    r = await client.get("/api/users", headers=auth(asesor_token))
    assert r.status_code == 200
    names = {u["name"] for u in r.json()}
    assert "Usuario Otra Sucursal" not in names
