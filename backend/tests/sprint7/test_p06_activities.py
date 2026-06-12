"""
Sprint 7 · P-06 — Activities CRUD
Tests for POST / GET / PATCH /api/v1/contacts/{lead_id}/activities

Response fields (snake_case):
  activity_type, title, body, extra_data, due_date, completed_at,
  created_by, created_by_name, created_at, updated_at

Type filter: ?type=note  (alias="type" — NOT ?type[]=note)
Page size: 20

system activity rules:
  POST activity_type="system"  → 403  (route blocks it before any DB write)
  POST activity_type="unknown" → 422  (Pydantic validator: not in ACTIVITY_TYPES)
  PATCH on a system activity   → 403  (system check runs before creator check)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.tenant import Tenant
from app.models.user import User

# ── Helpers ───────────────────────────────────────────────────────────────────

_BASE = "/api/v1/contacts"


def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


def activities_url(lead_id: str) -> str:
    return f"{_BASE}/{lead_id}/activities"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    """Asesor as a dict {id, name, token}."""
    return {
        "id": str(asesor_user.id),
        "name": asesor_user.name or "",
        "token": asesor_token,
    }


@pytest_asyncio.fixture()
async def user_gerente(manager_user: User, manager_token: str) -> dict:
    return {
        "id": str(manager_user.id),
        "name": manager_user.name or "",
        "token": manager_token,
    }


@pytest_asyncio.fixture()
async def contact_full(client: AsyncClient, user_asesor: dict) -> dict:
    """Contact created via API; returns ContactDetail JSON."""
    r = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": "+5215512349001", "name": "Activ Test", "last_name": "Lead"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r2 = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert r2.status_code == 200, r2.text
    return r2.json()


# ── CREATE — POST /{lead_id}/activities ───────────────────────────────────────


@pytest.mark.parametrize(
    "activity_type, payload",
    [
        ("note", {"activity_type": "note", "body": "Una nota de prueba"}),
        (
            "call",
            {
                "activity_type": "call",
                "title": "Llamada",
                "extra_data": {"duration_minutes": 15, "outcome": "answered"},
            },
        ),
        (
            "task",
            {
                "activity_type": "task",
                "title": "Tarea pendiente",
                "due_date": "2026-12-31T10:00:00Z",
            },
        ),
        (
            "meeting",
            {
                "activity_type": "meeting",
                "title": "Reunión",
                "due_date": "2026-12-31T10:00:00Z",
                "extra_data": {"duration_minutes": 60},
            },
        ),
        (
            "email",
            {"activity_type": "email", "title": "Asunto del email", "body": "Contenido"},
        ),
    ],
)
async def test_create_activity_all_types(
    client: AsyncClient,
    contact_full: dict,
    user_asesor: dict,
    activity_type: str,
    payload: dict,
) -> None:
    """Crear actividad de cada tipo válido → 201, activity_type correcto, creator name."""
    r = await client.post(
        activities_url(contact_full["id"]),
        json=payload,
        headers=auth(user_asesor),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["activity_type"] == activity_type
    assert data["created_by_name"] == user_asesor["name"]
    assert data["created_by"] == user_asesor["id"]


async def test_create_system_activity_forbidden(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """POST con activity_type='system' es bloqueado con 403 (no con 422)."""
    r = await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "system", "body": "hack"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 403


async def test_create_invalid_activity_type_returns_422(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Tipo no reconocido es rechazado con 422 por el validador de Pydantic."""
    r = await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "unknown_type", "body": "test"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 422


async def test_create_activity_unknown_lead_returns_404(
    client: AsyncClient, user_asesor: dict
) -> None:
    """POST en un lead inexistente retorna 404."""
    r = await client.post(
        activities_url(str(uuid.uuid4())),
        json={"activity_type": "note", "body": "orphan"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 404


async def test_create_activity_no_auth_returns_401(
    client: AsyncClient, contact_full: dict
) -> None:
    """POST sin token retorna 401."""
    r = await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "note", "body": "anon"},
    )
    assert r.status_code == 401


