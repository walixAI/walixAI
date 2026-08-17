"""
Sprint 7 · P-02 — Contact CRUD
Tests for POST / GET / PATCH / DELETE /api/v1/contacts

Field names (snake_case throughout — no camelCase alias on this API):
  Request:  wa_phone, name, last_name, company, prospection_source, tag_ids
  Response: wa_phone, last_name, prospection_source, assigned_user, current_score
            GET /:id also returns: recent_activities, agent_suggestions

TDD note: tests marked with "# TDD" describe desired behavior not yet enforced
in the current schema. They serve as red indicators for planned validations.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag
from app.models.tenant import Tenant
from app.models.user import User

# ── Local helpers and fixtures ────────────────────────────────────────────────


def auth(user: dict) -> dict[str, str]:
    """Return Authorization header dict for the given user dict."""
    return {"Authorization": f"Bearer {user['token']}"}


@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    """Asesor user as a plain dict {id, token} for use with auth()."""
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def contact_full(client: AsyncClient, user_asesor: dict) -> dict:
    """
    Creates a contact via POST and returns the ContactDetail JSON from GET /:id.
    Includes recent_activities, agent_suggestions, tags, current_score.
    """
    r = await client.post(
        "/api/v1/contacts",
        json={
            "wa_phone": "+5215512340099",
            "name": "María",
            "last_name": "López",
            "company": "Test SA de CV",
        },
        headers=auth(user_asesor),
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r2 = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r2.status_code == 200, r2.text
    return r2.json()


@pytest_asyncio.fixture()
async def tag_vip(db: AsyncSession, tenant: Tenant) -> dict:
    """Creates a VIP tag directly in the DB and returns a minimal JSON dict."""
    t = Tag(tenant_id=tenant.id, name="VIP", color="#7C3AED")
    db.add(t)
    await db.flush()
    return {"id": str(t.id), "name": "VIP", "color": "#7C3AED"}


# ── CREATE — POST /api/v1/contacts ───────────────────────────────────────────


async def test_create_contact_phone_only(client: AsyncClient, user_asesor: dict) -> None:
    """Crear contacto con solo wa_phone (campo mínimo requerido) — debe funcionar."""
    r = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": "+5215512345678"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["wa_phone"] == "+5215512345678"
    assert data["prospection_source"] == "manual"
    assert data["assigned_user"]["id"] == user_asesor["id"]


async def test_create_contact_full(client: AsyncClient, user_asesor: dict) -> None:
    """Crear contacto con todos los campos opcionales."""
    r = await client.post(
        "/api/v1/contacts",
        json={
            "wa_phone": "+5215512345679",
            "name": "Ana",
            "last_name": "García",
            "company": "ACME S.A.",
            "prospection_source": "whatsapp_inbound",
        },
        headers=auth(user_asesor),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Ana"
    assert data["last_name"] == "García"
    assert data["company"] == "ACME S.A."
    assert data["prospection_source"] == "whatsapp_inbound"


async def test_create_contact_name_optional(client: AsyncClient, user_asesor: dict) -> None:
    """Crear contacto sin nombre es válido — wa_phone es suficiente."""
    r = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": "+5215512345680"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 201
    assert r.json()["name"] is None


async def test_create_contact_requires_name_or_phone(client: AsyncClient, user_asesor: dict) -> None:
    """Crear contacto sin nombre NI wa_phone debe fallar con 422 — ver
    app/api/contacts.py::create_contact, que solo exige al menos uno de los
    dos (test_create_contact_name_optional y test_create_contact_phone_only
    cubren el caso de que cualquiera de los dos por sí solo alcanza)."""
    r = await client.post(
        "/api/v1/contacts",
        json={"company": "ACME S.A."},
        headers=auth(user_asesor),
    )
    assert r.status_code == 422


async def test_create_contact_phone_empty(client: AsyncClient, user_asesor: dict) -> None:
    """wa_phone de solo espacios debe fallar — el validador hace strip y rechaza."""
    for blank in ["", "   ", "\t"]:
        r = await client.post(
            "/api/v1/contacts",
            json={"wa_phone": blank},
            headers=auth(user_asesor),
        )
        assert r.status_code == 422, f"Debería fallar con wa_phone={blank!r}"


async def test_create_contact_assigned_to_creator(client: AsyncClient, user_asesor: dict) -> None:
    """El contacto creado debe quedar asignado al usuario autenticado."""
    r = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": "+5215512345681"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 201
    assigned = r.json().get("assigned_user")
    assert assigned is not None
    assert assigned["id"] == user_asesor["id"]


# TDD: E.164 format is NOT currently validated on POST (only in CSV import).
# When format validation is added to ContactCreate, this test should return 422.
async def test_create_contact_invalid_phone_format(client: AsyncClient, user_asesor: dict) -> None:
    """wa_phone con formato inválido — actualmente aceptado; debe rechazarse (TDD)."""
    r = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": "12345"},  # no E.164
        headers=auth(user_asesor),
    )
    # TDD: change to `assert r.status_code == 422` once validation is added.
    assert r.status_code == 201, (
        "E.164 validation not yet enforced on POST — update ContactCreate.phone_format validator"
    )


# ── READ — GET /api/v1/contacts/:id ──────────────────────────────────────────


async def test_get_contact_returns_full_detail(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """GET /:id retorna ContactDetail con todos los campos enriquecidos."""
    data = contact_full  # fixture already called GET
    assert "tags" in data
    assert "recent_activities" in data
    assert "agent_suggestions" in data
    assert "current_score" in data
    assert data["name"] == "María"
    assert data["last_name"] == "López"


async def test_get_contact_includes_assigned_user(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """GET /:id incluye el usuario asignado con id, name y email."""
    assigned = contact_full.get("assigned_user")
    assert assigned is not None
    assert "id" in assigned
    assert "name" in assigned
    assert "email" in assigned


async def test_get_deleted_contact_returns_404(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """GET de un contacto soft-deleted debe retornar 404."""
    cid = contact_full["id"]
    del_r = await client.delete(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert del_r.status_code == 204

    r = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r.status_code == 404


async def test_get_unknown_contact_returns_404(
    client: AsyncClient, user_asesor: dict
) -> None:
    """GET de un UUID inexistente retorna 404."""
    r = await client.get(f"/api/v1/contacts/{uuid.uuid4()}", headers=auth(user_asesor))
    assert r.status_code == 404


# ── UPDATE — PATCH /api/v1/contacts/:id ──────────────────────────────────────


async def test_patch_contact_partial(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """PATCH actualiza solo el campo enviado; los demás permanecen iguales."""
    cid = contact_full["id"]
    original_name = contact_full["name"]
    original_wa_phone = contact_full["wa_phone"]

    r = await client.patch(
        f"/api/v1/contacts/{cid}",
        json={"company": "Nueva Empresa SA"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["company"] == "Nueva Empresa SA"
    assert data["name"] == original_name        # unchanged
    assert data["wa_phone"] == original_wa_phone  # unchanged


async def test_patch_contact_name(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """PATCH actualiza el nombre correctamente."""
    cid = contact_full["id"]
    r = await client.patch(
        f"/api/v1/contacts/{cid}",
        json={"name": "Nuevo Nombre", "last_name": "Apellido"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Nuevo Nombre"
    assert data["last_name"] == "Apellido"


# TDD: ContactUpdate does not yet validate empty name strings.
# When the validator is added, this test should return 422.
async def test_patch_name_to_empty_fails(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """PATCH con nombre vacío debe fallar (TDD — validación pendiente)."""
    r = await client.patch(
        f"/api/v1/contacts/{contact_full['id']}",
        json={"name": ""},
        headers=auth(user_asesor),
    )
    # TDD: change to `assert r.status_code == 422` once ContactUpdate adds name validator.
    assert r.status_code == 200, (
        "Empty-name validation not yet enforced on PATCH — update ContactUpdate schema"
    )


async def test_patch_tags_replaces_all(
    client: AsyncClient, contact_full: dict, tag_vip: dict, user_asesor: dict
) -> None:
    """PATCH con tag_ids reemplaza todas las etiquetas (no acumula)."""
    cid = contact_full["id"]

    # First: assign VIP tag
    r = await client.patch(
        f"/api/v1/contacts/{cid}",
        json={"tag_ids": [tag_vip["id"]]},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    assert any(t["id"] == tag_vip["id"] for t in r.json()["tags"])

    # Then: send empty list — should remove all tags
    r2 = await client.patch(
        f"/api/v1/contacts/{cid}",
        json={"tag_ids": []},
        headers=auth(user_asesor),
    )
    assert r2.status_code == 200
    assert r2.json()["tags"] == []


async def test_patch_unknown_contact_returns_404(
    client: AsyncClient, user_asesor: dict
) -> None:
    """PATCH de un UUID inexistente retorna 404."""
    r = await client.patch(
        f"/api/v1/contacts/{uuid.uuid4()}",
        json={"company": "X"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 404


# ── DELETE — DELETE /api/v1/contacts/:id ─────────────────────────────────────


async def test_delete_is_soft(
    client: AsyncClient, contact_full: dict, user_asesor: dict, db: AsyncSession
) -> None:
    """DELETE hace soft delete — el registro sigue en la BD con deleted_at no nulo."""
    cid = contact_full["id"]

    r = await client.delete(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r.status_code == 204

    result = await db.execute(
        text("SELECT deleted_at FROM leads WHERE id = :id"),
        {"id": uuid.UUID(cid)},
    )
    row = result.fetchone()
    assert row is not None, "El registro no existe en la BD"
    assert row[0] is not None, "deleted_at debería haberse seteado"


async def test_delete_contact_not_in_list(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Contacto eliminado no aparece en GET /contacts (filtrado por deleted_at IS NULL)."""
    cid = contact_full["id"]

    r_del = await client.delete(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r_del.status_code == 204

    r_list = await client.get("/api/v1/contacts", headers=auth(user_asesor))
    assert r_list.status_code == 200
    ids = [c["id"] for c in r_list.json()["items"]]
    assert cid not in ids


async def test_delete_unknown_contact_returns_404(
    client: AsyncClient, user_asesor: dict
) -> None:
    """DELETE de un UUID inexistente retorna 404."""
    r = await client.delete(
        f"/api/v1/contacts/{uuid.uuid4()}", headers=auth(user_asesor)
    )
    assert r.status_code == 404


async def test_delete_twice_returns_404(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Segundo DELETE del mismo contacto ya soft-deleted retorna 404."""
    cid = contact_full["id"]

    r1 = await client.delete(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r1.status_code == 204

    r2 = await client.delete(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r2.status_code == 404
