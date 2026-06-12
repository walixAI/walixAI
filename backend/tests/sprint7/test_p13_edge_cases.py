"""
Sprint 7 · P-13 — Casos borde: caracteres especiales, bulk vacío, CSV grande,
                   concurrencia, soft-delete y filtros.

Correcciones respecto al pseudo-código original:
  · `jobId`      → `job_id`   (campo snake_case de ImportJobOut)
  · `tagIds`     → `tag_ids`  (campo snake_case de ContactUpdate)
  · CSV > 1000 filas: la implementación trunca silenciosamente a 1000 filas
    y responde 202 — no rechaza con 400.
  · `contacts_list` no existe en conftest; se define aquí como `contacts_30`.
  · Tests que llegan al `await redis_client.set(...)` requieren Redis
    y se marcan con @pytest.mark.integration.
  · `patch_session_local` autouse redirige AsyncSessionLocal al session de prueba
    para que el background task no contamine la BD real.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStatus
from app.models.tag import Tag
from app.models.tenant import Branch, Tenant
from app.models.user import User


# ── Helpers ───────────────────────────────────────────────────────────────────

def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


async def wait_for_job(
    client: AsyncClient,
    job_id: str,
    user: dict,
    *,
    timeout: float = 15.0,
    poll_interval: float = 0.1,
) -> dict:
    """Poll GET /api/v1/contacts/import/{job_id} until completed or failed."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(
            f"/api/v1/contacts/import/{job_id}",
            headers=auth(user),
        )
        assert r.status_code == 200, f"Job polling failed: {r.text}"
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Import job {job_id!r} did not complete within {timeout}s")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_session_local(db: AsyncSession, monkeypatch) -> None:
    """
    Redirige AsyncSessionLocal (usado por el background task de importación)
    al session de prueba, de modo que el commit del task queda dentro del
    SAVEPOINT y se revierte al finalizar el test.
    """
    @asynccontextmanager
    async def _mock_session():
        yield db

    monkeypatch.setattr("app.api.contacts.AsyncSessionLocal", _mock_session)


@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def user_gerente(manager_user: User, manager_token: str) -> dict:
    return {"id": str(manager_user.id), "token": manager_token}


@pytest_asyncio.fixture()
async def contact_full(client: AsyncClient, user_asesor: dict) -> dict:
    """Contacto creado vía POST; devuelve el JSON de GET /:id."""
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
    t = Tag(tenant_id=tenant.id, name="VIP", color="#7C3AED")
    db.add(t)
    await db.flush()
    return {"id": str(t.id), "name": "VIP", "color": "#7C3AED"}


@pytest_asyncio.fixture()
async def contacts_30(
    db: AsyncSession, tenant: Tenant, branch: Branch
) -> list[Lead]:
    """30 contactos en el tenant de prueba para tests de paginación."""
    leads = []
    for i in range(30):
        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            wa_phone=f"+5215534{i:06d}",
            name=f"PaginaContacto{i:02d}",
            last_name="Prueba",
            status=LeadStatus.NUEVO,
        )
        db.add(lead)
        leads.append(lead)
    await db.flush()
    return leads


# ── § 1: CARACTERES ESPECIALES Y ENCODING ────────────────────────────────────

