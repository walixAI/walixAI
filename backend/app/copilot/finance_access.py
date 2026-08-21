"""Copiloto — acceso a finanzas para tools wireadas (hallazgo #8,
docs/PERMISSIONS_DRIFT_BACKLOG.md).

El modelo de permisos del catálogo (ActionDefinition.required_role) es
estático por rol y no puede expresar un grant dinámico scoped por branch
como FinancePermission (branch_id=NULL = tenant-wide, branch_id=<id> = solo
esa sucursal, otorgado fila por fila a usuarios que no son OWNER/
PLATFORM_OWNER). Este helper es la excepción ad-hoc para el dominio de
finanzas — mismo patrón que ya usa execute_tool::get_team_performance con
app/copilot/permissions.py::check_permission para su propio caso especial
(rol OWNER-tier), no un framework nuevo.

require_finance_access replica exactamente
app/api/finance.py::_require_finance_access, pero retorna (allowed, reason)
en vez de levantar HTTPException — mismo contrato que
app/copilot/permissions.py::check_permission — porque execute_tool nunca
levanta excepciones crudas (devuelve {"error": ...}, ver docstring de
app/ai/copilot_tools.py).
"""
from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import FinancePermission
from app.models.user import User, UserRole

# Mismo set que app/api/finance.py::_OWNER_ROLES — si esa definición
# cambia, esta debería revisarse también.
_OWNER_ROLES = (UserRole.OWNER, UserRole.PLATFORM_OWNER)


async def require_finance_access(
    user: User,
    branch_id: uuid.UUID | None,
    db: AsyncSession,
) -> tuple[bool, str | None]:
    """Returns (allowed, reason). Mirrors app/api/finance.py::
    _require_finance_access exactly, but returns instead of raising —
    same contract as app/copilot/permissions.py::check_permission."""
    if user.role in _OWNER_ROLES:
        return True, None

    result = await db.execute(
        select(FinancePermission).where(
            FinancePermission.tenant_id == user.tenant_id,
            FinancePermission.user_id == user.id,
            or_(
                FinancePermission.branch_id == branch_id,
                FinancePermission.branch_id.is_(None),
            ),
        )
    )
    if result.scalar_one_or_none() is None:
        return False, "No tienes acceso a finanzas"

    return True, None
