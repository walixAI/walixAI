"""
Sprint 8A · P-04 — WalixAIBar contact_create intent
Prueba la creación de contactos desde el AI Bar.

Adaptaciones al spec original:
  - Endpoint real: POST /api/ai/command  (no /api/v1/aibar/command)
  - Body: {message, context, history}     (no {command, context})
  - Auth: fixture auth_asesor             (no user_asesor['jwt_token'])
  - Mock: fixture mock_claude_haiku       (no @patch manual)
  - Respuesta: resp.json()["action_data"] (no campos top-level)
  - prospection_source / assigned_user → verificar via GET /contacts/{id}
  - Langfuse → verificar ai_command_logs que sí está implementado
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.models.user import User

_AIBAR = "/api/ai/command"
_CONTACTS = "/api/v1/contacts"


def _cmd(message: str, screen: str = "contacts", contact_id: str | None = None) -> dict:
    ctx: dict = {"screen": screen}
    if contact_id:
        ctx["contact_id"] = contact_id
    return {"message": message, "context": ctx, "history": []}


# ── P-04-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_contact_full_data(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_create con nombre, teléfono y empresa crea el contacto correctamente."""
    mock_claude_haiku.returns_contact_create(
        "Luis Martínez",
        phone="+5281123456789",
        company="Grupo Norte",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd("agrega a Luis Martínez, tel 81 1234 5678, empresa Grupo Norte"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["action_data"] is not None, "action_data debe estar presente"
    assert data["action_data"]["action"] == "contact_created"

    contact = data["action_data"]["contact"]
    assert contact["name"] == "Luis Martínez"
    assert contact["company"] == "Grupo Norte"

    # Verificar que el contacto existe en BD
    db_resp = await client.get(f"{_CONTACTS}/{contact['id']}", headers=auth_asesor)
    assert db_resp.status_code == 200, db_resp.text
    assert db_resp.json()["name"] == "Luis Martínez"


# ── P-04-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_contact_minimal_name_only(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_create con solo nombre funciona (nombre es el único campo obligatorio)."""
    mock_claude_haiku.returns_contact_create("María")

    resp = await client.post(
        _AIBAR,
        json=_cmd("nuevo contacto: María"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "contact_created"
    assert ad["contact"]["name"] == "María"
    # Sin teléfono → se usa NOPHONE_ placeholder; contact.phone debe ser None
    assert ad["contact"]["phone"] is None


# ── P-04-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_normalizes_phone(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """El executor normaliza teléfonos de 10 dígitos agregando +52."""
    mock_claude_haiku.returns_contact_create("Pedro Ruiz", phone="8112345678")

    resp = await client.post(
        _AIBAR,
        json=_cmd("agrega a Pedro Ruiz tel 8112345678"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    phone = resp.json()["action_data"]["contact"]["phone"]
    assert phone is not None, "El teléfono no debe ser None"
    assert phone.startswith("+52"), (
        f"El teléfono de 10 dígitos debe normalizarse con +52, obtenido: {phone}"
    )
    assert "8112345678" in phone, "Los dígitos originales deben conservarse"


# ── P-04-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_assigns_to_current_user(
    client: AsyncClient,
    auth_asesor: dict,
    user_asesor: User,
    mock_claude_haiku,
) -> None:
    """contact_create asigna el contacto al usuario que ejecuta el comando."""
    mock_claude_haiku.returns_contact_create("Ana López")

    resp = await client.post(
        _AIBAR,
        json=_cmd("nuevo contacto Ana López"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    contact_id = resp.json()["action_data"]["contact"]["id"]

    # action_data no incluye assignedUser → verificar via GET /contacts/{id}
    db_resp = await client.get(f"{_CONTACTS}/{contact_id}", headers=auth_asesor)
    assert db_resp.status_code == 200, db_resp.text

    assigned = db_resp.json()["assigned_user"]
    assert assigned is not None, "El contacto debe tener un vendedor asignado"
    assert assigned["id"] == str(user_asesor.id), (
        f"Esperaba asignado a {user_asesor.id}, obtenido {assigned['id']}"
    )


# ── P-04-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_whatsapp_source(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_create conserva la fuente de prospección detectada por Claude."""
    mock_claude_haiku.returns_contact_create(
        "Carlos",
        phone="+5281999888777",
        prospection_source="whatsapp_inbound",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd("llegó por WhatsApp: Carlos, tel +5281999888777"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    contact_id = resp.json()["action_data"]["contact"]["id"]

    # Verificar vía GET /contacts/{id} (snake_case en response)
    db_resp = await client.get(f"{_CONTACTS}/{contact_id}", headers=auth_asesor)
    assert db_resp.status_code == 200, db_resp.text
    assert db_resp.json()["prospection_source"] == "whatsapp_inbound"


# ── P-04-06 ───────────────────────────────────────────────────────────────────
# Langfuse no está implementado — verificamos ai_command_logs (nuestra persistencia)


@pytest.mark.asyncio
async def test_aibar_create_contact_command_logged(
    client: AsyncClient,
    auth_asesor: dict,
    db: AsyncSession,
    user_asesor: User,
    mock_claude_haiku,
) -> None:
    """La creación via AIBar queda registrada en ai_command_logs."""
    mock_claude_haiku.returns_contact_create("Test Log", company="LogTest SA")

    resp = await client.post(
        _AIBAR,
        json=_cmd("nuevo contacto Test Log de LogTest SA"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    # Response always has tokens_used + latency_ms when the log path ran
    data = resp.json()
    assert "tokens_used" in data
    assert "latency_ms" in data

    # Verify the row was persisted in ai_command_logs
    count = (
        await db.execute(
            text("SELECT COUNT(*) FROM ai_command_logs WHERE user_id = :uid"),
            {"uid": str(user_asesor.id)},
        )
    ).scalar()
    assert count >= 1, "Debe existir al menos un registro en ai_command_logs"


# ── P-04-07 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_no_jwt_fails(
    client: AsyncClient,
) -> None:
    """POST /api/ai/command sin JWT retorna 401."""
    resp = await client.post(
        _AIBAR,
        json=_cmd("nuevo contacto Test"),
    )
    assert resp.status_code == 401


# ── P-04-08 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_response_structure(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """La respuesta tiene todos los campos del CommandResult y action_data completo."""
    mock_claude_haiku.returns_contact_create("Estructura Test")

    resp = await client.post(
        _AIBAR,
        json=_cmd("nuevo contacto Estructura Test"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200
    data = resp.json()

    # Top-level CommandResult fields
    for field in ("intent_type", "response_text", "requires_confirmation",
                  "actions_taken", "suggested_actions", "tokens_used",
                  "latency_ms", "action_data"):
        assert field in data, f"Campo faltante en respuesta: {field}"

    # action_data fields
    ad = data["action_data"]
    assert ad["action"] == "contact_created"
    assert "contact" in ad
    assert "message" in ad

    # contact fields
    for field in ("id", "name", "phone", "company"):
        assert field in ad["contact"], f"Campo faltante en contact: {field}"


# ── P-04-09 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_missing_name_returns_error(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_create sin nombre retorna action_data con action='error'."""
    mock_claude_haiku.returns_json({
        "intent_type": "accion",
        "response_text": "Intentando crear contacto sin nombre.",
        "requires_confirmation": False,
        "actions": [{"type": "contact_create", "params": {"name": "", "phone": None}}],
        "data_query": None,
        "suggested_actions": [],
    })

    resp = await client.post(
        _AIBAR,
        json=_cmd("crea un contacto"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200  # AIBar siempre retorna 200 al frontend

    data = resp.json()
    # El executor debe haber retornado action="error" al no tener nombre
    if data["action_data"]:
        assert data["action_data"]["action"] == "error"
    else:
        # Alternativamente, la action falló
        assert not data["actions_taken"][0]["success"]


# ── P-04-10 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_create_contact_tenant_isolated(
    client: AsyncClient,
    auth_asesor: dict,
    auth_other: dict,
    user_asesor: User,
    user_other_tenant: User,
    mock_claude_haiku,
) -> None:
    """Un contacto creado vía AIBar pertenece al tenant del usuario que lo crea."""
    mock_claude_haiku.returns_contact_create("Tenant Test")

    resp = await client.post(
        _AIBAR,
        json=_cmd("nuevo contacto Tenant Test"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    contact_id = resp.json()["action_data"]["contact"]["id"]

    # El asesor de tenant_a puede verlo
    r_asesor = await client.get(f"{_CONTACTS}/{contact_id}", headers=auth_asesor)
    assert r_asesor.status_code == 200

    # El usuario de tenant_b no puede verlo (tenant isolation)
    r_other = await client.get(f"{_CONTACTS}/{contact_id}", headers=auth_other)
    assert r_other.status_code == 404
