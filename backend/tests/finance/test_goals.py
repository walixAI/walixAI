"""Goals — product_categories, monthly_goals, assignments."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goals import MonthlyGoal, MonthlyGoalAssignment, MonthlyGoalHistory, ProductCategory
from app.models.tenant import Tenant
from app.models.user import User
from tests.finance.conftest import grant_finance_access


# ── Helpers ───────────────────────────────────────────────────────────────────


def _current_period() -> tuple[int, int]:
    today = date.today()
    return today.year, today.month


def _next_month_period() -> tuple[int, int]:
    today = date.today()
    if today.month == 12:
        return today.year + 1, 1
    return today.year, today.month + 1


# ── product_categories — 403 + CRUD ──────────────────────────────────────────


async def test_403_product_categories_without_access(
    client: AsyncClient, auth_asesor: dict
) -> None:
    r = await client.get("/api/goals/product-categories", headers=auth_asesor)
    assert r.status_code == 403


async def test_create_product_category(
    client: AsyncClient, auth_owner: dict
) -> None:
    r = await client.post(
        "/api/goals/product-categories",
        json={"name": "Consultas", "position": 0},
        headers=auth_owner,
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Consultas"
    assert r.json()["is_active"] is True


async def test_duplicate_category_name_409(
    client: AsyncClient, auth_owner: dict
) -> None:
    """Crear dos product_categories con el mismo nombre → 409 (no 500)."""
    payload = {"name": "Cirugías", "position": 1}
    r1 = await client.post("/api/goals/product-categories", json=payload, headers=auth_owner)
    assert r1.status_code == 201

    r2 = await client.post("/api/goals/product-categories", json=payload, headers=auth_owner)
    assert r2.status_code == 409


# ── monthly_goals — past period, upsert, validator ────────────────────────────


async def test_past_period_goal_raises_422(
    client: AsyncClient, auth_owner: dict
) -> None:
    """Crear meta con mes pasado → 422."""
    today = date.today()
    if today.month == 1:
        past_year, past_month = today.year - 1, 12
    else:
        past_year, past_month = today.year, today.month - 1

    r = await client.post(
        "/api/goals/monthly-goals",
        json={
            "period_year": past_year,
            "period_month": past_month,
            "amount": 10000,
            "dimension": "global",
        },
        headers=auth_owner,
    )
    assert r.status_code == 422


async def test_upsert_global_goal_no_duplicate(
    client: AsyncClient, auth_owner: dict
) -> None:
    """POST con la misma dimensión/periodo hace upsert, no duplica."""
    year, month = _current_period()
    payload = {
        "period_year": year,
        "period_month": month,
        "amount": 10000,
        "dimension": "global",
    }

    r1 = await client.post("/api/goals/monthly-goals", json=payload, headers=auth_owner)
    assert r1.status_code == 200  # first post creates

    payload["amount"] = 20000
    r2 = await client.post("/api/goals/monthly-goals", json=payload, headers=auth_owner)
    assert r2.status_code == 200  # second post updates existing
    assert float(r2.json()["amount"]) == 20000.0

    # Exactly one row for this period/dimension
    r_list = await client.get(
        "/api/goals/monthly-goals",
        params={"period_year": year, "period_month": month, "dimension": "global"},
        headers=auth_owner,
    )
    assert len(r_list.json()) == 1


async def test_validator_global_with_value_text_raises_422(
    client: AsyncClient, auth_owner: dict
) -> None:
    year, month = _current_period()
    r = await client.post(
        "/api/goals/monthly-goals",
        json={
            "period_year": year,
            "period_month": month,
            "amount": 5000,
            "dimension": "global",
            "dimension_value_text": "NoDebería",  # invalid for global
        },
        headers=auth_owner,
    )
    assert r.status_code == 422


async def test_validator_deal_type_without_text_raises_422(
    client: AsyncClient, auth_owner: dict
) -> None:
    year, month = _current_period()
    r = await client.post(
        "/api/goals/monthly-goals",
        json={
            "period_year": year,
            "period_month": month,
            "amount": 5000,
            "dimension": "deal_type",
            # missing dimension_value_text
        },
        headers=auth_owner,
    )
    assert r.status_code == 422


async def test_validator_pipeline_without_uuid_raises_422(
    client: AsyncClient, auth_owner: dict
) -> None:
    year, month = _current_period()
    r = await client.post(
        "/api/goals/monthly-goals",
        json={
            "period_year": year,
            "period_month": month,
            "amount": 5000,
            "dimension": "pipeline",
            # missing dimension_value_uuid
        },
        headers=auth_owner,
    )
    assert r.status_code == 422


# ── History ───────────────────────────────────────────────────────────────────


async def test_goal_history_on_create(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    year, month = _current_period()
    r = await client.post(
        "/api/goals/monthly-goals",
        json={"period_year": year, "period_month": month, "amount": 7500, "dimension": "global"},
        headers=auth_owner,
    )
    assert r.status_code == 200
    goal_id = uuid.UUID(r.json()["id"])

    rows = (await db.execute(
        select(MonthlyGoalHistory).where(MonthlyGoalHistory.goal_id == goal_id)
    )).scalars().all()
    assert len(rows) >= 1
    assert any(h.action == "goal_created" for h in rows)


async def test_goal_history_on_patch(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    year, month = _current_period()
    r_create = await client.post(
        "/api/goals/monthly-goals",
        json={"period_year": year, "period_month": month, "amount": 8000, "dimension": "global"},
        headers=auth_owner,
    )
    goal_id = r_create.json()["id"]

    await client.patch(
        f"/api/goals/monthly-goals/{goal_id}",
        json={"amount": 9000},
        headers=auth_owner,
    )

    rows = (await db.execute(
        select(MonthlyGoalHistory).where(MonthlyGoalHistory.goal_id == uuid.UUID(goal_id))
    )).scalars().all()
    assert any(h.action == "goal_updated" for h in rows)


# ── Assignments ───────────────────────────────────────────────────────────────


async def _create_goal(client, auth, year, month, amount=50000, is_draft=False) -> dict:
    r = await client.post(
        "/api/goals/monthly-goals",
        json={
            "period_year": year,
            "period_month": month,
            "amount": amount,
            "dimension": "global",
            "is_draft": is_draft,
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_assignments_sum_not_100_on_non_draft_raises_422(
    client: AsyncClient,
    user_owner: User,
    user_asesor: User,
    auth_owner: dict,
) -> None:
    year, month = _current_period()
    goal = await _create_goal(client, auth_owner, year, month, is_draft=False)

    r = await client.put(
        f"/api/goals/monthly-goals/{goal['id']}/assignments",
        json={"assignments": [{"user_id": str(user_owner.id), "share_percent": 60}]},
        headers=auth_owner,
    )
    assert r.status_code == 422


async def test_assignments_sum_not_100_on_draft_ok(
    client: AsyncClient,
    user_owner: User,
    auth_owner: dict,
) -> None:
    """Meta borrador acepta assignments cuya suma no sea 100."""
    year, month = _current_period()
    goal = await _create_goal(client, auth_owner, year, month, is_draft=True)

    r = await client.put(
        f"/api/goals/monthly-goals/{goal['id']}/assignments",
        json={"assignments": [{"user_id": str(user_owner.id), "share_percent": 60}]},
        headers=auth_owner,
    )
    assert r.status_code == 200, r.text


async def test_assignment_amount_calculation(
    client: AsyncClient,
    db: AsyncSession,
    user_owner: User,
    user_asesor: User,
    auth_owner: dict,
) -> None:
    """El amount de cada assignment = goal.amount * share_percent / 100."""
    year, month = _current_period()
    goal = await _create_goal(client, auth_owner, year, month, amount=50000, is_draft=False)

    r = await client.put(
        f"/api/goals/monthly-goals/{goal['id']}/assignments",
        json={"assignments": [
            {"user_id": str(user_owner.id), "share_percent": 60},
            {"user_id": str(user_asesor.id), "share_percent": 40},
        ]},
        headers=auth_owner,
    )
    assert r.status_code == 200, r.text
    assignments = {a["user_id"]: a for a in r.json()}

    assert float(assignments[str(user_owner.id)]["amount"]) == pytest.approx(30000.0)
    assert float(assignments[str(user_asesor.id)]["amount"]) == pytest.approx(20000.0)


async def test_put_assignments_replaces_previous(
    client: AsyncClient,
    user_owner: User,
    user_asesor: User,
    auth_owner: dict,
) -> None:
    """Un segundo PUT reemplaza completamente los assignments anteriores."""
    year, month = _current_period()
    goal = await _create_goal(client, auth_owner, year, month, is_draft=False)

    # First PUT: both users
    await client.put(
        f"/api/goals/monthly-goals/{goal['id']}/assignments",
        json={"assignments": [
            {"user_id": str(user_owner.id), "share_percent": 70},
            {"user_id": str(user_asesor.id), "share_percent": 30},
        ]},
        headers=auth_owner,
    )

    # Second PUT: only owner (removes asesor)
    r = await client.put(
        f"/api/goals/monthly-goals/{goal['id']}/assignments",
        json={"assignments": [{"user_id": str(user_owner.id), "share_percent": 100}]},
        headers=auth_owner,
    )
    assert r.status_code == 200
    user_ids = [a["user_id"] for a in r.json()]
    assert str(user_owner.id) in user_ids
    assert str(user_asesor.id) not in user_ids
