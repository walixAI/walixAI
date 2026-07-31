"""Finance — expense_categories: access control, CRUD, soft-delete."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import ExpenseCategory
from app.models.tenant import Tenant
from app.models.user import User
from tests.finance.conftest import grant_finance_access


# ── 403 — no finance permission and not OWNER ─────────────────────────────────


async def test_403_list_without_permission(
    client: AsyncClient, auth_asesor: dict, user_asesor: User
) -> None:
    """Asesor sin FinancePermission recibe 403 en GET /expense-categories."""
    r = await client.get("/api/finance/expense-categories", headers=auth_asesor)
    assert r.status_code == 403


async def test_403_create_without_permission(
    client: AsyncClient, auth_asesor: dict
) -> None:
    r = await client.post(
        "/api/finance/expense-categories",
        json={"name": "Renta", "kind": "fijo"},
        headers=auth_asesor,
    )
    assert r.status_code == 403


async def test_403_patch_without_permission(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    auth_asesor: dict,
) -> None:
    """Asesor sin permiso tampoco puede editar aunque conozca el ID."""
    cat = ExpenseCategory(tenant_id=tenant.id, name="Agua", kind="fijo")
    db.add(cat)
    await db.flush()
    r = await client.patch(
        f"/api/finance/expense-categories/{cat.id}",
        json={"name": "Agua editada"},
        headers=auth_asesor,
    )
    assert r.status_code == 403


# ── OWNER — CRUD básico ────────────────────────────────────────────────────────


async def test_owner_can_create_category(
    client: AsyncClient, auth_owner: dict
) -> None:
    r = await client.post(
        "/api/finance/expense-categories",
        json={"name": "Nómina", "kind": "fijo", "icon": "💼"},
        headers=auth_owner,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Nómina"
    assert data["kind"] == "fijo"
    assert data["is_active"] is True


async def test_owner_can_list_active_only(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    """GET sin include_inactive solo devuelve categorías activas."""
    cat_active = ExpenseCategory(tenant_id=tenant.id, name="Luz", kind="fijo", is_active=True)
    cat_inactive = ExpenseCategory(tenant_id=tenant.id, name="Gas", kind="fijo", is_active=False)
    db.add_all([cat_active, cat_inactive])
    await db.flush()

    r = await client.get("/api/finance/expense-categories", headers=auth_owner)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Luz" in names
    assert "Gas" not in names


async def test_list_with_include_inactive(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    cat = ExpenseCategory(tenant_id=tenant.id, name="Obsoleta", kind="variable", is_active=False)
    db.add(cat)
    await db.flush()

    r = await client.get(
        "/api/finance/expense-categories",
        params={"include_inactive": "true"},
        headers=auth_owner,
    )
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Obsoleta" in names


async def test_patch_is_active_false_row_still_exists(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    """is_active=False desactiva la categoría pero NO la borra de la BD."""
    cat = ExpenseCategory(tenant_id=tenant.id, name="Temporal", kind="variable", is_active=True)
    db.add(cat)
    await db.flush()
    cat_id = cat.id

    r = await client.patch(
        f"/api/finance/expense-categories/{cat_id}",
        json={"is_active": False},
        headers=auth_owner,
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # La fila sigue existiendo en la BD
    row = await db.get(ExpenseCategory, cat_id)
    assert row is not None
    assert row.is_active is False


async def test_asesor_with_perm_can_list(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    user_asesor: User,
    auth_asesor: dict,
) -> None:
    """Asesor con FinancePermission (branch_id=NULL) puede listar categorías."""
    await grant_finance_access(db, tenant, user_asesor, user_owner)
    r = await client.get("/api/finance/expense-categories", headers=auth_asesor)
    assert r.status_code == 200
