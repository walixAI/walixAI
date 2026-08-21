"""
Regresión — Copiloto: acceso a finanzas en get_profitability/get_run_rate/
get_expenses_summary (hallazgo #8, docs/PERMISSIONS_DRIFT_BACKLOG.md).

Código auditado:
  - app/copilot/finance_access.py::require_finance_access — replica
    app/api/finance.py::_require_finance_access (líneas 29-47), pero
    retorna (allowed, reason) en vez de levantar HTTPException.
  - app/ai/copilot_tools.py::execute_tool, ramas "get_profitability",
    "get_run_rate", "get_expenses_summary" — ahora llaman
    require_finance_access(user, None, db) antes de ejecutar. branch_id=None
    coincide con cómo profitability.py llama a _require_finance_access
    para sus endpoints equivalentes (líneas 91, 108).
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_tools import execute_tool
from app.models.finance import FinancePermission
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole

_FINANCE_TOOLS = ("get_profitability", "get_run_rate", "get_expenses_summary")


def _grant(tenant: Tenant, user: User, branch_id: uuid.UUID | None) -> FinancePermission:
    return FinancePermission(tenant_id=tenant.id, branch_id=branch_id, user_id=user.id)


# ── OWNER/PLATFORM_OWNER — bypass por rol, sin fila en FinancePermission ───────

async def test_owner_can_use_all_three_tools_without_finance_permission_row(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    for tool_name in _FINANCE_TOOLS:
        result = await execute_tool(tool_name, {}, owner_user, tenant, db)
        assert "error" not in result, f"{tool_name}: {result}"


async def test_platform_owner_can_use_all_three_tools_without_finance_permission_row(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    owner_user.role = UserRole.PLATFORM_OWNER  # solo en memoria, no se persiste
    for tool_name in _FINANCE_TOOLS:
        result = await execute_tool(tool_name, {}, owner_user, tenant, db)
        assert "error" not in result, f"{tool_name}: {result}"


# ── ASESOR sin fila en FinancePermission — denegado, sin datos reales ──────────

async def test_asesor_without_finance_permission_denied_on_all_three_tools(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    for tool_name in _FINANCE_TOOLS:
        result = await execute_tool(tool_name, {}, asesor_user, tenant, db)
        assert result == {"error": "No tienes acceso a finanzas"}, f"{tool_name}: {result}"
        # No debe venir ningún dato financiero real junto al error.
        assert set(result.keys()) == {"error"}, f"{tool_name} filtró datos junto al error: {result}"


# ── ASESOR con fila tenant-wide (branch_id=NULL) — permitido ───────────────────

async def test_asesor_with_tenant_wide_finance_permission_allowed_on_all_three_tools(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    db.add(_grant(tenant, asesor_user, branch_id=None))
    await db.flush()

    for tool_name in _FINANCE_TOOLS:
        result = await execute_tool(tool_name, {}, asesor_user, tenant, db)
        assert "error" not in result, f"{tool_name}: {result}"


# ── ASESOR con fila scoped a OTRO branch — sigue denegado (branch_id=None no matchea) ──

async def test_asesor_with_other_branch_finance_permission_still_denied(
    db: AsyncSession, tenant: Tenant, branch: Branch, asesor_user: User,
) -> None:
    other_branch = Branch(
        company_id=branch.company_id, tenant_id=tenant.id,
        name="Otra Sucursal", is_active=True,
    )
    db.add(other_branch)
    await db.flush()

    db.add(_grant(tenant, asesor_user, branch_id=other_branch.id))
    await db.flush()

    for tool_name in _FINANCE_TOOLS:
        result = await execute_tool(tool_name, {}, asesor_user, tenant, db)
        assert result == {"error": "No tienes acceso a finanzas"}, f"{tool_name}: {result}"
        assert set(result.keys()) == {"error"}, f"{tool_name} filtró datos junto al error: {result}"
