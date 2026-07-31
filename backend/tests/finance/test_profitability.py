"""Profitability + run-rate: cálculos, semáforo, suggest_goal_split."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal
from app.models.finance import Expense
from app.models.goals import MonthlyGoal
from app.models.tenant import Tenant
from app.models.user import User
from tests.finance.conftest import (
    _token,
    make_lead,
    make_pipeline_and_stage,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _current_period() -> tuple[int, int]:
    today = date.today()
    return today.year, today.month


async def _create_goal(client, auth, amount: float, *, is_draft: bool = False) -> dict:
    year, month = _current_period()
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


async def _make_won_deal(
    db: AsyncSession,
    tenant: Tenant,
    owner: User,
    branch,
    *,
    amount: float,
    cost_amount: float = 0.0,
    updated_at: datetime | None = None,
) -> Deal:
    lead = await make_lead(db, tenant, branch)
    _, stage = await make_pipeline_and_stage(db, tenant, branch)
    deal = Deal(
        tenant_id=tenant.id,
        lead_id=lead.id,
        pipeline_stage_id=stage.id,
        title="Deal test",
        amount=Decimal(str(amount)),
        cost_amount=Decimal(str(cost_amount)),
        is_won=True,
        owner_id=owner.id,
    )
    if updated_at is not None:
        deal.updated_at = updated_at
    db.add(deal)
    await db.flush()
    return deal


# ── run-rate: relaciones matemáticas ─────────────────────────────────────────


async def test_run_rate_calculation(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    branch,
    auth_owner: dict,
) -> None:
    """meta=$50k, vendido=$30k → verificar expected_today, gap, status, run_rate."""
    year, month = _current_period()
    await _create_goal(client, auth_owner, 50000.0)

    await _make_won_deal(db, tenant, user_owner, branch, amount=30000.0)

    r = await client.get(
        "/api/finance/run-rate",
        params={"year": year, "month": month},
        headers=auth_owner,
    )
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["won_revenue"] == pytest.approx(30000.0)
    assert d["goal_amount"] == pytest.approx(50000.0)
    assert d["gap"] == pytest.approx(20000.0)

    # run_rate debe satisfacer la proporción días
    expected_rr = 30000.0 * d["total_days"] / d["elapsed_days"]
    assert d["run_rate"] == pytest.approx(expected_rr, rel=0.01)

    # expected_today = goal * elapsed / total
    expected_today = 50000.0 * d["elapsed_days"] / d["total_days"]
    assert d["expected_today"] == pytest.approx(expected_today, rel=0.01)

    # status: semáforo basado en pct_of_goal
    assert d["status"] in ("green", "yellow", "red")
    pct = d["pct_of_goal"]
    if pct >= 100:
        assert d["status"] == "green"
    elif pct >= 70:
        assert d["status"] == "yellow"
    else:
        assert d["status"] == "red"

    # recommendations is a list, max 3
    assert isinstance(d["recommendations"], list)
    assert len(d["recommendations"]) <= 3

    # sold_by_deal_type es un dict
    assert isinstance(d["sold_by_deal_type"], dict)


async def test_run_rate_no_goal_no_pct(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    branch,
    auth_owner: dict,
) -> None:
    """Sin meta definida, pct_of_goal=None y status='red'."""
    year, month = _current_period()
    await _make_won_deal(db, tenant, user_owner, branch, amount=10000.0)

    r = await client.get(
        "/api/finance/run-rate",
        params={"year": year, "month": month},
        headers=auth_owner,
    )
    assert r.status_code == 200
    d = r.json()
    assert d["pct_of_goal"] is None
    assert d["goal_amount"] is None
    assert d["status"] == "red"
    # sin meta, primera recomendación habla de definir meta
    assert len(d["recommendations"]) >= 1
    assert "meta" in d["recommendations"][0].lower()


# ── profitability: profit = revenue - expenses (SIN cost_amount) ──────────────


async def test_profitability_excludes_cost_amount(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    branch,
    auth_owner: dict,
) -> None:
    """profit = revenue - expenses. cost_amount NO debe restarse (prompt 11b)."""
    year, month = _current_period()

    # Deal: amount=$1000, cost_amount=$500 (cost_amount should be ignored)
    await _make_won_deal(db, tenant, user_owner, branch, amount=1000.0, cost_amount=500.0)

    # Expense confirmada: $200
    exp = Expense(
        tenant_id=tenant.id,
        amount=Decimal("200"),
        kind="variable",
        currency="MXN",
        incurred_at=date.today(),
        status="confirmed",
        source="manual",
    )
    db.add(exp)
    await db.flush()

    r = await client.get(
        "/api/finance/profitability",
        params={"year": year, "month": month},
        headers=auth_owner,
    )
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["revenue"] == pytest.approx(1000.0)
    assert d["expenses"] == pytest.approx(200.0)
    # profit = 1000 - 200 = 800 (NOT 1000 - 500 - 200 = 300)
    assert d["profit"] == pytest.approx(800.0)
    assert d["profit_pct"] == pytest.approx(80.0, rel=0.01)
    assert "deal_costs" not in d
    assert "total_costs" not in d


# ── suggest_goal_split ────────────────────────────────────────────────────────


async def test_suggest_goal_split_proportional(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    user_asesor: User,
    branch,
    auth_owner: dict,
) -> None:
    """user_owner vendió $8k, user_asesor $2k → reparto 80%/20%."""
    # Deals dentro de la ventana de 3 meses (antes del inicio del mes actual)
    past_date = datetime(2026, 6, 15, tzinfo=timezone.utc)
    await _make_won_deal(db, tenant, user_owner, branch, amount=8000.0, updated_at=past_date)

    lead2 = await make_lead(db, tenant, branch)
    _, stage2 = await make_pipeline_and_stage(db, tenant, branch)
    deal2 = Deal(
        tenant_id=tenant.id,
        lead_id=lead2.id,
        pipeline_stage_id=stage2.id,
        title="Deal asesor",
        amount=Decimal("2000"),
        is_won=True,
        owner_id=user_asesor.id,
        updated_at=past_date,
    )
    db.add(deal2)
    await db.flush()

    r = await client.get(
        "/api/finance/goal-split-suggestion",
        params={
            "dimension": "global",
            "user_ids": [str(user_owner.id), str(user_asesor.id)],
        },
        headers=auth_owner,
    )
    assert r.status_code == 200, r.text
    result = r.json()

    assert str(user_owner.id) in result
    assert str(user_asesor.id) in result
    assert result[str(user_owner.id)] == pytest.approx(80.0, rel=0.01)
    assert result[str(user_asesor.id)] == pytest.approx(20.0, rel=0.01)


async def test_suggest_goal_split_equal_when_no_sales(
    client: AsyncClient,
    tenant: Tenant,
    user_owner: User,
    user_asesor: User,
    auth_owner: dict,
) -> None:
    """Si ningún usuario vendió en la ventana → reparto equitativo 50%/50%."""
    # No deals created — nobody sold anything
    r = await client.get(
        "/api/finance/goal-split-suggestion",
        params={
            "dimension": "global",
            "user_ids": [str(user_owner.id), str(user_asesor.id)],
        },
        headers=auth_owner,
    )
    assert r.status_code == 200, r.text
    result = r.json()
    total = sum(result.values())
    # Both users should have equal shares
    for uid_str, pct in result.items():
        assert pct == pytest.approx(50.0, rel=0.01)


# ── Acceso cross-user: asesor no puede ver run-rate de otro usuario ────────────


async def test_cross_user_run_rate_403(
    client: AsyncClient,
    user_owner: User,
    user_asesor: User,
    auth_asesor: dict,
) -> None:
    """Asesor intentando ver run-rate de otro usuario → 403."""
    r = await client.get(
        f"/api/finance/run-rate/users/{user_owner.id}",
        headers=auth_asesor,
    )
    assert r.status_code == 403


async def test_user_can_see_own_run_rate(
    client: AsyncClient,
    user_asesor: User,
    auth_asesor: dict,
) -> None:
    """Asesor puede ver su propio run-rate sin necesitar FinancePermission."""
    year, month = _current_period()
    r = await client.get(
        f"/api/finance/run-rate/users/{user_asesor.id}",
        params={"year": year, "month": month},
        headers=auth_asesor,
    )
    assert r.status_code == 200


async def test_goal_split_suggestion_requires_owner(
    client: AsyncClient,
    user_owner: User,
    user_asesor: User,
    auth_asesor: dict,
) -> None:
    """goal-split-suggestion requiere rol OWNER."""
    r = await client.get(
        "/api/finance/goal-split-suggestion",
        params={"dimension": "global", "user_ids": [str(user_owner.id)]},
        headers=auth_asesor,
    )
    assert r.status_code == 403
