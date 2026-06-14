"""
Sprint 8A · P-06 — WalixAIBar contact_update + contact_activity intents
Prueba la actualización de contactos y el registro de actividades desde el AI Bar.

Adaptaciones al spec original:
  - Endpoint: POST /api/ai/command
  - Respuesta: resp.json()["action_data"]
  - action values: "contact_updated", "activity_created", "ambiguous"
  - Status en minúsculas: "calificado", "nuevo", etc.
  - Activity metadata → "extra_data" (no "metadata")
  - Fixtures ORM objects: contact_full.id, contact_full.name (no dict access)
  - Auth: auth_asesor (no jwt_token)
  - Creación de contactos: wa_phone obligatorio
  - test_aibar_update_contact_not_in_tenant_fails: action == "ambiguous"
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.lead import Lead
from app.models.user import User

_AIBAR = "/api/ai/command"
_CONTACTS = "/api/v1/contacts"


def _cmd(message: str, screen: str = "contacts", contact_id: str | None = None) -> dict:
    ctx: dict = {"screen": screen}
    if contact_id:
        ctx["contact_id"] = contact_id
    return {"message": message, "context": ctx, "history": []}


# ── P-06-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_update_status(
    client: AsyncClient,
    auth_asesor: dict,
    contact_minimal: Lead,   # status=NUEVO → cambiaremos a "calificado"
    mock_claude_haiku,
) -> None:
    """contact_update cambia el status de un contacto identificado por nombre."""
    mock_claude_haiku.returns_contact_update(
        contact_ref=contact_minimal.name,
        field="status",
        new_value="calificado",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"cambia el status de {contact_minimal.name} a calificado"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "contact_updated", f"Esperaba 'contact_updated', obtenido: {ad}"

    # Verificar en BD vía GET /contacts/{id}
    updated = (await client.get(f"{_CONTACTS}/{contact_minimal.id}", headers=auth_asesor)).json()
    assert updated["status"] == "calificado"


# ── P-06-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_update_ambiguous_contact_ref(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_update con referencia ambigua retorna action='ambiguous'."""
    # Crear dos contactos con nombre similar (ambos empiezan con "Carlos")
    phone_a = f"+521{uuid.uuid4().int % 10**9:09d}"
    phone_b = f"+521{uuid.uuid4().int % 10**9:09d}"
    await client.post(_CONTACTS, json={"wa_phone": phone_a, "name": "Carlos García"}, headers=auth_asesor)
    await client.post(_CONTACTS, json={"wa_phone": phone_b, "name": "Carlos González"}, headers=auth_asesor)

    mock_claude_haiku.returns_contact_update(
        contact_ref="Carlos",
        field="status",
        new_value="nuevo",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd("cambia el status de Carlos a nuevo"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "ambiguous", (
        f"Con 2 'Carlos' se esperaba 'ambiguous', obtenido: {ad['action']}"
    )
    assert "message" in ad
    assert len(ad["message"]) > 0


# ── P-06-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_update_uses_screen_contact_id(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_update sin contact_ref usa el contact_id del contexto de pantalla."""
    mock_claude_haiku.returns_contact_update(
        contact_ref="",
        field="company",
        new_value="Empresa Nueva",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd(
            "cambia la empresa a Empresa Nueva",
            screen=f"contacts/{contact_full.id}",
            contact_id=str(contact_full.id),
        ),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "contact_updated", (
        f"Con contact_id en contexto se esperaba 'contact_updated', obtenido: {ad}"
    )

    # Verificar campo en BD
    updated = (await client.get(f"{_CONTACTS}/{contact_full.id}", headers=auth_asesor)).json()
    assert updated["company"] == "Empresa Nueva"


# ── P-06-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_activity_note(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_activity crea una nota sobre el contacto."""
    mock_claude_haiku.returns_contact_activity(
        contact_ref=contact_full.name,
        activity_type="note",
        body="Pidió cotización para 50 unidades",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"nota sobre {contact_full.name}: pidió cotización para 50 unidades"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "activity_created"

    # Verificar la nota en BD
    acts = (await client.get(f"{_CONTACTS}/{contact_full.id}/activities", headers=auth_asesor)).json()
    notes = [a for a in acts["items"] if a["activity_type"] == "note"]
    assert any("cotización" in (n["body"] or "") for n in notes), (
        "No se encontró la nota con 'cotización' en las actividades"
    )


# ── P-06-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_activity_call_with_duration(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_activity registra llamada con duration_minutes en extra_data."""
    mock_claude_haiku.returns_json({
        "intent_type": "accion",
        "response_text": "Registrando llamada.",
        "requires_confirmation": False,
        "actions": [{
            "type": "contact_activity",
            "params": {
                "contact_ref": contact_full.name,
                "activity_type": "call",
                "title": "Llamada de seguimiento",
                "body": "No contestó",
                "due_date": None,
                "duration_minutes": 5,
            },
        }],
        "data_query": None,
        "suggested_actions": [],
    })

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"llamé a {contact_full.name} 5 min, no contestó"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action_data"]["action"] == "activity_created"

    # Verificar que la llamada existe y tiene extra_data con duration_minutes
    acts = (await client.get(f"{_CONTACTS}/{contact_full.id}/activities", headers=auth_asesor)).json()
    calls = [a for a in acts["items"] if a["activity_type"] == "call"]
    assert len(calls) > 0, "No se encontró la llamada en actividades"
    call = calls[0]
    assert call["extra_data"] is not None, "extra_data debe estar presente en la llamada"
    assert call["extra_data"].get("duration_minutes") == 5, (
        f"Se esperaba duration_minutes=5, obtenido: {call['extra_data']}"
    )


# ── P-06-06 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_activity_task_with_due_date(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_activity crea tarea con due_date en ISO."""
    due_iso = "2026-06-19T10:00:00"
    mock_claude_haiku.returns_json({
        "intent_type": "accion",
        "response_text": "Tarea creada.",
        "requires_confirmation": False,
        "actions": [{
            "type": "contact_activity",
            "params": {
                "contact_ref": contact_full.name,
                "activity_type": "task",
                "title": "Llamar el jueves",
                "body": None,
                "due_date": due_iso,
                "duration_minutes": None,
            },
        }],
        "data_query": None,
        "suggested_actions": [],
    })

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"tarea: llamar a {contact_full.name} el jueves a las 10am"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action_data"]["action"] == "activity_created"

    # Verificar tarea con due_date en BD
    acts = (await client.get(f"{_CONTACTS}/{contact_full.id}/activities", headers=auth_asesor)).json()
    tasks = [a for a in acts["items"] if a["activity_type"] == "task"]
    assert len(tasks) > 0, "No se encontró la tarea en actividades"
    assert tasks[0]["due_date"] is not None, "La tarea debe tener due_date"
    assert "2026-06-19" in tasks[0]["due_date"]


# ── P-06-07 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_activity_infers_contact_from_screen(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_activity sin contact_ref usa el contacto en pantalla (context_contact_id)."""
    mock_claude_haiku.returns_contact_activity(
        contact_ref="",
        activity_type="note",
        body="Nota sobre el contacto actual",
    )

    acts_before = (
        await client.get(f"{_CONTACTS}/{contact_full.id}/activities", headers=auth_asesor)
    ).json()["total"]

    resp = await client.post(
        _AIBAR,
        json=_cmd(
            "registra nota: Nota sobre el contacto actual",
            screen=f"contacts/{contact_full.id}",
            contact_id=str(contact_full.id),
        ),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action_data"]["action"] == "activity_created"

    acts_after = (
        await client.get(f"{_CONTACTS}/{contact_full.id}/activities", headers=auth_asesor)
    ).json()["total"]
    assert acts_after == acts_before + 1


# ── P-06-08 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_update_contact_not_in_tenant_fails(
    client: AsyncClient,
    auth_asesor: dict,
    auth_other: dict,
    mock_claude_haiku,
) -> None:
    """contact_update no puede modificar un contacto de otro tenant."""
    # Crear contacto en tenant_b
    phone_b = f"+521{uuid.uuid4().int % 10**9:09d}"
    r = await client.post(
        _CONTACTS,
        json={"wa_phone": phone_b, "name": "Contacto Otro Tenant"},
        headers=auth_other,
    )
    assert r.status_code == 201, r.text

    # Desde tenant_a, intentar actualizar ese contacto por nombre
    mock_claude_haiku.returns_contact_update(
        contact_ref="Contacto Otro Tenant",
        field="status",
        new_value="nuevo",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd("cambia el status de Contacto Otro Tenant a nuevo"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    # El executor filtra por tenant_a → no encuentra el contacto → "ambiguous"
    assert ad["action"] == "ambiguous", (
        f"No debe poder modificar contacto de otro tenant, obtenido: {ad['action']}"
    )


# ── P-06-09 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_update_invalid_status_returns_error(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_update con status inválido retorna action='error'."""
    mock_claude_haiku.returns_contact_update(
        contact_ref=contact_full.name,
        field="status",
        new_value="status_inventado",
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"cambia el status de {contact_full.name} a status_inventado"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "error"
    assert "inválido" in ad["message"].lower() or "invalido" in ad["message"].lower()


# ── P-06-10 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_activity_creates_last_activity_summary(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_activity actualiza last_activity_summary del contacto."""
    note_body = "Reunión productiva con el cliente"
    mock_claude_haiku.returns_contact_activity(
        contact_ref=contact_full.name,
        activity_type="meeting",
        body=note_body,
    )

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"registra reunión con {contact_full.name}: {note_body}"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action_data"]["action"] == "activity_created"

    # Verificar que last_activity_summary se actualizó
    contact = (await client.get(f"{_CONTACTS}/{contact_full.id}", headers=auth_asesor)).json()
    summary = contact["last_activity_summary"]
    assert summary is not None
    assert "Reunión" in summary or "reunión" in summary or "productiva" in summary
