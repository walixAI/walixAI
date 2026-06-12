"""
Sprint 7 · P-12 — Seguridad: aislamiento multi-tenant, autorización por rol,
                   endpoints sin JWT.

CRÍTICO: estos tests deben pasar al 100% antes de producción.

Categorías:
  § 1 · Aislamiento multi-tenant — un usuario de un tenant diferente NO puede
        leer, modificar, eliminar ni registrar actividades en contactos ajenos;
        la lista y los tags tampoco exponen datos del otro tenant.
  § 2 · Sin autenticación — todos los endpoints retornan 401 sin JWT.
  § 3 · Autorización por rol — importar CSV y bulk-delete requieren gerente+.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

# ── Constants ─────────────────────────────────────────────────────────────────

# UUID sintácticamente válido que no existe en la BD — necesario para que
# FastAPI no devuelva 422 (validación de path param) antes de comprobar auth.
_FAKE_UUID = "00000000-0000-0000-0000-000000000001"


# ── Helpers ───────────────────────────────────────────────────────────────────

def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    """Asesor del tenant principal como {id, token}."""
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def contact_full(client: AsyncClient, user_asesor: dict) -> dict:
    """Contacto creado vía POST en el tenant principal; devuelve el JSON de GET /:id."""
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
async def user_other_tenant(db: AsyncSession) -> dict:
    """Usuario OWNER de un tenant completamente diferente al principal, con {id, token}."""
    t = Tenant(
        name=f"Tenant Externo {uuid.uuid4().hex[:6]}",
        email=f"ext-{uuid.uuid4().hex[:6]}@walix.test",
        plan=TenantPlan.STARTER,
        is_active=True,
    )
    db.add(t)
    await db.flush()

    company = Company(tenant_id=t.id, name="Empresa Externa S.A.")
    db.add(company)
    await db.flush()

    branch = Branch(
        company_id=company.id,
        tenant_id=t.id,
        name="Sucursal Externa",
        is_active=True,
    )
    db.add(branch)
    await db.flush()

    u = User(
        tenant_id=t.id,
        branch_id=branch.id,
        email=f"ext-{uuid.uuid4().hex[:8]}@walix.test",
        name="Usuario Externo",
        hashed_password=hash_password("test1234"),
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(u)
    await db.flush()

    return {"id": str(u.id), "token": create_access_token({"sub": str(u.id)})}


# ── § 1: AISLAMIENTO MULTI-TENANT ────────────────────────────────────────────

async def test_cannot_read_other_tenant_contact(
    client: AsyncClient, contact_full: dict, user_other_tenant: dict
) -> None:
    """Usuario de otro tenant NO puede leer un contacto que no es suyo."""
    r = await client.get(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_other_tenant),
    )
    assert r.status_code in (403, 404)


async def test_cannot_update_other_tenant_contact(
    client: AsyncClient, contact_full: dict, user_asesor: dict, user_other_tenant: dict
) -> None:
    """Usuario de otro tenant NO puede actualizar un contacto ajeno."""
    r = await client.patch(
        f"/api/v1/contacts/{contact_full['id']}",
        json={"name": "Hack"},
        headers=auth(user_other_tenant),
    )
    assert r.status_code in (403, 404)

    # Verificar que el nombre no cambió en el tenant propietario
    r2 = await client.get(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_asesor),
    )
    assert r2.status_code == 200
    assert r2.json()["name"] != "Hack"


async def test_cannot_delete_other_tenant_contact(
    client: AsyncClient, contact_full: dict, user_other_tenant: dict
) -> None:
    """Usuario de otro tenant NO puede eliminar un contacto ajeno."""
    r = await client.delete(
        f"/api/v1/contacts/{contact_full['id']}",
        headers=auth(user_other_tenant),
    )
    assert r.status_code in (403, 404)


async def test_list_only_returns_own_tenant(
    client: AsyncClient, user_asesor: dict, user_other_tenant: dict
) -> None:
    """GET /contacts solo retorna contactos del propio tenant."""
    ts = uuid.uuid4().hex[:8]

    r1 = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": f"+52155{ts}", "name": "Mío"},
        headers=auth(user_asesor),
    )
    assert r1.status_code == 201, r1.text

    r2 = await client.post(
        "/api/v1/contacts",
        json={"wa_phone": f"+52156{ts}", "name": "Ajeno"},
        headers=auth(user_other_tenant),
    )
    assert r2.status_code == 201, r2.text

    r = await client.get("/api/v1/contacts", headers=auth(user_asesor))
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["items"]]
    assert "Mío" in names
    assert "Ajeno" not in names


async def test_activities_tenant_isolation(
    client: AsyncClient, contact_full: dict, user_other_tenant: dict
) -> None:
    """No se puede crear una actividad en un contacto de otro tenant."""
    r = await client.post(
        f"/api/v1/contacts/{contact_full['id']}/activities",
        json={"activity_type": "note", "body": "espionaje"},
        headers=auth(user_other_tenant),
    )
    assert r.status_code in (403, 404)


async def test_tags_tenant_isolation(
    client: AsyncClient, user_asesor: dict, user_other_tenant: dict
) -> None:
    """GET /tags solo retorna tags del propio tenant."""
    r1 = await client.post(
        "/api/v1/tags", json={"name": "MiTag"}, headers=auth(user_asesor)
    )
    assert r1.status_code == 201, r1.text

    r2 = await client.post(
        "/api/v1/tags", json={"name": "OtroTag"}, headers=auth(user_other_tenant)
    )
    assert r2.status_code == 201, r2.text

    r = await client.get("/api/v1/tags", headers=auth(user_asesor))
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "MiTag" in names
    assert "OtroTag" not in names


# ── § 2: SIN AUTENTICACIÓN ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "method,url,body",
    [
        ("GET",    "/api/v1/contacts",                                          None),
        ("POST",   "/api/v1/contacts",                                          {"wa_phone": "+5215512345000"}),
        ("GET",    f"/api/v1/contacts/{_FAKE_UUID}",                            None),
        ("PATCH",  f"/api/v1/contacts/{_FAKE_UUID}",                            {"name": "X"}),
        ("DELETE", f"/api/v1/contacts/{_FAKE_UUID}",                            None),
        ("POST",   "/api/v1/contacts/bulk",                                     {"action": "delete", "ids": [_FAKE_UUID], "payload": {}}),
        ("GET",    f"/api/v1/contacts/{_FAKE_UUID}/activities",                 None),
        ("POST",   f"/api/v1/contacts/{_FAKE_UUID}/activities",                 {"activity_type": "note", "body": "x"}),
        ("GET",    "/api/v1/tags",                                              None),
        ("GET",    "/api/v1/contacts/export",                                   None),
    ],
)
async def test_all_endpoints_require_auth(
    client: AsyncClient, method: str, url: str, body: dict | None
) -> None:
    """Todos los endpoints del módulo de Contactos retornan 401 sin JWT."""
    if method == "GET":
        r = await client.get(url)
    elif method == "POST":
        r = await client.post(url, json=body)
    elif method == "PATCH":
        r = await client.patch(url, json=body)
    else:  # DELETE
        r = await client.delete(url)
    assert r.status_code == 401, (
        f"{method} {url} → esperado 401, obtenido {r.status_code}: {r.text}"
    )


# ── § 3: AUTORIZACIÓN POR ROL ─────────────────────────────────────────────────

async def test_import_requires_gerente_or_above(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Asesor NO puede importar CSV — se requiere gerente o superior (403)."""
    r = await client.post(
        "/api/v1/contacts/import",
        files={"file": ("t.csv", b"nombre\nTest", "text/csv")},
        headers=auth(user_asesor),
    )
    assert r.status_code == 403


async def test_bulk_delete_requires_gerente(
    client: AsyncClient, contact_full: dict, user_asesor: dict
) -> None:
    """Asesor NO puede hacer bulk delete — se requiere gerente o superior (403)."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={
            "action": "delete",
            "ids": [contact_full["id"]],
            "payload": {},
        },
        headers=auth(user_asesor),
    )
    assert r.status_code == 403
