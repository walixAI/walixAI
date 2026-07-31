"""Finance — recurring_expenses, expense_rules y generación automática."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal
from app.models.finance import Expense, ExpenseRule, RecurringExpense
from app.models.tenant import Tenant
from app.models.user import User
from app.services.expense_generation import generate_deal_expense_drafts, generate_recurring_expenses
from tests.finance.conftest import (
    grant_finance_access,
    make_lead,
    make_pipeline_and_stage,
)


# ── Recurring expenses — CRUD + 403 ──────────────────────────────────────────


async def test_create_recurring_expense(
    client: AsyncClient, auth_owner: dict
) -> None:
    r = await client.post(
        "/api/finance/recurring-expenses",
        json={"amount": 3500.0, "day_of_month": 1, "description": "Renta mensual"},
        headers=auth_owner,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert float(data["amount"]) == 3500.0
    assert data["day_of_month"] == 1
    assert data["is_active"] is True


async def test_403_recurring_without_permission(
    client: AsyncClient, auth_asesor: dict
) -> None:
    r = await client.get("/api/finance/recurring-expenses", headers=auth_asesor)
    assert r.status_code == 403


async def test_delete_recurring_sets_null_on_expense(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    """ON DELETE SET NULL: borrar la RecurringExpense pone recurring_id=NULL en el Expense."""
    rec = RecurringExpense(
        tenant_id=tenant.id,
        amount=Decimal("500"),
        day_of_month=1,
        is_active=True,
    )
    db.add(rec)
    await db.flush()

    exp = Expense(
        tenant_id=tenant.id,
        amount=Decimal("500"),
        kind="fijo",
        currency="MXN",
        incurred_at=date.today(),
        status="confirmed",
        source="recurring",
        recurring_id=rec.id,
    )
    db.add(exp)
    await db.flush()
    exp_id = exp.id

    r = await client.delete(f"/api/finance/recurring-expenses/{rec.id}", headers=auth_owner)
    assert r.status_code == 204

    # Expense sigue existiendo con recurring_id=NULL
    await db.refresh(exp)
    assert exp.recurring_id is None
    assert exp.id == exp_id


# ── Expense rules — CRUD ──────────────────────────────────────────────────────


async def test_create_expense_rule(
    client: AsyncClient, auth_owner: dict
) -> None:
    r = await client.post(
        "/api/finance/expense-rules",
        json={
            "name": "Comisión 10%",
            "rule_type": "percent_of_deal",
            "value": 10.0,
            "auto_confirm": False,
        },
        headers=auth_owner,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Comisión 10%"
    assert float(data["value"]) == 10.0
    assert data["is_active"] is True


async def test_delete_rule_sets_null_on_expense(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    auth_owner: dict,
) -> None:
    """ON DELETE SET NULL: borrar la ExpenseRule pone rule_id=NULL en el Expense."""
    rule = ExpenseRule(
        tenant_id=tenant.id,
        name="Comisión temporal",
        rule_type="percent_of_deal",
        value=Decimal("5"),
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    exp = Expense(
        tenant_id=tenant.id,
        amount=Decimal("50"),
        kind="variable",
        currency="MXN",
        incurred_at=date.today(),
        status="draft",
        source="rule",
        rule_id=rule.id,
    )
    db.add(exp)
    await db.flush()
    exp_id = exp.id

    r = await client.delete(f"/api/finance/expense-rules/{rule.id}", headers=auth_owner)
    assert r.status_code == 204

    await db.refresh(exp)
    assert exp.rule_id is None
    assert exp.id == exp_id


# ── Generación automática (servicio directo) ──────────────────────────────────


async def test_generate_deal_expense_rule_match(
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    branch,
) -> None:
    """ExpenseRule 10% en deal de $1,000 → Expense draft de $100."""
    rule = ExpenseRule(
        tenant_id=tenant.id,
        name="Comisión 10%",
        rule_type="percent_of_deal",
        value=Decimal("10"),
        auto_confirm=False,
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    lead = await make_lead(db, tenant, branch)
    _, stage = await make_pipeline_and_stage(db, tenant, branch)

    deal = Deal(
        tenant_id=tenant.id,
        lead_id=lead.id,
        pipeline_stage_id=stage.id,
        title="Venta prueba",
        amount=Decimal("1000"),
        is_won=True,
        owner_id=user_owner.id,
    )
    db.add(deal)
    await db.flush()

    created = await generate_deal_expense_drafts(deal, db)
    await db.flush()

    assert len(created) == 1
    exp = created[0]
    assert float(exp.amount) == pytest.approx(100.0)
    assert exp.status == "draft"
    assert exp.source == "rule"
    assert exp.rule_id == rule.id


async def test_generate_deal_type_filter_no_match(
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    branch,
) -> None:
    """Regla con deal_type_filter='Servicio' no genera gasto en deal de tipo 'Venta'."""
    rule = ExpenseRule(
        tenant_id=tenant.id,
        name="Comisión servicios",
        rule_type="percent_of_deal",
        value=Decimal("5"),
        deal_type_filter="Servicio",
        auto_confirm=False,
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    lead = await make_lead(db, tenant, branch)
    _, stage = await make_pipeline_and_stage(db, tenant, branch, stage_name="Negociacion")

    deal = Deal(
        tenant_id=tenant.id,
        lead_id=lead.id,
        pipeline_stage_id=stage.id,
        title="Venta equipo",
        amount=Decimal("2000"),
        deal_type="Venta",
        is_won=True,
        owner_id=user_owner.id,
    )
    db.add(deal)
    await db.flush()

    created = await generate_deal_expense_drafts(deal, db)
    assert created == []


async def test_generate_recurring_idempotent(
    client: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    user_owner: User,
    auth_owner: dict,
) -> None:
    """Llamar generate-recurring dos veces en el mismo mes solo genera 1 Expense."""
    rec = RecurringExpense(
        tenant_id=tenant.id,
        amount=Decimal("1200"),
        day_of_month=1,
        description="Seguro mensual",
        is_active=True,
    )
    db.add(rec)
    await db.flush()
    # Necesitamos commit para que generate_recurring_expenses pueda ver el registro
    # (la función hace su propio query). En SAVEPOINT mode, flush es suficiente.
    # generate_recurring_expenses llama db.commit() internamente.

    r1 = await client.post("/api/finance/recurring-expenses/generate", headers=auth_owner)
    assert r1.status_code == 200
    assert r1.json()["generated"] >= 1

    # Segunda llamada — debe retornar 0 (idempotente)
    r2 = await client.post("/api/finance/recurring-expenses/generate", headers=auth_owner)
    assert r2.status_code == 200
    assert r2.json()["generated"] == 0
