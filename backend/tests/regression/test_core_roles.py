"""
Regresión — app/core/roles.py: fuente única de MULTI_BRANCH_ROLES
(hallazgo #1, docs/PERMISSIONS_DRIFT_BACKLOG.md).

Antes de este módulo, leads.py, pipeline.py, pipelines.py y users.py
redefinían _MULTI_BRANCH_ROLES localmente como (OWNER, IT), sin
PLATFORM_OWNER — divergiendo de metrics.py, que sí lo incluía. Este test
fija el contrato del módulo compartido; los tests de comportamiento real
por endpoint viven en test_multi_branch_roles_platform_owner.py.
"""
from __future__ import annotations

from app.core.roles import MULTI_BRANCH_ROLES
from app.models.user import UserRole


def test_multi_branch_roles_is_frozenset() -> None:
    assert isinstance(MULTI_BRANCH_ROLES, frozenset)


def test_multi_branch_roles_contains_exactly_owner_it_platform_owner() -> None:
    assert MULTI_BRANCH_ROLES == frozenset(
        {UserRole.OWNER, UserRole.IT, UserRole.PLATFORM_OWNER}
    )


def test_multi_branch_roles_excludes_gerente_and_asesor() -> None:
    assert UserRole.GERENTE not in MULTI_BRANCH_ROLES
    assert UserRole.ASESOR not in MULTI_BRANCH_ROLES
