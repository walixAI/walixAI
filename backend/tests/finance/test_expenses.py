"""Finance — expenses: validación, filtros, confirm, confirm-all, delete."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Expense
from app.models.tenant import Tenant
from app.models.user import User
from tests.finance.conftest import (
    _make_branch,
    _make_company,
    _make_tenant,
    _make_user,
    _token,
    grant_finance_access,
)
from app.models.user import UserRole


# ── Helpers ───────────────────────────────────────────────────────────────────


def _expense_payload(**overrides) -> dict:
    base = {"amount": 150.0, "kind": "fijo"}
    return {**base, **overrides}


def _make_db_expense(
    tenant: Tenant,
    *,
    amount: float = 200.0,
    kind: str = "fijo",
    status: str = "draft",
    month: date | None = None,
) -> Expense:
    inc = month or date.today()
    return Expense(
        tenant_id=tenant.id,
        amount=amount,
        kind=kind,
        currency="MXN",
        incurred_at=inc,
        status=status,
        source="manual",
    )


# ── amount <= 0 → 422 ─────────────────────────────────────────────────────────


async def test_create_amount_zero_raises_422(client: AsyncClient, auth_owner: dict) -> None:
    r = await client.post(
        "/api/finance/expenses",
        json=_expense_payload(amount=0),
        headers=auth_owner,
    )
    assert r.status_code == 422


async def test_create_negative_amount_raises_422(client: AsyncClient, auth_owner: dict) -> None:
    r = await client.post(
        "/api/finance/expenses",
        json=_expense_payload(amount=-50),
        headers=auth_owner,
    )
    assert r.status_code == 422


async def test_update_amount_zero_raises_422(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    exp = _make_db_expense(tenant, status="confirmed")
    db.add(exp)
    await db.flush()

    r = await client.patch(
        f"/api/finance/expenses/{exp.id}",
        json={"amount": 0},
        headers=auth_owner,
    )
    assert r.status_code == 422


# ── Filtros GET /expenses ─────────────────────────────────────────────────────


async def test_filter_by_month(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    """Solo devuelve gastos dentro del mes especificado."""
    jan = date(2026, 1, 15)
    jun = date(2026, 6, 15)
    exp_jan = _make_db_expense(tenant, month=jan, status="confirmed")
    exp_jun = _make_db_expense(tenant, month=jun, status="confirmed")
    db.add_all([exp_jan, exp_jun])
    await db.flush()

    r = await client.get(
        "/api/finance/expenses",
        params={"month": "2026-01-01"},
        headers=auth_owner,
    )
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert str(exp_jan.id) in ids
    assert str(exp_jun.id) not in ids


async def test_filter_by_kind(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    exp_fijo = _make_db_expense(tenant, kind="fijo", status="confirmed")
    exp_var = _make_db_expense(tenant, kind="variable", status="confirmed")
    db.add_all([exp_fijo, exp_var])
    await db.flush()

    r = await client.get(
        "/api/finance/expenses",
        params={"kind": "fijo"},
        headers=auth_owner,
    )
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert str(exp_fijo.id) in ids
    assert str(exp_var.id) not in ids


async def test_filter_by_status(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    exp_draft = _make_db_expense(tenant, status="draft")
    exp_conf = _make_db_expense(tenant, status="confirmed")
    db.add_all([exp_draft, exp_conf])
    await db.flush()

    r = await client.get(
        "/api/finance/expenses",
        params={"status": "draft"},
        headers=auth_owner,
    )
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert str(exp_draft.id) in ids
    assert str(exp_conf.id) not in ids


# ── Cross-branch 403 ──────────────────────────────────────────────────────────


async def test_cross_branch_403(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    branch_b,
    user_asesor: User,
) -> None:
    """Asesor con permiso SOLO en branch_b no puede crear gasto en branch central."""
    from app.models.tenant import Branch
    # grant access to branch_b only
    from app.models.finance import FinancePermission
    perm = FinancePermission(
        tenant_id=tenant.id,
        user_id=user_asesor.id,
        branch_id=branch_b.id,
        granted_by=user_owner.id,
    )
    db.add(perm)
    await db.flush()

    # branch fixture (branch_central) has different id than branch_b
    # asesor tries to create expense associated with branch_b — should be OK
    # but branch_central (branch) would fail → let's verify with a random branch_id not in permissions
    random_branch_id = uuid.uuid4()
    r = await client.post(
        "/api/finance/expenses",
        json={"amount": 100, "kind": "fijo", "branch_id": str(random_branch_id)},
        headers={"Authorization": f"Bearer {_token(user_asesor)}"},
    )
    assert r.status_code == 403


# ── confirm ───────────────────────────────────────────────────────────────────


async def test_confirm_expense_changes_status(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    exp = _make_db_expense(tenant, status="draft")
    db.add(exp)
    await db.flush()

    r = await client.post(
        f"/api/finance/expenses/{exp.id}/confirm",
        headers=auth_owner,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


async def test_confirm_expense_adjusts_amount(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    exp = _make_db_expense(tenant, amount=100.0, status="draft")
    db.add(exp)
    await db.flush()

    r = await client.post(
        f"/api/finance/expenses/{exp.id}/confirm",
        json={"amount": 999.99},
        headers=auth_owner,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "confirmed"
    assert float(data["amount"]) == pytest.approx(999.99)


# ── confirm-all ───────────────────────────────────────────────────────────────


async def test_confirm_all_only_affects_own_tenant(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    """confirm-all solo confirma drafts del tenant del usuario autenticado."""
    # tenant_a (user_owner's tenant) — 2 drafts
    exp_a1 = _make_db_expense(tenant, status="draft")
    exp_a2 = _make_db_expense(tenant, status="draft")
    db.add_all([exp_a1, exp_a2])

    # tenant_b (diferente) — 1 draft directo en BD
    tenant_b = await _make_tenant(db, "B")
    exp_b = Expense(
        tenant_id=tenant_b.id,
        amount=500,
        kind="fijo",
        currency="MXN",
        incurred_at=date.today(),
        status="draft",
        source="manual",
    )
    db.add(exp_b)
    await db.flush()

    r = await client.post("/api/finance/expenses/confirm-all", headers=auth_owner)
    assert r.status_code == 200
    assert r.json()["updated"] == 2

    # tenant_b's expense must still be draft
    await db.refresh(exp_b)
    assert exp_b.status == "draft"


# ── delete ────────────────────────────────────────────────────────────────────


async def test_delete_expense_gives_404_after(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    exp = _make_db_expense(tenant, status="confirmed")
    db.add(exp)
    await db.flush()
    exp_id = str(exp.id)

    r_del = await client.delete(f"/api/finance/expenses/{exp_id}", headers=auth_owner)
    assert r_del.status_code == 204

    # Verify it's gone from the list
    r_list = await client.get(
        "/api/finance/expenses",
        headers=auth_owner,
    )
    ids = [e["id"] for e in r_list.json()]
    assert exp_id not in ids
