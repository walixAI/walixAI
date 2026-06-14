"""
P-11 — Seguridad y aislamiento multi-tenant (Sprint 8A)

Verifica que:
  - Las vistas guardadas están aisladas por usuario (no por tenant)
  - Las vistas de tenant_a son invisibles para tenant_b
  - Las actividades de un contacto de tenant_a son inaccesibles desde tenant_b
  - El AI Bar siempre crea contactos en el tenant del usuario autenticado
  - Las notas rápidas (activities) no se pueden crear sobre contactos de otro tenant
  - Solo el dueño de una vista puede eliminarla
  - Todos los endpoints protegidos devuelven 401 sin JWT

Adaptaciones al spec original:
  - Endpoint AI Bar: /api/ai/command (no /api/v1/aibar/command)
  - Auth headers: auth_asesor/auth_gerente/auth_other (no user['jwt_token'])
  - ContactCreate requiere wa_phone (no phone)
  - _lead_dict no incluye tenant_id → la verificación de tenant se hace via DB
  - mock_claude_haiku.returns_contact_create() es el helper oficial del conftest
  - El endpoint de vistas se verifica con GET (no POST vacío) para evitar 422 por body
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.user import User


# ── P-11-01 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_isolated_by_user(
    client: AsyncClient,
    auth_gerente: dict,
    auth_asesor: dict,
) -> None:
    """Un usuario no puede ver las vistas guardadas de otro usuario del mismo tenant."""
    # Crear vista como gerente
    r = await client.post(
        "/api/v1/contacts/views",
        json={"name": "Vista Privada Gerente", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_gerente,
    )
    assert r.status_code == 201

    # Listar vistas como asesor
    r = await client.get("/api/v1/contacts/views", headers=auth_asesor)
    assert r.status_code == 200

    names = [v["name"] for v in r.json()]
    assert "Vista Privada Gerente" not in names


# ── P-11-02 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_views_tenant_b_not_visible(
    client: AsyncClient,
    auth_asesor: dict,
    auth_other: dict,
) -> None:
    """Un usuario de tenant_b no puede ver las vistas de tenant_a."""
    r = await client.post(
        "/api/v1/contacts/views",
        json={"name": "Vista Tenant A", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    assert r.status_code == 201

    r = await client.get("/api/v1/contacts/views", headers=auth_other)
    assert r.status_code == 200

    assert not any(v["name"] == "Vista Tenant A" for v in r.json())


# ── P-11-03 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_field_history_not_visible_cross_tenant(
    client: AsyncClient,
    auth_asesor: dict,
    auth_other: dict,
    contact_full: Lead,
) -> None:
    """Un usuario de tenant_b no puede ver las activities de un contacto de tenant_a."""
    # Generar un campo histórico actualizando el contacto
    await client.patch(
        f"/api/v1/contacts/{contact_full.id}",
        json={"company": "Empresa A"},
        headers=auth_asesor,
    )

    # Intentar leer activities del contacto desde tenant_b
    resp = await client.get(
        f"/api/v1/contacts/{contact_full.id}/activities",
        headers=auth_other,
    )
    assert resp.status_code in (403, 404)


# ── P-11-04 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_cannot_create_contact_in_other_tenant(
    client: AsyncClient,
    db: AsyncSession,
    auth_asesor: dict,
    user_asesor: User,
    user_other_tenant: User,
    mock_claude_haiku,
) -> None:
    """El AI Bar siempre crea contactos en el tenant del usuario autenticado."""
    mock_claude_haiku.returns_contact_create("Intruso E2E")

    resp = await client.post(
        "/api/ai/command",
        json={"message": "crea el contacto Intruso E2E", "context": {"screen": "contacts"}, "history": []},
        headers=auth_asesor,
    )
    assert resp.status_code == 200

    data = resp.json()
    action_data = data.get("action_data") or {}
    contact_info = action_data.get("contact")
    assert contact_info is not None, "La respuesta debería contener action_data.contact"

    # Verificar desde la DB que el contacto pertenece al tenant del asesor
    lead = await db.get(Lead, uuid.UUID(contact_info["id"]))
    assert lead is not None
    assert lead.tenant_id == user_asesor.tenant_id
    assert lead.tenant_id != user_other_tenant.tenant_id


# ── P-11-05 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quick_note_requires_own_tenant_contact(
    client: AsyncClient,
    auth_asesor: dict,
    auth_other: dict,
) -> None:
    """La nota rápida no puede crearse sobre un contacto de otro tenant."""
    # Crear contacto en tenant_b
    unique_phone = f"+5215599{uuid.uuid4().int % 10_000_000:07d}"
    r = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": unique_phone, "name": "Contacto Tenant B"},
        headers=auth_other,
    )
    assert r.status_code == 201
    contact_b_id = r.json()["id"]

    # Intentar crear actividad sobre ese contacto desde tenant_a
    resp = await client.post(
        f"/api/v1/contacts/{contact_b_id}/activities",
        json={"activity_type": "note", "body": "Nota intrusa"},
        headers=auth_asesor,
    )
    assert resp.status_code in (403, 404)


# ── P-11-06 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_view_delete_requires_ownership(
    client: AsyncClient,
    auth_gerente: dict,
    auth_asesor: dict,
) -> None:
    """Solo el dueño de una vista puede eliminarla (no otro usuario del mismo tenant)."""
    r = await client.post(
        "/api/v1/contacts/views",
        json={"name": "Vista Solo Gerente", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_gerente,
    )
    assert r.status_code == 201
    view_id = r.json()["id"]

    # Intentar borrarla como asesor (mismo tenant, distinto usuario)
    resp = await client.delete(
        f"/api/v1/contacts/views/{view_id}",
        headers=auth_asesor,
    )
    assert resp.status_code == 404


# ── P-11-07 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_command_without_auth_returns_401(
    client: AsyncClient,
) -> None:
    """Todos los endpoints protegidos del AI Bar y vistas requieren JWT."""
    # GET /api/v1/contacts/views sin token
    resp = await client.get("/api/v1/contacts/views")
    assert resp.status_code == 401, "GET /api/v1/contacts/views debería requerir auth"

    # POST /api/ai/command con body válido pero sin token
    resp = await client.post(
        "/api/ai/command",
        json={"message": "hola", "context": {}, "history": []},
    )
    assert resp.status_code == 401, "POST /api/ai/command debería requerir auth"

    # POST /api/v1/contacts/views con body válido pero sin token
    resp = await client.post(
        "/api/v1/contacts/views",
        json={"name": "Test", "filters": {}, "view_mode": "list", "is_default": False},
    )
    assert resp.status_code == 401, "POST /api/v1/contacts/views debería requerir auth"
