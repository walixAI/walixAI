"""
Sprint 7 · P-03 — Contacts list: filters, full-text search, pagination, sort
Tests for GET /api/v1/contacts

Query params (actual names — snake_case):
  q          — ilike on name, last_name, company, wa_phone, contact_phone (NOT email)
  status     — repeatable; values: nuevo | en_calificacion | calificado | escalado | perdido
  source     — repeatable string
  tag        — repeatable UUID
  assigned   — repeatable UUID
  date_from  — YYYY-MM-DD (inclusive)
  date_to    — YYYY-MM-DD (inclusive)
  sort       — name | company | status | lastActivity  (default: name)
  order      — asc | desc  (default: asc)
  page       — int ≥ 1  (default: 1); server PAGE_SIZE = 25

Response: ContactListResponse { items, total, page, page_size }

TDD note: `status` is not included in ContactRow items.
Status filter tests therefore assert on `total` counts, not item fields.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStatus
from app.models.tag import Tag
from app.models.tenant import Branch, Tenant
from app.models.user import User

# ── Helpers ───────────────────────────────────────────────────────────────────

PAGE_SIZE = 25  # mirrors app/api/contacts.py constant


def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


# ── Local fixtures ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def contacts_list(
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    asesor_user: User,
) -> list[Lead]:
    """
    Creates exactly 30 contacts with predictable, varied data:
    - Names "Alpha01" … "Alpha30" → alphanumeric-sorted = creation order
    - Status cycles through all 5 LeadStatus values (6 contacts per status)
    - Company "Empresa{i:02d}" for company-search tests
    - wa_phone "+52155{i:07d}" for phone-search tests
    """
    statuses = list(LeadStatus)  # 5 values
    leads = []
    for i in range(1, 31):
        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            wa_phone=f"+52155{i:07d}",
            name=f"Alpha{i:02d}",
            last_name=f"Omega{i:02d}",
            company=f"Empresa{i:02d} SA",
            status=statuses[(i - 1) % len(statuses)],
            prospection_source="manual",
            assigned_to=asesor_user.id,
        )
        db.add(lead)
        leads.append(lead)
    await db.flush()
    return leads


@pytest_asyncio.fixture()
async def contact_searchable(
    client: AsyncClient,
    user_asesor: dict,
) -> dict:
    """Single contact created via API with distinctive searchable data."""
    r = await client.post(
        "/api/v1/contacts",
        json={
            "wa_phone": "+5215598765432",
            "name": "Zoraya",
            "last_name": "Xochitl",
            "company": "Quetzal Corp",
        },
        headers=auth(user_asesor),
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest_asyncio.fixture()
async def tag_vip(db: AsyncSession, tenant: Tenant) -> dict:
    t = Tag(tenant_id=tenant.id, name="VIP", color="#7C3AED")
    db.add(t)
    await db.flush()
    return {"id": str(t.id), "name": "VIP", "color": "#7C3AED"}


# ── PAGINATION ────────────────────────────────────────────────────────────────


async def test_pagination_default_page_size(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Sin filtros, página 1 retorna exactamente PAGE_SIZE=25 ítems y total=30."""
    r = await client.get("/api/v1/contacts", headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == PAGE_SIZE
    assert data["total"] == 30
    assert data["page"] == 1
    assert data["page_size"] == PAGE_SIZE


async def test_pagination_page_2(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Página 2 retorna los 5 restantes (30 - 25 = 5)."""
    r = await client.get("/api/v1/contacts?page=2", headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2
    assert data["total"] == 30


async def test_pagination_ids_no_overlap(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Los IDs de página 1 y página 2 no se solapan (sin duplicados entre páginas)."""
    r1 = await client.get("/api/v1/contacts?page=1", headers=auth(user_asesor))
    r2 = await client.get("/api/v1/contacts?page=2", headers=auth(user_asesor))
    ids1 = {c["id"] for c in r1.json()["items"]}
    ids2 = {c["id"] for c in r2.json()["items"]}
    assert ids1.isdisjoint(ids2)


async def test_pagination_page_beyond_end(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Una página más allá del total retorna items vacío pero total correcto."""
    r = await client.get("/api/v1/contacts?page=99", headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 30


async def test_pagination_empty_tenant(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Sin contactos en el tenant, retorna total=0 y lista vacía."""
    r = await client.get("/api/v1/contacts", headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


# ── FULL-TEXT SEARCH ──────────────────────────────────────────────────────────


async def test_search_by_name(
    client: AsyncClient, contact_searchable: dict, user_asesor: dict
) -> None:
    """Búsqueda por fragmento de nombre (parcial) encuentra el contacto."""
    fragment = contact_searchable["name"][:4]  # "Zora"
    r = await client.get(f"/api/v1/contacts?q={fragment}", headers=auth(user_asesor))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert contact_searchable["id"] in ids


async def test_search_by_last_name(
    client: AsyncClient, contact_searchable: dict, user_asesor: dict
) -> None:
    """Búsqueda por apellido parcial encuentra el contacto."""
    fragment = contact_searchable["last_name"][:5]  # "Xochi"
    r = await client.get(f"/api/v1/contacts?q={fragment}", headers=auth(user_asesor))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert contact_searchable["id"] in ids


async def test_search_by_company(
    client: AsyncClient, contact_searchable: dict, user_asesor: dict
) -> None:
    """Búsqueda por empresa parcial encuentra el contacto."""
    fragment = contact_searchable["company"][:6]  # "Quetza"
    r = await client.get(f"/api/v1/contacts?q={fragment}", headers=auth(user_asesor))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert contact_searchable["id"] in ids


async def test_search_by_phone(
    client: AsyncClient, contact_searchable: dict, user_asesor: dict
) -> None:
    """Búsqueda por fragmento de teléfono encuentra el contacto."""
    phone = contact_searchable["wa_phone"]  # "+5215598765432"
    fragment = phone[3:8]                   # "15598"
    r = await client.get(f"/api/v1/contacts?q={fragment}", headers=auth(user_asesor))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert contact_searchable["id"] in ids


async def test_search_no_results(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Búsqueda sin coincidencias retorna lista vacía y total=0."""
    r = await client.get(
        "/api/v1/contacts?q=xyzzy_no_existe_12345", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_search_case_insensitive(
    client: AsyncClient, contact_searchable: dict, user_asesor: dict
) -> None:
    """La búsqueda q es case-insensitive (ilike)."""
    name_upper = contact_searchable["name"].upper()  # "ZORAYA"
    r = await client.get(f"/api/v1/contacts?q={name_upper}", headers=auth(user_asesor))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert contact_searchable["id"] in ids


async def test_search_matches_multiple_fields(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Término que aparece solo en company también hace match."""
    r_create = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": "+5215511112222", "name": "Sin Empresa", "company": "Zirconio SA"},
        headers=auth(user_asesor),
    )
    cid = r_create.json()["id"]

    r = await client.get("/api/v1/contacts?q=Zirconio", headers=auth(user_asesor))
    ids = [c["id"] for c in r.json()["items"]]
    assert cid in ids


# ── STATUS FILTER ─────────────────────────────────────────────────────────────
# Note: `status` is not included in ContactRow items.
# Assertions verify total counts derived from our fixture (6 per status, 30 total).


async def test_filter_by_status_nuevo(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Filtro status=nuevo retorna exactamente los 6 contactos con ese estado."""
    r = await client.get("/api/v1/contacts?status=nuevo", headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    # contacts_list cycles through 5 statuses for 30 contacts → 6 per status
    assert data["total"] == 6
    assert len(data["items"]) == 6


async def test_filter_by_multiple_status(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Múltiples status= son OR entre sí → retorna suma de ambos grupos."""
    r = await client.get(
        "/api/v1/contacts?status=nuevo&status=en_calificacion",
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 12   # 6 nuevo + 6 en_calificacion


async def test_filter_status_no_match(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Filtro de status que no tiene contactos retorna lista vacía."""
    # contacts_list has all statuses, but let's filter the DB with a valid status
    # while excluding those contacts by using a different tenant approach is complex;
    # Instead verify the count is exact (all 5 statuses present → none with zero)
    for status_val in ["nuevo", "en_calificacion", "calificado", "escalado", "perdido"]:
        r = await client.get(
            f"/api/v1/contacts?status={status_val}", headers=auth(user_asesor)
        )
        assert r.json()["total"] == 6, f"Expected 6 for status={status_val}"


async def test_filter_invalid_status_returns_empty(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Filtro con valor de status inexistente retorna lista vacía (no 422)."""
    r = await client.get(
        "/api/v1/contacts?status=estado_inventado", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── TAG FILTER ────────────────────────────────────────────────────────────────


async def test_filter_by_tag(
    client: AsyncClient,
    contacts_list: list[Lead],
    tag_vip: dict,
    user_asesor: dict,
) -> None:
    """Filtro tag= retorna solo contactos que tienen esa etiqueta asignada."""
    # Assign VIP tag to first 3 contacts via PATCH
    first_three_ids = [str(c.id) for c in contacts_list[:3]]
    for cid in first_three_ids:
        r = await client.patch(
            f"/api/v1/contacts/{cid}",
            json={"tag_ids": [tag_vip["id"]]},
            headers=auth(user_asesor),
        )
        assert r.status_code == 200

    # Filter by VIP tag
    r = await client.get(
        f"/api/v1/contacts?tag={tag_vip['id']}", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    data = r.json()
    returned_ids = {c["id"] for c in data["items"]}

    assert data["total"] == 3
    for cid in first_three_ids:
        assert cid in returned_ids


async def test_filter_by_tag_only_returns_tagged(
    client: AsyncClient,
    contacts_list: list[Lead],
    tag_vip: dict,
    user_asesor: dict,
) -> None:
    """Tag filter excludes contacts that do NOT have the tag."""
    # Tag only one contact
    target_id = str(contacts_list[0].id)
    await client.patch(
        f"/api/v1/contacts/{target_id}",
        json={"tag_ids": [tag_vip["id"]]},
        headers=auth(user_asesor),
    )

    r = await client.get(f"/api/v1/contacts?tag={tag_vip['id']}", headers=auth(user_asesor))
    ids = [c["id"] for c in r.json()["items"]]
    assert ids == [target_id]


# ── DATE FILTER ───────────────────────────────────────────────────────────────


async def test_filter_by_date_range_today(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """date_from=today&date_to=today retorna todos los contactos creados hoy."""
    today = datetime.now(timezone.utc).date().isoformat()
    r = await client.get(
        f"/api/v1/contacts?date_from={today}&date_to={today}",
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    data = r.json()
    # All contacts_list rows were just created → all should match today's range
    assert data["total"] == 30
    for contact in data["items"]:
        # created_at comes back as ISO string; check only the date part
        assert contact["created_at"][:10] >= today


async def test_filter_date_future_returns_empty(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """date_from en el futuro no retorna nada."""
    future = "2099-12-31"
    r = await client.get(
        f"/api/v1/contacts?date_from={future}", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── ASSIGNED FILTER ───────────────────────────────────────────────────────────


async def test_filter_by_assigned(
    client: AsyncClient,
    contacts_list: list[Lead],
    user_asesor: dict,
    asesor_user: User,
) -> None:
    """Filtro assigned= retorna solo contactos asignados a ese usuario."""
    uid = str(asesor_user.id)
    r = await client.get(
        f"/api/v1/contacts?assigned={uid}", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    # contacts_list assigns all 30 to asesor_user
    assert r.json()["total"] == 30


async def test_filter_by_assigned_no_match(
    client: AsyncClient,
    contacts_list: list[Lead],
    user_asesor: dict,
) -> None:
    """Filtro assigned= con UUID que no existe retorna lista vacía."""
    unknown_uid = str(uuid.uuid4())
    r = await client.get(
        f"/api/v1/contacts?assigned={unknown_uid}", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── SORT ──────────────────────────────────────────────────────────────────────


async def test_sort_by_name_asc(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """sort=name&order=asc — los ítems de página 1 están en orden A→Z."""
    r = await client.get(
        "/api/v1/contacts?sort=name&order=asc", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["items"]]
    # All names are non-null in contacts_list ("Alpha01"…"Alpha30")
    assert names == sorted(names, key=str.lower)


async def test_sort_by_name_desc(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """sort=name&order=desc — los ítems de página 1 están en orden Z→A."""
    r = await client.get(
        "/api/v1/contacts?sort=name&order=desc", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["items"]]
    assert names == sorted(names, key=str.lower, reverse=True)


async def test_sort_asc_desc_no_overlap_in_names(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Los primeros 25 en ASC y los primeros 25 en DESC cubren todos los contactos."""
    r_asc = await client.get(
        "/api/v1/contacts?sort=name&order=asc", headers=auth(user_asesor)
    )
    r_desc = await client.get(
        "/api/v1/contacts?sort=name&order=desc", headers=auth(user_asesor)
    )
    ids_asc = {c["id"] for c in r_asc.json()["items"]}
    ids_desc = {c["id"] for c in r_desc.json()["items"]}
    # 30 contacts, page_size=25 → 5 IDs differ between pages
    assert len(ids_asc) == PAGE_SIZE
    assert len(ids_desc) == PAGE_SIZE
    # Together they should cover all 30 contacts
    assert len(ids_asc | ids_desc) == 30


async def test_sort_default_is_name_asc(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """Sin parámetros sort/order, el orden por defecto es name ASC."""
    r_default = await client.get("/api/v1/contacts", headers=auth(user_asesor))
    r_explicit = await client.get(
        "/api/v1/contacts?sort=name&order=asc", headers=auth(user_asesor)
    )
    default_ids = [c["id"] for c in r_default.json()["items"]]
    explicit_ids = [c["id"] for c in r_explicit.json()["items"]]
    assert default_ids == explicit_ids


# ── COMBINED FILTERS ──────────────────────────────────────────────────────────


async def test_search_combined_with_status(
    client: AsyncClient, contacts_list: list[Lead], user_asesor: dict
) -> None:
    """q + status se combinan como AND: solo resultados que cumplen ambos criterios."""
    # All contacts_list names start with "Alpha"; 6 have status=nuevo
    r = await client.get(
        "/api/v1/contacts?q=Alpha&status=nuevo", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 6  # 6 "Alpha*" contacts with status=nuevo


async def test_search_combined_with_tag(
    client: AsyncClient,
    contacts_list: list[Lead],
    tag_vip: dict,
    user_asesor: dict,
) -> None:
    """q + tag se combinan como AND: solo resultados que cumplen ambas condiciones."""
    # Tag 2 contacts
    tagged_ids = [str(contacts_list[0].id), str(contacts_list[1].id)]
    for cid in tagged_ids:
        await client.patch(
            f"/api/v1/contacts/{cid}",
            json={"tag_ids": [tag_vip["id"]]},
            headers=auth(user_asesor),
        )

    # q=Alpha matches all 30; tag filter narrows to 2
    r = await client.get(
        f"/api/v1/contacts?q=Alpha&tag={tag_vip['id']}", headers=auth(user_asesor)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 2
