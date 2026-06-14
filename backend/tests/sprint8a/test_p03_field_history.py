"""
Sprint 8A · P-03 — Field history en contactos
Verifica el registro automático de cambios de campo vía PATCH /api/v1/contacts/{id}.

Adaptaciones respecto al spec original:
  - Fixtures retornan ORM objects (`.id`, no `['id']`).
  - Respuesta de activities usa `extra_data`, no `metadata`.
  - Valores de status en minúsculas: "calificado", "nuevo", "en_calificacion".
  - Patch target: app.api.contacts.create_field_change_activity (donde se importa).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.lead import Lead
from app.models.user import User

_CONTACTS = "/api/v1/contacts"


def _acts_url(contact_id: uuid.UUID) -> str:
    return f"{_CONTACTS}/{contact_id}/activities"


# ── P-03-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_change_creates_activity(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """Cambiar el status de un contacto crea una activity de tipo system."""
    cid = contact_full.id

    before = (await client.get(_acts_url(cid), headers=auth_asesor)).json()
    count_before = before["total"]

    # contact_full tiene status="calificado"; cambiamos a "nuevo"
    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"status": "nuevo"},
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    after = (await client.get(_acts_url(cid), headers=auth_asesor)).json()
    assert after["total"] == count_before + 1

    latest = after["items"][0]
    assert latest["activity_type"] == "system"
    assert "Estatus" in latest["body"]
    assert "nuevo" in latest["body"]


# ── P-03-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_field_history_metadata(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """La activity de cambio de campo tiene extra_data con old_value y new_value."""
    cid = contact_full.id

    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"company": "Nueva Empresa SA"},
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    acts = (await client.get(_acts_url(cid), headers=auth_asesor)).json()
    latest = acts["items"][0]

    meta = latest["extra_data"]
    assert meta is not None, "extra_data debe estar presente en la activity de field history"
    assert meta["field"] == "company"
    assert meta["new_value"] == "Nueva Empresa SA"
    assert "old_value" in meta
    assert "changed_by_id" in meta
    assert "changed_by_name" in meta


# ── P-03-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_change_no_activity(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """PATCH sin cambios reales no crea activities de field history."""
    cid = contact_full.id

    count_before = (await client.get(_acts_url(cid), headers=auth_asesor)).json()["total"]

    # Enviar el mismo status que ya tiene (calificado → calificado)
    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"status": "calificado"},
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    count_after = (await client.get(_acts_url(cid), headers=auth_asesor)).json()["total"]
    assert count_after == count_before, "No debe crearse activity cuando el valor no cambia"


# ── P-03-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_fields_creates_multiple_activities(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """PATCH con 3 campos distintos crea exactamente 3 activities de field history."""
    cid = contact_full.id

    count_before = (await client.get(_acts_url(cid), headers=auth_asesor)).json()["total"]

    # contact_full: status=calificado, company="Farmacia San Juan", last_name="García"
    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={
            "status": "en_calificacion",
            "company": "Empresa XYZ",
            "last_name": "Apellido Nuevo",
        },
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    count_after = (await client.get(_acts_url(cid), headers=auth_asesor)).json()["total"]
    assert count_after == count_before + 3, (
        f"Se esperaban 3 activities (una por campo), pero se crearon {count_after - count_before}"
    )


# ── P-03-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_field_history_activity_is_immutable(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """Una activity de tipo system no puede editarse via PATCH activities."""
    cid = contact_full.id

    # Crear una activity system cambiando el nombre
    await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"name": "Nombre Cambiado"},
        headers=auth_asesor,
    )

    acts = (await client.get(_acts_url(cid), headers=auth_asesor)).json()
    sys_activity = next(
        (a for a in acts["items"] if a["activity_type"] == "system"), None
    )
    if sys_activity is None:
        pytest.skip("No hay activities de tipo system para probar")

    resp = await client.patch(
        f"{_CONTACTS}/{cid}/activities/{sys_activity['id']}",
        json={"body": "Texto modificado"},
        headers=auth_asesor,
    )
    assert resp.status_code == 403


# ── P-03-06 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assigned_user_change_shows_names(
    client: AsyncClient,
    auth_asesor: dict,
    auth_gerente: dict,
    contact_full: Lead,
    user_gerente: User,
) -> None:
    """Cambiar vendedor asignado registra nombres en el body, no UUIDs."""
    cid = contact_full.id

    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"assigned_to": str(user_gerente.id)},
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    acts = (await client.get(_acts_url(cid), headers=auth_asesor)).json()
    latest = acts["items"][0]

    assert latest["activity_type"] == "system"
    assert user_gerente.name in latest["body"], (
        f"El nombre del gerente '{user_gerente.name}' debe aparecer en el body"
    )
    assert str(user_gerente.id) not in latest["body"], (
        "El UUID no debe aparecer en el body — debe resolverse a nombre"
    )


# ── P-03-07 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_last_activity_summary_updated(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """PATCH de contacto actualiza last_activity_summary del lead."""
    cid = contact_full.id

    # contact_full parte con status=calificado; cambiamos a nuevo
    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"status": "nuevo"},
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    contact = (await client.get(f"{_CONTACTS}/{cid}", headers=auth_asesor)).json()
    summary = contact["last_activity_summary"]
    assert summary is not None, "last_activity_summary debe actualizarse tras un cambio"
    # El resumen debe mencionar el campo o los valores involucrados
    assert "Estatus" in summary or "nuevo" in summary or "calificado" in summary


# ── P-03-08 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_field_history_does_not_rollback_on_error(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """Si falla la creación de la activity, el PATCH del contacto se mantiene."""
    cid = contact_full.id

    # El patch target correcto es donde se usa la función (app.api.contacts),
    # no donde está definida (app.services.activity_service).
    with patch(
        "app.api.contacts.create_field_change_activity",
        new=AsyncMock(side_effect=Exception("Fallo simulado de activity")),
    ):
        resp = await client.patch(
            f"{_CONTACTS}/{cid}",
            json={"company": "Empresa Sin Activity"},
            headers=auth_asesor,
        )
        assert resp.status_code == 200, (
            "El PATCH debe completarse aunque falle la creación de field history"
        )

    # El campo debe haberse guardado a pesar del error
    contact = (await client.get(f"{_CONTACTS}/{cid}", headers=auth_asesor)).json()
    assert contact["company"] == "Empresa Sin Activity"


# ── P-03-09 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tag_change_creates_single_activity(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
    tag_vip,
) -> None:
    """Cambiar etiquetas crea exactamente 1 activity 'Etiquetas actualizadas'."""
    cid = contact_full.id

    count_before = (await client.get(_acts_url(cid), headers=auth_asesor)).json()["total"]

    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"tag_ids": [str(tag_vip.id)]},
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    after = (await client.get(_acts_url(cid), headers=auth_asesor)).json()
    assert after["total"] == count_before + 1

    latest = after["items"][0]
    assert latest["activity_type"] == "system"
    assert "Etiquetas" in latest["body"]


# ── P-03-10 (bonus) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_field_history_body_format(
    client: AsyncClient,
    auth_asesor: dict,
    contact_full: Lead,
) -> None:
    """El body de la activity sigue el formato '{Label} cambiado: {old} → {new}'."""
    cid = contact_full.id

    r = await client.patch(
        f"{_CONTACTS}/{cid}",
        json={"name": "Nuevo Nombre"},
        headers=auth_asesor,
    )
    assert r.status_code == 200, r.text

    acts = (await client.get(_acts_url(cid), headers=auth_asesor)).json()
    latest = acts["items"][0]

    body = latest["body"]
    assert "Nombre" in body          # label del campo
    assert "cambiado" in body        # verbo estándar
    assert "→" in body               # separador old→new
    assert "Nuevo Nombre" in body    # nuevo valor
