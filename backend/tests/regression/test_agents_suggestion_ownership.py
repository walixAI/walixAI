"""
Regresión — REST: ownership real en confirm_suggestion/dismiss_suggestion
(hallazgo #7, docs/PERMISSIONS_DRIFT_BACKLOG.md).

Código auditado:
  - app/api/agents.py::_get_suggestion_for_user — antes solo validaba
    suggestion.tenant_id != user.tenant_id, así que cualquier usuario del
    tenant podía confirmar/descartar una sugerencia dirigida a OTRO
    usuario o rol específico. Ahora aplica el mismo filtro que
    list_suggestions (líneas 82-86): target_user_id == usuario, O
    target_user_id IS NULL Y target_role == rol del usuario. Se
    centralizó en el helper — confirm_suggestion y dismiss_suggestion no
    duplican la condición.
  - El mismo problema ya se había resuelto del lado del Copiloto
    (app/ai/copilot_tools.py::execute_tool, rama "dismiss_suggestion",
    ver tests/regression/test_copilot_dismiss_suggestion.py) en un commit
    anterior de esta sesión — este archivo cierra el lado REST que había
    quedado pendiente entonces.

Nota: confirm_suggestion encola execute_suggestion_task.delay(...) sobre
el Redis real de este entorno (Upstash, ver .env) — se monkeypatchea
.delay en todos los tests de confirm para no disparar un job real contra
esa infraestructura compartida.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentSuggestion
from app.models.tenant import Tenant
from app.models.user import User, UserRole


def _make_suggestion(
    tenant: Tenant,
    *,
    target_user_id: uuid.UUID | None = None,
    target_role: str = "owner",
    status: str = "suggested",
) -> AgentSuggestion:
    return AgentSuggestion(
        tenant_id=tenant.id,
        agent_type="follow_up",
        trigger_description="Lead sin respuesta hace 3 días",
        suggestion_text="Enviar seguimiento a Juan Pérez",
        target_role=target_role,
        target_user_id=target_user_id,
        status=status,
    )


@pytest_asyncio.fixture()
def _no_real_celery_dispatch(monkeypatch) -> MagicMock:
    """confirm_suggestion llama execute_suggestion_task.delay(...) — mockeado
    para no encolar un job real contra el Redis compartido del entorno."""
    mock = MagicMock()
    monkeypatch.setattr("app.api.agents.execute_suggestion_task.delay", mock)
    return mock


# ── Dirigida a OTRO usuario específico — debe rechazarse (404) ─────────────────

async def test_confirm_denied_wrong_target_user(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    owner_user: User, asesor_user: User, auth_owner: dict[str, str],
    _no_real_celery_dispatch: MagicMock,
) -> None:
    sug = _make_suggestion(tenant, target_user_id=asesor_user.id, target_role="asesor")
    db.add(sug)
    await db.flush()

    r = await client.post(f"/api/agents/suggestions/{sug.id}/confirm", headers=auth_owner)

    assert r.status_code == 404
    await db.refresh(sug)
    assert sug.status == "suggested"
    _no_real_celery_dispatch.assert_not_called()


async def test_dismiss_denied_wrong_target_user(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    owner_user: User, asesor_user: User, auth_owner: dict[str, str],
) -> None:
    sug = _make_suggestion(tenant, target_user_id=asesor_user.id, target_role="asesor")
    db.add(sug)
    await db.flush()

    r = await client.post(
        f"/api/agents/suggestions/{sug.id}/dismiss", json={}, headers=auth_owner,
    )

    assert r.status_code == 404
    await db.refresh(sug)
    assert sug.status == "suggested"


# ── Dirigida directamente al usuario — sigue funcionando ───────────────────────

async def test_confirm_allowed_direct_target(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    owner_user: User, auth_owner: dict[str, str],
    _no_real_celery_dispatch: MagicMock,
) -> None:
    sug = _make_suggestion(tenant, target_user_id=owner_user.id, target_role="owner")
    db.add(sug)
    await db.flush()

    r = await client.post(f"/api/agents/suggestions/{sug.id}/confirm", headers=auth_owner)

    assert r.status_code == 202
    assert r.json()["status"] == "confirmed"
    await db.refresh(sug)
    assert sug.status == "confirmed"
    _no_real_celery_dispatch.assert_called_once()


async def test_dismiss_allowed_direct_target(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    owner_user: User, auth_owner: dict[str, str],
) -> None:
    sug = _make_suggestion(tenant, target_user_id=owner_user.id, target_role="owner")
    db.add(sug)
    await db.flush()

    r = await client.post(
        f"/api/agents/suggestions/{sug.id}/dismiss", json={}, headers=auth_owner,
    )

    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    await db.refresh(sug)
    assert sug.status == "dismissed"


# ── Broadcast a su rol (target_user_id=None, target_role coincide) ─────────────

async def test_confirm_allowed_role_broadcast(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    asesor_user: User, auth_asesor: dict[str, str],
    _no_real_celery_dispatch: MagicMock,
) -> None:
    sug = _make_suggestion(tenant, target_user_id=None, target_role=UserRole.ASESOR.value)
    db.add(sug)
    await db.flush()

    r = await client.post(f"/api/agents/suggestions/{sug.id}/confirm", headers=auth_asesor)

    assert r.status_code == 202
    await db.refresh(sug)
    assert sug.status == "confirmed"


async def test_dismiss_allowed_role_broadcast(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    asesor_user: User, auth_asesor: dict[str, str],
) -> None:
    sug = _make_suggestion(tenant, target_user_id=None, target_role=UserRole.ASESOR.value)
    db.add(sug)
    await db.flush()

    r = await client.post(
        f"/api/agents/suggestions/{sug.id}/dismiss", json={}, headers=auth_asesor,
    )

    assert r.status_code == 200
    await db.refresh(sug)
    assert sug.status == "dismissed"


async def test_confirm_denied_role_broadcast_wrong_role(
    client: AsyncClient, db: AsyncSession, tenant: Tenant,
    owner_user: User, auth_owner: dict[str, str],
    _no_real_celery_dispatch: MagicMock,
) -> None:
    """target_user_id=NULL pero target_role no coincide con el rol del usuario."""
    sug = _make_suggestion(tenant, target_user_id=None, target_role="asesor")
    db.add(sug)
    await db.flush()

    r = await client.post(f"/api/agents/suggestions/{sug.id}/confirm", headers=auth_owner)

    assert r.status_code == 404
    await db.refresh(sug)
    assert sug.status == "suggested"


# ── Otro tenant — ya cubierto por tenant_id, confirmado explícitamente ─────────

async def test_confirm_denied_cross_tenant(
    client: AsyncClient, db: AsyncSession, owner_user: User, auth_owner: dict[str, str],
    other_tenant_ctx: dict,
    _no_real_celery_dispatch: MagicMock,
) -> None:
    other_tenant = other_tenant_ctx["tenant"]
    sug = _make_suggestion(other_tenant, target_user_id=None, target_role="owner")
    db.add(sug)
    await db.flush()

    r = await client.post(f"/api/agents/suggestions/{sug.id}/confirm", headers=auth_owner)

    assert r.status_code == 404
    _no_real_celery_dispatch.assert_not_called()


async def test_dismiss_denied_cross_tenant(
    client: AsyncClient, db: AsyncSession, owner_user: User, auth_owner: dict[str, str],
    other_tenant_ctx: dict,
) -> None:
    other_tenant = other_tenant_ctx["tenant"]
    sug = _make_suggestion(other_tenant, target_user_id=None, target_role="owner")
    db.add(sug)
    await db.flush()

    r = await client.post(
        f"/api/agents/suggestions/{sug.id}/dismiss", json={}, headers=auth_owner,
    )

    assert r.status_code == 404
