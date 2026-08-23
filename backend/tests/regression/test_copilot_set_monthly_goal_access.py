"""
Regresión — Copiloto: acceso a finanzas + unificación de lógica en
set_monthly_goal (hallazgo #6, docs/PERMISSIONS_DRIFT_BACKLOG.md).

Código auditado:
  - app/ai/copilot_tools.py::execute_tool, rama "set_monthly_goal" — ahora
    llama require_finance_access(user, None, db) ANTES del flujo
    confirmed=bool, para no revelar el mensaje de confirmación (con el
    monto) a un usuario sin acceso a finanzas.
  - app/services/goals_service.py::upsert_monthly_goal — lógica de negocio
    compartida con app/api/goals.py::create_or_update_monthly_goal; el
    acceso NO se valida ahí, es responsabilidad del caller.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_tools import execute_tool
from app.models.finance import FinancePermission
from app.models.goals import MonthlyGoal, MonthlyGoalHistory
from app.models.tenant import Tenant
from app.models.user import User


# ── ASESOR sin FinancePermission — denegado, sin side-effects en BD ────────────

async def test_asesor_without_finance_permission_denied_and_creates_nothing(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    result = await execute_tool(
        "set_monthly_goal",
        {"total": 50000, "confirmed": True},
        asesor_user, tenant, db,
    )
    assert result == {"error": "No tienes acceso a finanzas"}

    rows = (await db.execute(
        select(MonthlyGoal).where(MonthlyGoal.tenant_id == tenant.id)
    )).scalars().all()
    assert rows == [], "No debe crearse ningún MonthlyGoal cuando el acceso se deniega"


# ── OWNER — bypass por rol, sin fila en FinancePermission ──────────────────────

async def test_owner_can_set_goal_without_finance_permission_row(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    result = await execute_tool(
        "set_monthly_goal",
        {"total": 50000, "confirmed": True},
        owner_user, tenant, db,
    )
    assert result["set"] is True
    assert result["action"] == "created"


# ── ASESOR con FinancePermission tenant-wide — permitido ───────────────────────

async def test_asesor_with_tenant_wide_finance_permission_can_set_goal(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    db.add(FinancePermission(tenant_id=tenant.id, branch_id=None, user_id=asesor_user.id))
    await db.flush()

    result = await execute_tool(
        "set_monthly_goal",
        {"total": 75000, "confirmed": True},
        asesor_user, tenant, db,
    )
    assert result["set"] is True
    assert result["action"] == "created"


# ── Orden: acceso se chequea ANTES de revelar pending_confirmation ─────────────

async def test_access_denied_before_pending_confirmation_is_revealed(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    """confirmed=False + sin acceso → debe devolver el error de acceso, NO el
    mensaje de confirmación con el monto (que filtraría el monto solicitado
    a alguien que no debería poder verlo)."""
    result = await execute_tool(
        "set_monthly_goal",
        {"total": 999999, "confirmed": False},
        asesor_user, tenant, db,
    )
    assert result == {"error": "No tienes acceso a finanzas"}
    assert "pending_confirmation" not in result
    assert "amount_requested_mxn" not in result


async def test_pending_confirmation_still_returned_when_access_allowed(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    result = await execute_tool(
        "set_monthly_goal",
        {"total": 12345, "confirmed": False},
        owner_user, tenant, db,
    )
    assert result["pending_confirmation"] is True
    assert result["amount_requested_mxn"] == 12345.0

    rows = (await db.execute(
        select(MonthlyGoal).where(MonthlyGoal.tenant_id == tenant.id)
    )).scalars().all()
    assert rows == [], "confirmed=False no debe crear ni modificar ningún MonthlyGoal"


# ── Upsert real: crear y luego actualizar, historial completo ──────────────────

async def test_upsert_real_create_then_update_records_full_history(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    created = await execute_tool(
        "set_monthly_goal",
        {"total": 100000, "confirmed": True},
        owner_user, tenant, db,
    )
    assert created["set"] is True
    assert created["action"] == "created"
    goal_id = created["goal_id"]

    updated = await execute_tool(
        "set_monthly_goal",
        {"total": 150000, "confirmed": True},
        owner_user, tenant, db,
    )
    assert updated["set"] is True
    assert updated["action"] == "updated"
    assert updated["goal_id"] == goal_id, "El upsert debe reutilizar la misma meta global del periodo"

    goal = (await db.execute(
        select(MonthlyGoal).where(MonthlyGoal.id == goal_id)
    )).scalar_one()
    assert float(goal.amount) == 150000.0
    assert goal.currency == "MXN"
    assert goal.dimension == "global"
    assert goal.is_draft is False

    history = (await db.execute(
        select(MonthlyGoalHistory)
        .where(MonthlyGoalHistory.goal_id == goal_id)
        .order_by(MonthlyGoalHistory.action)
    )).scalars().all()
    actions = sorted(h.action for h in history)
    assert actions == ["goal_created", "goal_updated"]
