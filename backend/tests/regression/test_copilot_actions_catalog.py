"""
Regresión — Copiloto Fase 1, Parte D: catálogo de acciones + permisos.

Código auditado:
  - app/copilot/actions_catalog.py — formaliza las 18 tools ya existentes
    en app/ai/copilot_tools.py (COPILOT_TOOLS) con risk_tier,
    requires_confirmation y required_role declarativos, más 4 acciones
    representativas todavía no conectadas (handler=None).
  - app/copilot/permissions.py — reemplaza el check de rol ad-hoc que
    tenía copilot_tools.py::execute_tool en la rama de get_team_performance.
"""
from __future__ import annotations

import uuid

import pytest

from app.copilot.actions_catalog import ACTIONS, ACTIONS_LIST, get_action
from app.copilot.permissions import check_permission
from app.models.tenant import Tenant
from app.models.user import User, UserRole


# ── Catálogo: forma y consistencia ─────────────────────────────────────────────

def test_catalog_has_no_duplicate_names() -> None:
    names = [a.name for a in ACTIONS_LIST]
    assert len(names) == len(set(names))


def test_catalog_every_action_has_required_fields() -> None:
    assert len(ACTIONS_LIST) > 0
    for action in ACTIONS_LIST:
        assert action.name
        assert action.description
        assert action.risk_tier in ("low", "medium", "high")
        assert isinstance(action.required_role, frozenset)
        assert len(action.required_role) > 0
        assert all(isinstance(r, UserRole) for r in action.required_role)


def test_catalog_all_actions_require_confirmation_for_now() -> None:
    # Decisión de producto ya tomada (ver docstring de actions_catalog.py):
    # TRUE para todas, sin excepción, en esta fase.
    for action in ACTIONS_LIST:
        assert action.requires_confirmation is True, action.name


def test_catalog_covers_all_three_risk_tiers() -> None:
    tiers = {a.risk_tier for a in ACTIONS_LIST}
    assert tiers == {"low", "medium", "high"}


def test_catalog_wired_actions_have_execute_tool_handler() -> None:
    from app.ai.copilot_tools import execute_tool

    wired = [a for a in ACTIONS_LIST if a.handler is not None]
    assert len(wired) == 26  # 19 previas + 7 de la Ronda 1 de Finanzas/Gastos
    assert all(a.handler is execute_tool for a in wired)


def test_catalog_stub_actions_have_no_handler_yet() -> None:
    stubs = [a for a in ACTIONS_LIST if a.handler is None]
    assert {a.name for a in stubs} == {
        "assign_lead", "delete_deal", "send_whatsapp_message", "cancel_subscription",
        "confirm_suggestion",
    }


def test_get_action_returns_none_for_unknown_name() -> None:
    assert get_action("this_action_does_not_exist") is None
    assert get_action("get_pipeline_status") is ACTIONS["get_pipeline_status"]


# ── Permisos: rol requerido ─────────────────────────────────────────────────────

async def test_asesor_denied_on_owner_only_action(asesor_user: User) -> None:
    action = ACTIONS["get_team_performance"]
    allowed, reason = check_permission(asesor_user, action)
    assert allowed is False
    assert "get_team_performance" in reason


async def test_owner_allowed_on_owner_only_action(owner_user: User) -> None:
    action = ACTIONS["get_team_performance"]
    allowed, reason = check_permission(owner_user, action)
    assert allowed is True
    assert reason is None


async def test_asesor_allowed_on_open_action(asesor_user: User) -> None:
    action = ACTIONS["create_task"]
    allowed, _ = check_permission(asesor_user, action)
    assert allowed is True


async def test_asesor_denied_on_high_risk_owner_gated_action(asesor_user: User) -> None:
    action = ACTIONS["cancel_subscription"]
    allowed, reason = check_permission(asesor_user, action)
    assert allowed is False
    assert reason is not None


# ── Permisos: alcance de tenant ─────────────────────────────────────────────────

async def test_owner_denied_on_action_targeting_another_tenant(owner_user: User) -> None:
    action = ACTIONS["get_my_deals"]
    foreign_tenant_id = uuid.uuid4()
    allowed, reason = check_permission(owner_user, action, target_tenant_id=foreign_tenant_id)
    assert allowed is False
    assert reason is not None


async def test_owner_allowed_on_action_targeting_own_tenant(owner_user: User, tenant: Tenant) -> None:
    action = ACTIONS["get_my_deals"]
    allowed, _ = check_permission(owner_user, action, target_tenant_id=tenant.id)
    assert allowed is True


@pytest.mark.parametrize("cross_tenant_role", [UserRole.PLATFORM_OWNER])
async def test_platform_owner_allowed_cross_tenant(
    owner_user: User, cross_tenant_role: UserRole,
) -> None:
    # get_team_performance requiere OWNER/PLATFORM_OWNER — usamos owner_user
    # pero le pisamos el rol en memoria (sin tocar DB) solo para este check
    # de permisos, que es puro (no consulta la sesión).
    owner_user.role = cross_tenant_role
    action = ACTIONS["get_team_performance"]
    foreign_tenant_id = uuid.uuid4()
    allowed, _ = check_permission(owner_user, action, target_tenant_id=foreign_tenant_id)
    assert allowed is True