# ── READ — GET /{lead_id}/activities ─────────────────────────────────────────


async def test_get_activities_empty(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Contacto sin actividades retorna items=[] y total=0."""
    r = await client.get(activities_url(contact_full["id"]), headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1


async def test_get_activities_paginated(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Con 25 actividades, página 1 retorna 20 y total=25."""
    url = activities_url(contact_full["id"])
    for i in range(25):
        r = await client.post(
            url,
            json={"activity_type": "note", "body": f"Nota {i}"},
            headers=auth(user_asesor),
        )
        assert r.status_code == 201

    r = await client.get(url, headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 20
    assert data["total"] == 25
    assert data["page"] == 1


async def test_get_activities_page_2(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Página 2 retorna los 5 restantes."""
    url = activities_url(contact_full["id"])
    for i in range(25):
        await client.post(
            url,
            json={"activity_type": "note", "body": f"Nota {i}"},
            headers=auth(user_asesor),
        )

    r = await client.get(f"{url}?page=2", headers=auth(user_asesor))
    data = r.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2
    assert data["total"] == 25


async def test_get_activities_filter_by_type(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Filtro ?type=note retorna solo actividades de tipo note."""
    url = activities_url(contact_full["id"])
    await client.post(url, json={"activity_type": "note", "body": "nota"}, headers=auth(user_asesor))
    await client.post(url, json={"activity_type": "call", "title": "llamada"}, headers=auth(user_asesor))

    r = await client.get(f"{url}?type=note", headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    for activity in data["items"]:
        assert activity["activity_type"] == "note"


async def test_get_activities_filter_multiple_types(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Filtro ?type=note&type=call retorna actividades de ambos tipos (OR)."""
    url = activities_url(contact_full["id"])
    await client.post(url, json={"activity_type": "note", "body": "nota"}, headers=auth(user_asesor))
    await client.post(url, json={"activity_type": "call", "title": "llamada"}, headers=auth(user_asesor))
    await client.post(url, json={"activity_type": "email", "title": "email"}, headers=auth(user_asesor))

    r = await client.get(f"{url}?type=note&type=call", headers=auth(user_asesor))
    data = r.json()
    assert data["total"] == 2
    for activity in data["items"]:
        assert activity["activity_type"] in {"note", "call"}


async def test_get_activities_ordered_newest_first(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Las actividades se retornan con la más reciente primero."""
    url = activities_url(contact_full["id"])
    for title in ("Primera", "Segunda", "Tercera"):
        await client.post(url, json={"activity_type": "note", "body": title}, headers=auth(user_asesor))

    r = await client.get(url, headers=auth(user_asesor))
    bodies = [a["body"] for a in r.json()["items"]]
    assert bodies[0] == "Tercera"   # newest first
    assert bodies[-1] == "Primera"


# ── UPDATE — PATCH /{lead_id}/activities/{activity_id} ───────────────────────


async def test_patch_activity_by_creator(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """El creador puede editar el body y el title de su actividad."""
    create_r = await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "note", "body": "original"},
        headers=auth(user_asesor),
    )
    act_id = create_r.json()["id"]

    r = await client.patch(
        f"{activities_url(contact_full['id'])}/{act_id}",
        json={"body": "editado", "title": "Título añadido"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["body"] == "editado"
    assert data["title"] == "Título añadido"


async def test_patch_activity_by_other_user_forbidden(
    client: AsyncClient, contact_full: dict, user_asesor: dict, user_gerente: dict
) -> None:
    """Otro usuario (incluso gerente) NO puede editar la actividad del asesor."""
    create_r = await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "note", "body": "privada"},
        headers=auth(user_asesor),
    )
    act_id = create_r.json()["id"]

    r = await client.patch(
        f"{activities_url(contact_full['id'])}/{act_id}",
        json={"body": "hack"},
        headers=auth(user_gerente),
    )
    assert r.status_code == 403


async def test_patch_task_complete(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Marcar una tarea como completada seteando completed_at."""
    create_r = await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "task", "title": "Tarea a completar"},
        headers=auth(user_asesor),
    )
    act_id = create_r.json()["id"]
    assert create_r.json()["completed_at"] is None

    now_iso = datetime.now(timezone.utc).isoformat()
    r = await client.patch(
        f"{activities_url(contact_full['id'])}/{act_id}",
        json={"completed_at": now_iso},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    assert r.json()["completed_at"] is not None


async def test_patch_activity_unknown_id_returns_404(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """PATCH de un activity_id inexistente retorna 404."""
    r = await client.patch(
        f"{activities_url(contact_full['id'])}/{uuid.uuid4()}",
        json={"body": "test"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 404


# ── SYSTEM ACTIVITY IMMUTABILITY ──────────────────────────────────────────────


async def test_system_activity_immutable(
    client: AsyncClient,
    contact_full: dict,
    user_asesor: dict,
    db: AsyncSession,
    tenant: Tenant,
) -> None:
    """Actividades de tipo 'system' insertadas en BD son inmutables vía API."""
    sys_act = Activity(
        lead_id=uuid.UUID(contact_full["id"]),
        tenant_id=tenant.id,
        activity_type="system",
        body="Evento automático del sistema",
        created_by=None,  # system activities have no human creator
    )
    db.add(sys_act)
    await db.flush()

    r = await client.patch(
        f"{activities_url(contact_full['id'])}/{sys_act.id}",
        json={"body": "intento de modificación"},
        headers=auth(user_asesor),
    )
    assert r.status_code == 403
    detail = r.json().get("detail", "")
    assert "inmutabl" in detail.lower() or "system" in detail.lower()


async def test_system_activity_not_creatable_via_api(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Verificar que el sistema no puede crear actividades de tipo 'system' por API."""
    r = await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "system", "body": "test"},
        headers=auth(user_asesor),
    )
    # 403 — route explicitly rejects system type before reaching DB
    assert r.status_code == 403


# ── SIDE EFFECTS ──────────────────────────────────────────────────────────────


async def test_activity_updates_last_activity_summary(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Crear actividad actualiza last_activity_summary en el contacto (usa title > body > type)."""
    title = "Reunión de seguimiento importante"
    await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "meeting", "title": title},
        headers=auth(user_asesor),
    )

    detail = await client.get(
        f"/api/v1/contacts/{contact_full['id']}", headers=auth(user_asesor)
    )
    assert detail.status_code == 200
    assert detail.json()["last_activity_summary"] == title


async def test_activity_summary_falls_back_to_body(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Si no hay title, last_activity_summary usa el body."""
    body_text = "Contenido de la nota"
    await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "note", "body": body_text},
        headers=auth(user_asesor),
    )
    detail = await client.get(
        f"/api/v1/contacts/{contact_full['id']}", headers=auth(user_asesor)
    )
    assert detail.json()["last_activity_summary"] == body_text


async def test_activity_summary_falls_back_to_type(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Si no hay title ni body, last_activity_summary usa el activity_type."""
    await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "call"},
        headers=auth(user_asesor),
    )
    detail = await client.get(
        f"/api/v1/contacts/{contact_full['id']}", headers=auth(user_asesor)
    )
    assert detail.json()["last_activity_summary"] == "call"


async def test_get_activities_created_by_name_populated(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """La respuesta del GET incluye created_by_name con el nombre del creador."""
    await client.post(
        activities_url(contact_full["id"]),
        json={"activity_type": "note", "body": "test"},
        headers=auth(user_asesor),
    )
    r = await client.get(activities_url(contact_full["id"]), headers=auth(user_asesor))
    item = r.json()["items"][0]
    assert item["created_by_name"] == user_asesor["name"]
    assert item["created_by"] == user_asesor["id"]
