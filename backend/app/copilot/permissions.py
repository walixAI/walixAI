"""Copiloto — Fase 1: chequeo de permisos centralizado por acción.

Reemplaza los checks de rol ad-hoc que hoy viven sueltos dentro de
app/ai/copilot_tools.py::execute_tool (ej. `if user.role not in
_OWNER_ROLES` en la rama de get_team_performance) por una única función
reutilizable desde cualquier lugar que necesite decidir si un usuario
puede invocar una ActionDefinition del catálogo.

Aislamiento de tenant/branch: esto NO reemplaza RLS ni set_tenant_context
— esas siguen siendo la barrera real a nivel de base de datos. Esta
función es una verificación de INTENCIÓN, para fallar rápido y con un
mensaje claro antes de intentar ejecutar la acción, cuando el llamador ya
conoce el tenant_id/branch_id objetivo (ej. una acción vendría con un
target_tenant_id explícito en su payload). Ninguna de las 18 acciones
wireadas hoy en el catálogo pasa target_tenant_id/target_branch_id — son
todas implícitamente 'del tenant/branch del usuario actual', resuelto
normalmente vía user.tenant_id dentro de cada tool. Los parámetros están
acá listos para cuando eso deje de ser cierto (ej. un platform_owner
operando sobre un tenant ajeno).
"""
from __future__ import annotations

import uuid

from app.copilot.actions_catalog import ActionDefinition
from app.models.user import User, UserRole

# Mismo set que app/api/metrics.py::_MULTI_BRANCH_ROLES — roles que pueden
# operar fuera de su propia sucursal. GERENTE queda afuera a propósito,
# igual que en metrics.py (no es un alias local independiente: si esa
# definición cambia, esta debería revisarse también).
_MULTI_BRANCH_ROLES = frozenset({UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER})


class PermissionDenied(Exception):
    """Un usuario no tiene permiso para invocar una acción del catálogo."""


def check_permission(
    user: User,
    action: ActionDefinition,
    target_tenant_id: uuid.UUID | None = None,
    target_branch_id: uuid.UUID | None = None,
) -> tuple[bool, str | None]:
    """Returns (allowed, reason). reason is None when allowed=True."""
    if user.role not in action.required_role:
        allowed_roles = ", ".join(sorted(r.value for r in action.required_role))
        return False, (
            f"Rol '{user.role.value}' no autorizado para '{action.name}' "
            f"(requiere uno de: {allowed_roles})"
        )

    if target_tenant_id is not None and target_tenant_id != user.tenant_id:
        # Único rol con alcance cross-tenant legítimo hoy — mismo criterio
        # que app/api/platform.py::require_platform_owner.
        if user.role != UserRole.PLATFORM_OWNER:
            return False, (
                f"La acción '{action.name}' apunta a un tenant distinto al del usuario "
                "y su rol no tiene alcance cross-tenant"
            )

    if (
        target_branch_id is not None
        and user.branch_id is not None
        and target_branch_id != user.branch_id
        and user.role not in _MULTI_BRANCH_ROLES
    ):
        return False, (
            f"La acción '{action.name}' apunta a una sucursal distinta a la del usuario "
            "y su rol no tiene alcance multi-sucursal"
        )

    return True, None


def require_permission(
    user: User,
    action: ActionDefinition,
    target_tenant_id: uuid.UUID | None = None,
    target_branch_id: uuid.UUID | None = None,
) -> None:
    """Same as check_permission but raises PermissionDenied instead of returning False."""
    allowed, reason = check_permission(user, action, target_tenant_id, target_branch_id)
    if not allowed:
        raise PermissionDenied(reason)