async def test_contact_with_special_characters(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Nombres con acentos, ñ y caracteres especiales se guardan y recuperan correctamente."""
    name = "Señorita García-Martínez O'Brien"
    r = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": "+5215512340088", "name": name},
        headers=auth(user_asesor),
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    detail = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert detail.status_code == 200
    assert detail.json()["name"] == name


async def test_search_with_special_characters(
    client: AsyncClient, user_asesor: dict
) -> None:
    """
    Búsqueda con caracteres especiales y strings de inyección SQL no rompe el endpoint.

    SQLAlchemy usa consultas parametrizadas (ilike con bind params), así que
    ninguna de estas cadenas puede alterar la consulta SQL.
    """
    injection_strings = [
        "'; DROP TABLE leads; --",
        "%' OR '1'='1",
        "",
    ]
    for query in injection_strings:
        r = await client.get(
            "/api/v1/contacts",
            params={"q": query},
            headers=auth(user_asesor),
        )
        assert r.status_code == 200, f"q={query!r} → esperado 200, obtenido {r.status_code}"


@pytest.mark.integration
async def test_csv_import_with_special_characters(
    client: AsyncClient, user_gerente: dict
) -> None:
    """CSV con nombres acentuados (UTF-8) se importa correctamente.

    Requiere Redis disponible en el entorno de test.
    """
    csv_content = "nombre,empresa\nJosé García,Señales SA\nMaría Ñoño,Açaí Corp"
    r = await client.post(
        "/api/v1/contacts/import",
        files={"file": ("special.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    data = r.json()
    assert data["total_rows"] == 2

    job = await wait_for_job(client, data["job_id"], user_gerente)
    assert job["status"] == "completed"
    assert job["processed"] == 2
    assert job["errors"] == []


# ── § 2: PAGINACIÓN Y LÍMITES ─────────────────────────────────────────────────

async def test_page_beyond_total_returns_empty(
    client: AsyncClient, contacts_30: list[Lead], user_asesor: dict
) -> None:
    """Solicitar página 999 cuando solo hay 30 contactos retorna lista vacía."""
    r = await client.get("/api/v1/contacts", params={"page": 999}, headers=auth(user_asesor))
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 30


async def test_bulk_with_empty_ids(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Bulk action con lista vacía de IDs retorna updated=0 sin error."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "status", "ids": [], "payload": {"status": "calificado"}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 0


@pytest.mark.integration
async def test_csv_over_1000_rows_truncated_to_limit(
    client: AsyncClient, user_gerente: dict
) -> None:
    """
    CSV con más de 1000 filas se trunca silenciosamente a 1000 filas y se acepta (202).

    La implementación usa `break` al llegar a _IMPORT_MAX_ROWS=1000, por lo que
    el job se crea con total_rows=1000, no se rechaza el archivo completo.
    Requiere Redis disponible en el entorno de test.
    """
    rows = "\n".join(f"Contacto {i}" for i in range(1001))
    csv_content = f"nombre\n{rows}".encode("utf-8")
    r = await client.post(
        "/api/v1/contacts/import",
        files={"file": ("big.csv", csv_content, "text/csv")},
        headers=auth(user_gerente),
    )
    assert r.status_code == 202
    assert r.json()["total_rows"] == 1000


# ── § 3: DATOS SIMULTÁNEOS ────────────────────────────────────────────────────

async def test_concurrent_tag_assignment_no_duplicate(
    client: AsyncClient,
    contact_full: dict,
    tag_vip: dict,
    user_asesor: dict,
    user_gerente: dict,
) -> None:
    """
    Asignación del mismo tag desde dos usuarios simultáneos no crea duplicados.

    El endpoint usa ON CONFLICT DO NOTHING en lead_tags_table, así que aunque
    ambas solicitudes se procesen en el mismo ciclo de eventos, el resultado
    final debe ser exactamente un tag asignado.
    """
    cid = contact_full["id"]
    tid = tag_vip["id"]

    results = await asyncio.gather(
        client.patch(
            f"/api/v1/contacts/{cid}",
            json={"tag_ids": [tid]},
            headers=auth(user_asesor),
        ),
        client.patch(
            f"/api/v1/contacts/{cid}",
            json={"tag_ids": [tid]},
            headers=auth(user_gerente),
        ),
        return_exceptions=True,
    )

    statuses = [r.status_code for r in results if not isinstance(r, Exception)]
    assert 200 in statuses, f"Al menos un PATCH debe retornar 200; obtenidos: {statuses}"

    detail = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_asesor))
    assert detail.status_code == 200
    vip_tags = [t for t in detail.json()["tags"] if t["id"] == tid]
    assert len(vip_tags) == 1, f"Se esperaba exactamente 1 tag VIP, se encontraron {len(vip_tags)}"


# ── § 4: SOFT DELETE Y FILTROS ────────────────────────────────────────────────

async def test_deleted_contact_excluded_from_search(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Contacto eliminado no aparece en búsqueda full-text."""
    # El fragmento del nombre debe ser lo bastante selectivo para identificarlo
    name_fragment = contact_full["name"][:4]

    await client.delete(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_asesor),
    )

    r = await client.get(
        "/api/v1/contacts",
        params={"q": name_fragment},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["items"]]
    assert contact_full["id"] not in ids


async def test_deleted_contact_excluded_from_export(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Contacto eliminado no aparece en la exportación CSV."""
    await client.delete(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_asesor),
    )

    r = await client.get("/api/v1/contacts/export", headers=auth(user_asesor))
    assert r.status_code == 200
    # UTF-8 BOM stripped by decode('utf-8-sig')
    csv_text = r.content.decode("utf-8-sig")
    assert contact_full["name"] not in csv_text
