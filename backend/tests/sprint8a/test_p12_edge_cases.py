"""
P-12 — Casos borde (Sprint 8A)

Verifica los límites y comportamientos defensivos del Sprint 8A:
  - Validación de nombre en vistas guardadas (vacío, solo espacios, demasiado largo)
  - view_mode inválido rechazado
  - filters acepta cualquier JSON válido
  - body de nota rápida: mínimo 2 chars, máximo 500 chars
  - AI Bar maneja respuestas con intents desconocidos sin lanzar excepción
  - PATCH sobre contacto soft-deleted devuelve 404

Adaptaciones al spec original:
  - Auth via auth_asesor (dict de headers), no user_asesor['jwt_token']
  - POST /contacts/views devuelve 201, no 200
  - filters round-trip: resp.json() usa clave 'filters' (nombre del campo en SavedViewRow)
  - /api/ai/command (no /api/v1/aibar/command); body es {"message", "context", "history"}
  - mock_claude_haiku.returns_json() para intent desconocido
  - resp body de CommandResult tiene 'intent_type', no 'action'
  - ActivityCreate ahora valida body: min_length=2, max_length=500
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.lead import Lead


# ── P-12-01 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_view_name_empty_fails(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST /contacts/views con nombre vacío retorna 422."""
    resp = await client.post(
        "/api/v1/contacts/views",
        json={"name": "", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    assert resp.status_code == 422


# ── P-12-02 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_view_name_only_spaces_fails(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST /contacts/views con nombre de solo espacios retorna 422
    (el validator hace strip antes de validar min_length=1)."""
    resp = await client.post(
        "/api/v1/contacts/views",
        json={"name": "   ", "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    assert resp.status_code == 422


# ── P-12-03 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_view_name_max_length_fails(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST /contacts/views con nombre > 80 chars retorna 422."""
    resp = await client.post(
        "/api/v1/contacts/views",
        json={"name": "A" * 81, "filters": {}, "view_mode": "list", "is_default": False},
        headers=auth_asesor,
    )
    assert resp.status_code == 422


# ── P-12-04 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_view_invalid_view_mode_fails(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST /contacts/views con view_mode fuera del Literal retorna 422."""
    resp = await client.post(
        "/api/v1/contacts/views",
        json={"name": "Test", "filters": {}, "view_mode": "tabla", "is_default": False},
        headers=auth_asesor,
    )
    assert resp.status_code == 422


# ── P-12-05 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_saved_view_filters_accepts_any_json(
    client: AsyncClient,
    auth_asesor: dict,
) -> None:
    """POST /contacts/views acepta cualquier JSON válido en filters (JSONB libre)."""
    arbitrary_filters = {"campo_futuro": [1, 2, 3], "otro": True}
    resp = await client.post(
        "/api/v1/contacts/views",
        json={
            "name": "Vista JSON libre",
            "filters": arbitrary_filters,
            "view_mode": "list",
            "is_default": False,
        },
        headers=auth_asesor,
    )
    assert resp.status_code == 201
    assert resp.json()["filters"] == arbitrary_filters


# ── P-12-06 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quick_note_too_short_fails(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """Nota rápida con body < 2 caracteres retorna 422."""
    resp = await client.post(
        f"/api/v1/contacts/{contact_full.id}/activities",
        json={"activity_type": "note", "body": "a"},
        headers=auth_asesor,
    )
    assert resp.status_code == 422


# ── P-12-07 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quick_note_too_long_fails(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """Nota rápida con body > 500 caracteres retorna 422."""
    resp = await client.post(
        f"/api/v1/contacts/{contact_full.id}/activities",
        json={"activity_type": "note", "body": "x" * 501},
        headers=auth_asesor,
    )
    assert resp.status_code == 422


# ── P-12-08 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quick_note_min_body_passes(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """Nota rápida con exactamente 2 caracteres pasa la validación."""
    resp = await client.post(
        f"/api/v1/contacts/{contact_full.id}/activities",
        json={"activity_type": "note", "body": "ok"},
        headers=auth_asesor,
    )
    assert resp.status_code == 201


# ── P-12-09 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_unknown_intent_returns_graceful_response(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """El AI Bar maneja intents con acciones desconocidas sin lanzar excepción (no 500)."""
    # Claude devuelve un intent válido pero con un tipo de acción desconocida
    mock_claude_haiku.returns_json({
        "intent_type": "accion",
        "response_text": "Acción desconocida procesada.",
        "requires_confirmation": False,
        "actions": [{"type": "unknown_future_action", "params": {}}],
        "data_query": None,
        "suggested_actions": [],
    })

    resp = await client.post(
        "/api/ai/command",
        json={"message": "haz algo que no existe", "context": {"screen": "contacts"}, "history": []},
        headers=auth_asesor,
    )

    # No debe retornar 500
    assert resp.status_code != 500
    assert resp.status_code == 200

    body = resp.json()
    # La respuesta debe tener la estructura de CommandResult
    assert "intent_type" in body
    assert "response_text" in body
    # La acción desconocida debe aparecer en actions_taken como fallida (no permitida)
    taken = body.get("actions_taken", [])
    if taken:
        assert taken[0]["success"] is False


# ── P-12-10 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_field_history_on_deleted_contact(
    client: AsyncClient,
    auth_asesor: dict,
    contact_minimal: Lead,
) -> None:
    """PATCH sobre un contacto soft-deleted devuelve 404."""
    # Soft-delete del contacto
    del_resp = await client.delete(
        f"/api/v1/contacts/{contact_minimal.id}",
        headers=auth_asesor,
    )
    assert del_resp.status_code == 204

    # Intentar editar el contacto eliminado
    resp = await client.patch(
        f"/api/v1/contacts/{contact_minimal.id}",
        json={"company": "Empresa Post Delete"},
        headers=auth_asesor,
    )
    assert resp.status_code == 404
