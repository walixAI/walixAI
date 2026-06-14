"""
Sprint 8A · P-05 — WalixAIBar contact_read intent
Prueba la búsqueda de contactos desde el AI Bar.

Adaptaciones al spec original:
  - Endpoint: POST /api/ai/command  (no /api/v1/aibar/command)
  - Body: {message, context, history}
  - Respuesta: resp.json()["action_data"]
  - action values: "contacts_not_found" (no "no_results"), "contact_found", "contacts_found"
  - Status en minúsculas: "calificado" (no "Calificado")
  - Mock: fixture mock_claude_haiku
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


# ── P-05-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_by_status_returns_list(
    client: AsyncClient,
    auth_asesor: dict,
    contacts_list: list[Lead],  # 12 contactos; 2 con status="calificado"
    mock_claude_haiku,
) -> None:
    """contact_read filtrando por status retorna contactos con ese status."""
    mock_claude_haiku.returns_contact_read(status=["calificado"])

    resp = await client.post(
        _AIBAR,
        json=_cmd("muéstrame los contactos calificados"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad is not None
    assert ad["action"] in ("contacts_found", "contact_found"), (
        f"Se esperaba contacts_found o contact_found, obtenido: {ad['action']}"
    )
    # Todos los contactos retornados deben tener el status correcto
    if ad["action"] == "contacts_found":
        for c in ad["contacts"]:
            assert c["status"] == "calificado"


# ── P-05-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_no_results_friendly_message(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_read sin resultados retorna action='contacts_not_found' con mensaje."""
    mock_claude_haiku.returns_contact_read(q="ZZZ_empresa_que_no_existe_xyzabc")

    resp = await client.post(
        _AIBAR,
        json=_cmd("busca contactos de ZZZ_empresa_que_no_existe_xyzabc"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad is not None
    assert ad["action"] == "contacts_not_found", (
        f"Se esperaba 'contacts_not_found', obtenido: {ad['action']}"
    )
    assert "message" in ad
    assert len(ad["message"]) > 0, "El mensaje amigable no debe estar vacío"


# ── P-05-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_single_result_provides_navigate(
    client: AsyncClient,
    auth_asesor: dict,
    mock_claude_haiku,
) -> None:
    """contact_read con 1 resultado incluye navigate_to con el id del contacto."""
    unique_name = f"ContactoUnico{uuid.uuid4().hex[:8]}"
    unique_phone = f"+521{uuid.uuid4().int % 10**9:09d}"

    # Crear el contacto directamente via API
    r = await client.post(
        _CONTACTS,
        json={"wa_phone": unique_phone, "name": unique_name},
        headers=auth_asesor,
    )
    assert r.status_code == 201, r.text
    created_id = r.json()["id"]

    mock_claude_haiku.returns_contact_read(q=unique_name)

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"busca a {unique_name}"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "contact_found", (
        f"Se esperaba 'contact_found' con 1 resultado único, obtenido: {ad['action']}"
    )
    assert "navigate_to" in ad
    assert created_id in ad["navigate_to"], (
        f"navigate_to debe contener el id del contacto encontrado"
    )
    assert ad["contact"]["id"] == created_id


# ── P-05-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_isolates_by_tenant(
    client: AsyncClient,
    auth_asesor: dict,
    auth_other: dict,
    mock_claude_haiku,
) -> None:
    """contact_read solo retorna contactos del tenant del usuario (aislamiento)."""
    unique_name = f"ContactoTenantB_{uuid.uuid4().hex[:6]}"
    unique_phone = f"+521{uuid.uuid4().int % 10**9:09d}"

    # Crear contacto en tenant_b
    r = await client.post(
        _CONTACTS,
        json={"wa_phone": unique_phone, "name": unique_name},
        headers=auth_other,
    )
    assert r.status_code == 201, r.text

    # Buscar desde tenant_a — no debe encontrarlo
    mock_claude_haiku.returns_contact_read(q=unique_name)

    resp = await client.post(
        _AIBAR,
        json=_cmd(f"busca {unique_name}"),
        headers=auth_asesor,  # usuario de tenant_a
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "contacts_not_found", (
        "Un usuario de tenant_a no debe ver contactos de tenant_b"
    )


# ── P-05-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_multiple_results_returns_first_five(
    client: AsyncClient,
    auth_asesor: dict,
    contacts_list: list[Lead],  # 12 contactos en tenant_a
    mock_claude_haiku,
) -> None:
    """contact_read con múltiples resultados retorna máx 5 contactos en la respuesta."""
    assert len(contacts_list) == 12  # validar fixture

    # Búsqueda sin filtros → retorna todos (12)
    mock_claude_haiku.returns_contact_read()  # empty params

    resp = await client.post(
        _AIBAR,
        json=_cmd("muéstrame todos mis contactos"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "contacts_found", (
        f"Con 12 contactos se esperaba 'contacts_found', obtenido: {ad['action']}"
    )
    assert len(ad["contacts"]) <= 5, (
        f"El AIBar debe retornar máx 5 contactos, retornó {len(ad['contacts'])}"
    )
    assert ad["total"] > 5, (
        f"El total debe ser > 5 (hay 12), obtenido: {ad['total']}"
    )
    assert "message" in ad


# ── P-05-06 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_context_screen_contact_detail(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """En pantalla de ficha con 1 contacto, contact_read sin filtros lo encuentra."""
    # Con solo contact_full en el tenant, q=None retorna 1 resultado → contact_found
    mock_claude_haiku.returns_contact_read()  # empty params

    resp = await client.post(
        _AIBAR,
        json=_cmd(
            "muéstrame este contacto",
            screen=f"contacts/{contact_full.id}",
            contact_id=str(contact_full.id),
        ),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] == "contact_found", (
        f"Con 1 contacto en el tenant se esperaba 'contact_found', obtenido: {ad['action']}"
    )
    assert ad["contact"]["id"] == str(contact_full.id)
    assert "navigate_to" in ad
    assert str(contact_full.id) in ad["navigate_to"]


# ── P-05-07 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_by_company_filter(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_read filtrando por empresa retorna los contactos correctos."""
    mock_claude_haiku.returns_contact_read(company="Farmacia San Juan")

    resp = await client.post(
        _AIBAR,
        json=_cmd("busca contactos de Farmacia San Juan"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    assert ad["action"] in ("contact_found", "contacts_found")
    # El contacto encontrado debe ser contact_full (tiene company="Farmacia San Juan")
    if ad["action"] == "contact_found":
        assert ad["contact"]["id"] == str(contact_full.id)


# ── P-05-08 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aibar_read_date_range_today(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    mock_claude_haiku,
) -> None:
    """contact_read con date_range='today' filtra por contactos creados hoy."""
    mock_claude_haiku.returns_contact_read(date_range="today")

    resp = await client.post(
        _AIBAR,
        json=_cmd("cuántos contactos entraron hoy"),
        headers=auth_asesor,
    )
    assert resp.status_code == 200, resp.text

    ad = resp.json()["action_data"]
    # contact_full fue creado "ahora" → debe aparecer en today
    assert ad["action"] in ("contact_found", "contacts_found"), (
        f"Se esperaba al menos 1 contacto de hoy, obtenido: {ad['action']}"
    )
