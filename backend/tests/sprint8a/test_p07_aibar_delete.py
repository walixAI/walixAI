"""
Sprint 8A · P-07 — WalixAIBar contact_delete + confirmación
Prueba el flujo de dos pasos: requires_confirmation → contact_delete_confirmed.

Adaptaciones al spec original:
  - Endpoint: POST /api/ai/command
  - Respuesta: resp.json()["action_data"]
  - Confirmación: {message: "__confirm__", context: {confirmation_action: {type: "contact_delete", ...}}}
    (NO context.pending_confirmation como en el spec)
  - El mock usa requires_confirmation=False: el executor corre y retorna
    {action: "requires_confirmation"} por su propia lógica (no Claude)
  - deleted_at verificado con SQL raw (GET devuelve 404 post-delete)
  - Fixture objects: contact_full.name / .id (no dict)
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.models.lead import Lead

_AIBAR = "/api/ai/command"
_CONTACTS = "/api/v1/contacts"


def _first_call(contact_name: str, screen: str = "contacts") -> dict:
    return {
        "message": f"archiva a {contact_name}",
        "context": {"screen": screen},
        "history": [],
    }


def _confirm_call(confirmation_id: str, contact_id: str) -> dict:
    return {
        "message": "__confirm__",
        "context": {
            "screen": "contacts",
            "confirmation_action": {
                "type": "contact_delete",
                "confirmation_id": confirmation_id,
                "contact_id": contact_id,
            },
        },
        "history": [],
    }


# ── P-07-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_requires_confirmation(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_delete siempre retorna requires_confirmation, nunca ejecuta directo."""
    # requires_confirmation=False → executor corre → retorna {action:"requires_confirmation"}
    mock_claude_haiku.returns_contact_delete(contact_full.name, requires_confirmation=False)

    resp = await client.post(
        _AIBAR,
        json=_first_call(contact_full.name),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad is not None
    assert ad["action"] == "requires_confirmation"
    assert "confirmation_id" in ad
    assert "contact_id" in ad
    assert "confirm_action" in ad
    assert ad["confirm_action"] == "contact_delete_confirmed"
    assert "archivar" in ad["message"].lower() or "archivar" in ad.get("contact_name", "").lower()

    # El contacto NO debe haberse eliminado
    r = await client.get(f"{_CONTACTS}/{contact_full.id}", headers=auth_asesor)
    assert r.status_code == 200, "El contacto aún debe existir tras la primera llamada"
    assert r.json()["deleted_at"] is None


# ── P-07-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_confirmed_executes(
    client: AsyncClient,
    auth_asesor: dict,
    db: AsyncSession,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_delete_confirmed con datos válidos ejecuta el soft delete."""
    # ── Primera llamada: obtener confirmation_id y contact_id ─────────────────
    mock_claude_haiku.returns_contact_delete(contact_full.name, requires_confirmation=False)

    resp1 = await client.post(
        _AIBAR,
        json=_first_call(contact_full.name),
        headers=auth_asesor,
    )
    assert resp1.status_code == 200
    ad1 = resp1.json()["action_data"]
    assert ad1["action"] == "requires_confirmation"

    confirmation_id = ad1["confirmation_id"]
    contact_id = ad1["contact_id"]

    # ── Segunda llamada: confirmar (shortcut — no llama a Claude) ─────────────
    resp2 = await client.post(
        _AIBAR,
        json=_confirm_call(confirmation_id, contact_id),
        headers=auth_asesor,
    )
    assert resp2.status_code == 200, resp2.text

    ad2 = resp2.json()["action_data"]
    assert ad2["action"] == "contact_deleted", (
        f"Se esperaba 'contact_deleted', obtenido: {ad2}"
    )

    # Soft delete: GET /contacts/{id} devuelve 404 (deleted_at IS NOT NULL)
    r = await client.get(f"{_CONTACTS}/{contact_full.id}", headers=auth_asesor)
    assert r.status_code == 404, "El contacto debe estar archivado (404 en GET)"

    # Confirmar via SQL que deleted_at fue seteado
    deleted_at = (
        await db.execute(
            text("SELECT deleted_at FROM leads WHERE id = :id"),
            {"id": str(contact_full.id)},
        )
    ).scalar()
    assert deleted_at is not None, "deleted_at debe tener un valor tras el archivado"


# ── P-07-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_invalid_contact_id_fails(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_delete_confirmed con contact_id inválido retorna error."""
    # Enviar directamente la confirmación con un contact_id que no es UUID válido
    resp = await client.post(
        _AIBAR,
        json=_confirm_call(
            confirmation_id=str(uuid.uuid4()),
            contact_id="not-a-valid-uuid",
        ),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "error", (
        f"Un contact_id inválido debe retornar 'error', obtenido: {ad['action']}"
    )
    assert "inválido" in ad["message"].lower() or "invalido" in ad["message"].lower()

    # Verificar que contact_full sigue sin archivar
    r = await client.get(f"{_CONTACTS}/{contact_full.id}", headers=auth_asesor)
    assert r.status_code == 200, "El contacto no debe haberse eliminado"


# ── P-07-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_wa_conversations_preserved(
    client: AsyncClient,
    auth_asesor: dict,
    db: AsyncSession,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """El soft delete no elimina las conversaciones de WhatsApp del contacto."""
    # Contar conversaciones antes del archivado (puede ser 0)
    conv_before = (
        await db.execute(
            text("SELECT COUNT(*) FROM conversations WHERE lead_id = :lid"),
            {"lid": str(contact_full.id)},
        )
    ).scalar()

    # Ejecutar el flujo de delete
    mock_claude_haiku.returns_contact_delete(contact_full.name, requires_confirmation=False)
    resp1 = await client.post(_AIBAR, json=_first_call(contact_full.name), headers=auth_asesor)
    ad1 = resp1.json()["action_data"]

    resp2 = await client.post(
        _AIBAR,
        json=_confirm_call(ad1["confirmation_id"], ad1["contact_id"]),
        headers=auth_asesor,
    )
    assert resp2.json()["action_data"]["action"] == "contact_deleted"

    # Las conversaciones deben seguir intactas
    conv_after = (
        await db.execute(
            text("SELECT COUNT(*) FROM conversations WHERE lead_id = :lid"),
            {"lid": str(contact_full.id)},
        )
    ).scalar()
    assert conv_after == conv_before, (
        "El archivado no debe eliminar las conversaciones de WhatsApp"
    )


# ── P-07-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_message_says_archivar_not_eliminar(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """El mensaje de confirmación usa 'archivar', nunca 'eliminar'."""
    mock_claude_haiku.returns_contact_delete(contact_full.name, requires_confirmation=False)

    resp = await client.post(
        _AIBAR,
        json=_first_call(contact_full.name),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "requires_confirmation"

    message_lower = ad.get("message", "").lower()
    assert "eliminar" not in message_lower, (
        f"El mensaje no debe usar 'eliminar'. Mensaje: {ad['message']}"
    )
    assert "archivar" in message_lower, (
        f"El mensaje debe usar 'archivar'. Mensaje: {ad['message']}"
    )


# ── P-07-06 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_asesor_can_delete_own_contact(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """Un asesor puede archivar un contacto que le está asignado."""
    # Crear contacto propio (asignado al asesor automáticamente)
    unique_phone = f"+521{uuid.uuid4().int % 10**9:09d}"
    r = await client.post(
        _CONTACTS,
        json={"wa_phone": unique_phone, "name": "Mi Contacto Personal"},
        headers=auth_asesor,
    )
    assert r.status_code == 201, r.text
    contact_id = r.json()["id"]

    # Primera llamada: solicitar archivado
    mock_claude_haiku.returns_contact_delete("Mi Contacto Personal", requires_confirmation=False)
    resp1 = await client.post(
        _AIBAR,
        json=_first_call("Mi Contacto Personal"),
        headers=auth_asesor,
    )
    assert resp1.status_code == 200, resp1.text
    ad1 = resp1.json()["action_data"]
    assert ad1["action"] == "requires_confirmation", (
        f"Se esperaba 'requires_confirmation', obtenido: {ad1}"
    )

    # Segunda llamada: confirmar
    resp2 = await client.post(
        _AIBAR,
        json=_confirm_call(ad1["confirmation_id"], ad1["contact_id"]),
        headers=auth_asesor,
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["action_data"]["action"] == "contact_deleted"

    # Contacto archivado → 404 en GET
    r2 = await client.get(f"{_CONTACTS}/{contact_id}", headers=auth_asesor)
    assert r2.status_code == 404


# ── P-07-07 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_contact_not_found_returns_ambiguous(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_delete con nombre que no existe retorna action='ambiguous'."""
    mock_claude_haiku.returns_contact_delete("ZZZ Nombre Que No Existe XYZ", requires_confirmation=False)

    resp = await client.post(
        _AIBAR,
        json=_first_call("ZZZ Nombre Que No Existe XYZ"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "ambiguous", (
        f"Un nombre inexistente debe retornar 'ambiguous', obtenido: {ad['action']}"
    )


# ── P-07-08 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_delete_other_tenant_contact_fails(
    client: AsyncClient,
    auth_asesor: dict,
    auth_other: dict,
    mock_claude_haiku,
) -> None:
    """No se puede archivar un contacto de otro tenant."""
    # Crear contacto en tenant_b
    phone_b = f"+521{uuid.uuid4().int % 10**9:09d}"
    r = await client.post(
        _CONTACTS,
        json={"wa_phone": phone_b, "name": "Contacto Tenant B"},
        headers=auth_other,
    )
    assert r.status_code == 201
    contact_b_id = r.json()["id"]

    # Intentar archivar desde tenant_a
    mock_claude_haiku.returns_contact_delete("Contacto Tenant B", requires_confirmation=False)
    resp = await client.post(
        _AIBAR,
        json=_first_call("Contacto Tenant B"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    # El executor filtra por tenant → no encontrará el contacto → ambiguous
    assert ad["action"] == "ambiguous", (
        f"No debe poder archivar contacto de otro tenant, obtenido: {ad['action']}"
    )

    # Verificar que el contacto sigue activo en tenant_b
    r2 = await client.get(f"{_CONTACTS}/{contact_b_id}", headers=auth_other)
    assert r2.status_code == 200
    assert r2.json()["deleted_at"] is None
