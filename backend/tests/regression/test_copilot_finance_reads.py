"""
Regresión — Copiloto: Ronda 1 de la expansión de Finanzas/Gastos (7 tools de
lectura wireadas al catálogo).

Código auditado:
  - app/ai/copilot_tools.py::execute_tool, ramas "list_expenses",
    "list_expense_categories", "list_recurring_expenses",
    "list_expense_rules", "list_product_categories", "list_goal_assignments"
    — replican la query de su endpoint REST equivalente
    (app/api/finance.py, app/api/goals.py), con
    require_finance_access(user, branch_id, db) antes de ejecutar
    (branch_id=None salvo list_expenses, que usa el branch_id del filtro,
    igual que finance.py::list_expenses).
  - app/ai/copilot_tools.py::execute_tool, rama "list_finance_permissions"
    — usa check_permission + ACTIONS["list_finance_permissions"]
    (required_role=_OWNER_TIER), NO require_finance_access, igual que su
    endpoint REST real (_require_owner, no _require_finance_access).
  - app/copilot/actions_catalog.py — las 7 agregadas a _LOW_RISK con
    _wired(); list_finance_permissions con required_role=_OWNER_TIER, las
    otras 6 con _ALL_ROLES (el gate real es require_finance_access dentro
    del dispatcher).

No repite la matriz completa de branch-scoped/tenant-wide de
test_copilot_finance_access.py — esa ya cubre el comportamiento de
require_finance_access a fondo con las 3 tools preexistentes. Acá solo se
confirma que las 6 tools nuevas SÍ están aplicando ese mismo chequeo (1-2
casos por acción), más filtrado real por acción y los casos específicos de
list_finance_permissions/list_goal_assignments pedidos en el prompt.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_tools import execute_tool
from app.models.finance import Expense, ExpenseCategory, ExpenseRule, FinancePermission, RecurringExpense
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment, ProductCategory
from app.models.tenant import Branch, Tenant
from app.models.user import User

_FINANCE_ACCESS_TOOLS = (
    "list_expenses",
    "list_expense_categories",
    "list_recurring_expenses",
    "list_expense_rules",
    "list_product_categories",
    "list_goal_assignments",
)


async def _seed_goal(db: AsyncSession, tenant: Tenant) -> MonthlyGoal:
    goal = MonthlyGoal(
        tenant_id=tenant.id, period_year=2026, period_month=8,
        amount=Decimal("100000"), dimension="global",
    )
    db.add(goal)
    await db.flush()
    return goal


# ── OWNER puede listar las 7 sin restricción ────────────────────────────────────

async def test_owner_can_use_all_seven_finance_read_tools(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    goal = await _seed_goal(db, tenant)

    for tool_name, extra_args in (
        ("list_expenses", {}),
        ("list_expense_categories", {}),
        ("list_recurring_expenses", {}),
        ("list_expense_rules", {}),
        ("list_product_categories", {}),
        ("list_goal_assignments", {"goal_id": str(goal.id)}),
        ("list_finance_permissions", {}),
    ):
        result = await execute_tool(tool_name, extra_args, owner_user, tenant, db)
        assert "error" not in result, f"{tool_name}: {result}"


# ── ASESOR sin FinancePermission — denegado en las 6 que usan require_finance_access ──

async def test_asesor_without_finance_permission_denied_on_six_tools(
    db: AsyncSession, tenant: Tenant, owner_user: User, asesor_user: User,
) -> None:
    goal = await _seed_goal(db, tenant)

    for tool_name, extra_args in (
        ("list_expenses", {}),
        ("list_expense_categories", {}),
        ("list_recurring_expenses", {}),
        ("list_expense_rules", {}),
        ("list_product_categories", {}),
        ("list_goal_assignments", {"goal_id": str(goal.id)}),
    ):
        result = await execute_tool(tool_name, extra_args, asesor_user, tenant, db)
        assert result == {"error": "No tienes acceso a finanzas"}, f"{tool_name}: {result}"


async def test_asesor_with_tenant_wide_finance_permission_allowed_on_six_tools(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    db.add(FinancePermission(tenant_id=tenant.id, branch_id=None, user_id=asesor_user.id))
    await db.flush()
    goal = await _seed_goal(db, tenant)

    for tool_name, extra_args in (
        ("list_expenses", {}),
        ("list_expense_categories", {}),
        ("list_recurring_expenses", {}),
        ("list_expense_rules", {}),
        ("list_product_categories", {}),
        ("list_goal_assignments", {"goal_id": str(goal.id)}),
    ):
        result = await execute_tool(tool_name, extra_args, asesor_user, tenant, db)
        assert "error" not in result, f"{tool_name}: {result}"


# ── list_finance_permissions: ASESOR con acceso a finanzas SIGUE denegado ──────

async def test_asesor_with_finance_permission_still_denied_on_list_finance_permissions(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    """A diferencia de las otras 6, esta usa _OWNER_TIER — tener acceso de
    lectura a finanzas (FinancePermission) no habilita ver QUIÉN tiene ese
    acceso, solo OWNER/PLATFORM_OWNER pueden."""
    db.add(FinancePermission(tenant_id=tenant.id, branch_id=None, user_id=asesor_user.id))
    await db.flush()

    result = await execute_tool("list_finance_permissions", {}, asesor_user, tenant, db)
    assert "error" in result


# ── list_goal_assignments con goal_id inexistente / de otro tenant ─────────────

async def test_list_goal_assignments_nonexistent_goal_returns_error(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    result = await execute_tool(
        "list_goal_assignments", {"goal_id": str(uuid.uuid4())}, owner_user, tenant, db,
    )
    assert "error" in result


async def test_list_goal_assignments_other_tenant_goal_returns_error(
    db: AsyncSession, tenant: Tenant, owner_user: User, other_tenant_ctx: dict,
) -> None:
    other_goal = await _seed_goal(db, other_tenant_ctx["tenant"])
    result = await execute_tool(
        "list_goal_assignments", {"goal_id": str(other_goal.id)}, owner_user, tenant, db,
    )
    assert "error" in result


async def test_list_goal_assignments_invalid_uuid_returns_error(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    result = await execute_tool(
        "list_goal_assignments", {"goal_id": "not-a-uuid"}, owner_user, tenant, db,
    )
    assert "error" in result


# ── Filtrado real por acción ─────────────────────────────────────────────────────

async def test_list_expenses_filters_by_kind(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    db.add(Expense(tenant_id=tenant.id, amount=Decimal("500"), kind="fijo"))
    db.add(Expense(tenant_id=tenant.id, amount=Decimal("200"), kind="variable"))
    await db.flush()

    result = await execute_tool("list_expenses", {"kind": "fijo"}, owner_user, tenant, db)
    assert "error" not in result
    assert len(result) == 1
    assert result[0]["kind"] == "fijo"


async def test_list_expense_categories_excludes_inactive_by_default(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    db.add(ExpenseCategory(tenant_id=tenant.id, name="Renta", kind="fijo", is_active=True))
    db.add(ExpenseCategory(tenant_id=tenant.id, name="Vieja", kind="fijo", is_active=False))
    await db.flush()

    default_result = await execute_tool("list_expense_categories", {}, owner_user, tenant, db)
    assert [c["name"] for c in default_result] == ["Renta"]

    all_result = await execute_tool(
        "list_expense_categories", {"include_inactive": True}, owner_user, tenant, db,
    )
    assert {c["name"] for c in all_result} == {"Renta", "Vieja"}


async def test_list_recurring_expenses_excludes_inactive_by_default(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    db.add(RecurringExpense(tenant_id=tenant.id, amount=Decimal("1000"), is_active=True))
    db.add(RecurringExpense(tenant_id=tenant.id, amount=Decimal("2000"), is_active=False))
    await db.flush()

    default_result = await execute_tool("list_recurring_expenses", {}, owner_user, tenant, db)
    assert len(default_result) == 1

    all_result = await execute_tool(
        "list_recurring_expenses", {"include_inactive": True}, owner_user, tenant, db,
    )
    assert len(all_result) == 2


async def test_list_expense_rules_excludes_inactive_by_default(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    db.add(ExpenseRule(
        tenant_id=tenant.id, name="Comisión", rule_type="percent_of_deal",
        value=Decimal("10"), is_active=True,
    ))
    db.add(ExpenseRule(
        tenant_id=tenant.id, name="Vieja", rule_type="fixed_per_deal",
        value=Decimal("50"), is_active=False,
    ))
    await db.flush()

    default_result = await execute_tool("list_expense_rules", {}, owner_user, tenant, db)
    assert len(default_result) == 1

    all_result = await execute_tool(
        "list_expense_rules", {"include_inactive": True}, owner_user, tenant, db,
    )
    assert len(all_result) == 2


async def test_list_product_categories_excludes_inactive_by_default(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    db.add(ProductCategory(tenant_id=tenant.id, name="Software", is_active=True))
    db.add(ProductCategory(tenant_id=tenant.id, name="Descontinuada", is_active=False))
    await db.flush()

    default_result = await execute_tool("list_product_categories", {}, owner_user, tenant, db)
    assert [c["name"] for c in default_result] == ["Software"]

    all_result = await execute_tool(
        "list_product_categories", {"include_inactive": True}, owner_user, tenant, db,
    )
    assert {c["name"] for c in all_result} == {"Software", "Descontinuada"}


async def test_list_goal_assignments_only_returns_rows_for_requested_goal(
    db: AsyncSession, tenant: Tenant, owner_user: User, asesor_user: User,
) -> None:
    goal_a = await _seed_goal(db, tenant)
    goal_b = MonthlyGoal(
        tenant_id=tenant.id, period_year=2026, period_month=9,
        amount=Decimal("50000"), dimension="global",
    )
    db.add(goal_b)
    await db.flush()

    db.add(MonthlyGoalAssignment(
        goal_id=goal_a.id, tenant_id=tenant.id, user_id=owner_user.id,
        share_percent=Decimal("100"), amount=Decimal("100000"),
    ))
    db.add(MonthlyGoalAssignment(
        goal_id=goal_b.id, tenant_id=tenant.id, user_id=asesor_user.id,
        share_percent=Decimal("100"), amount=Decimal("50000"),
    ))
    await db.flush()

    result = await execute_tool(
        "list_goal_assignments", {"goal_id": str(goal_a.id)}, owner_user, tenant, db,
    )
    assert len(result) == 1
    assert result[0]["user_id"] == str(owner_user.id)


async def test_list_finance_permissions_does_not_leak_other_tenant_rows(
    db: AsyncSession, tenant: Tenant, owner_user: User, other_tenant_ctx: dict,
) -> None:
    other_tenant = other_tenant_ctx["tenant"]
    other_user = other_tenant_ctx["user"]
    db.add(FinancePermission(tenant_id=other_tenant.id, branch_id=None, user_id=other_user.id))
    await db.flush()

    result = await execute_tool("list_finance_permissions", {}, owner_user, tenant, db)
    assert "error" not in result
    assert all(row["tenant_id"] == str(tenant.id) for row in result)


# ── list_expenses: FinancePermission scoped a un branch específico ────────────

async def test_list_expenses_branch_scoped_permission_allows_matching_branch(
    db: AsyncSession, tenant: Tenant, branch: Branch, asesor_user: User,
) -> None:
    other_branch = Branch(
        company_id=branch.company_id, tenant_id=tenant.id,
        name="Otra Sucursal", is_active=True,
    )
    db.add(other_branch)
    await db.flush()

    db.add(FinancePermission(tenant_id=tenant.id, branch_id=other_branch.id, user_id=asesor_user.id))
    await db.flush()

    result = await execute_tool(
        "list_expenses", {"branch_id": str(other_branch.id)}, asesor_user, tenant, db,
    )
    assert "error" not in result


async def test_list_expenses_branch_scoped_permission_denies_different_branch(
    db: AsyncSession, tenant: Tenant, branch: Branch, asesor_user: User,
) -> None:
    other_branch = Branch(
        company_id=branch.company_id, tenant_id=tenant.id,
        name="Otra Sucursal", is_active=True,
    )
    db.add(other_branch)
    await db.flush()

    db.add(FinancePermission(tenant_id=tenant.id, branch_id=other_branch.id, user_id=asesor_user.id))
    await db.flush()

    result = await execute_tool(
        "list_expenses", {"branch_id": str(branch.id)}, asesor_user, tenant, db,
    )
    assert result == {"error": "No tienes acceso a finanzas"}
