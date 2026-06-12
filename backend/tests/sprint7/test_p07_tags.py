"""
Sprint 7 · P-07 — Tags: uniqueness, auto-colors, tenant isolation
Tests for GET / POST /api/v1/tags

Response: TagRow { id: UUID, name: str, color: str | None }

Auto-color: round-robin through _PRESET_COLORS (6 colors) based on count of
existing tags for the tenant. Explicit color in the request overrides it.

Duplicate name in same tenant → 409 (IntegrityError → HTTPException).
Same name in different tenants → 201 for both (tenant_id in unique index).

GET /tags returns only own-tenant tags, ordered alphabetically by name.
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

# ── Auto-color presets — must mirror app/api/tags.py ─────────────────────────
_PRESET_COLORS = ["#7C3AED", "#0891B2", "#059669", "#D97706", "#DC2626", "#DB2777"]

# ── Helpers ───────────────────────────────────────────────────────────────────


def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def user_other_tenant(db: AsyncSession) -> dict:
    """User in a completely separate tenant — for cross-tenant isolation tests."""
    other_tenant = Tenant(
        name=f"Tenant Externo {uuid.uuid4().hex[:6]}",
        email=f"ext-{uuid.uuid4().hex[:6]}@test.com",
        plan=TenantPlan.STARTER,
        is_active=True,
    )
    db.add(other_tenant)
    await db.flush()

    other_company = Company(tenant_id=other_tenant.id, name="Ext Corp")
    db.add(other_company)
    await db.flush()

    other_branch = Branch(
        company_id=other_company.id,
        tenant_id=other_tenant.id,
        name="Sucursal Ext",
        is_active=True,
    )
    db.add(other_branch)
    await db.flush()

    other_user = User(
        tenant_id=other_tenant.id,
        branch_id=other_branch.id,
        email=f"ext-user-{uuid.uuid4().hex[:6]}@test.com",
        name="Usuario Externo",
        hashed_password=hash_password("test1234"),
        role=UserRole.ASESOR,
        is_active=True,
    )
    db.add(other_user)
    await db.flush()

    return {
        "id": str(other_user.id),
        "token": create_access_token({"sub": str(other_user.id)}),
    }


# ── CREATE — POST /api/v1/tags ────────────────────────────────────────────────


async def test_create_tag(client: AsyncClient, user_asesor: dict) -> None:
    """Crear tag nuevo retorna el tag con color automático válido."""
    r = await client.post("/api/v1/tags", json={"name": "Premium"}, headers=auth(user_asesor))
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Premium"
    assert data["color"] is not None
    assert data["color"].startswith("#")
    assert len(data["color"]) == 7


async def test_create_tag_with_custom_color(client: AsyncClient, user_asesor: dict) -> None:
    """Color explícito en el request se preserva tal cual."""
    r = await client.post(
        "/api/v1/tags", json={"name": "VIP2", "color": "#FF5733"}, headers=auth(user_asesor)
    )
    assert r.status_code == 201
    assert r.json()["color"] == "#FF5733"


async def test_create_tag_returns_id(client: AsyncClient, user_asesor: dict) -> None:
    """La respuesta incluye un id UUID válido."""
    r = await client.post("/api/v1/tags", json={"name": "ConID"}, headers=auth(user_asesor))
    assert r.status_code == 201
    tag_id = r.json()["id"]
    assert uuid.UUID(tag_id)  # raises if not a valid UUID


async def test_create_duplicate_tag_same_tenant_fails(
    client: AsyncClient, user_asesor: dict
) -> None:
    """El mismo nombre de tag en el mismo tenant devuelve 409."""
    await client.post("/api/v1/tags", json={"name": "Único"}, headers=auth(user_asesor))
    r = await client.post("/api/v1/tags", json={"name": "Único"}, headers=auth(user_asesor))
    assert r.status_code == 409


async def test_create_duplicate_case_sensitive(
    client: AsyncClient, user_asesor: dict
) -> None:
    """'VIP' y 'vip' son nombres distintos — PostgreSQL collation es case-sensitive."""
    r1 = await client.post("/api/v1/tags", json={"name": "VIP"}, headers=auth(user_asesor))
    r2 = await client.post("/api/v1/tags", json={"name": "vip"}, headers=auth(user_asesor))
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


async def test_create_tag_name_stripped(client: AsyncClient, user_asesor: dict) -> None:
    """Espacios al inicio y al final del nombre se eliminan."""
    r = await client.post(
        "/api/v1/tags", json={"name": "  ConEspacios  "}, headers=auth(user_asesor)
    )
    assert r.status_code == 201
    assert r.json()["name"] == "ConEspacios"


async def test_create_same_tag_name_different_tenant_ok(
    client: AsyncClient, user_asesor: dict, user_other_tenant: dict
) -> None:
    """El mismo nombre puede existir en tenants distintos — no se cruzan."""
    r1 = await client.post(
        "/api/v1/tags", json={"name": "Compartido"}, headers=auth(user_asesor)
    )
    r2 = await client.post(
        "/api/v1/tags", json={"name": "Compartido"}, headers=auth(user_other_tenant)
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


async def test_create_tag_no_auth(client: AsyncClient) -> None:
    """POST sin token retorna 401."""
    r = await client.post("/api/v1/tags", json={"name": "Anon"})
    assert r.status_code == 401


# ── AUTO-COLOR ROUND-ROBIN ────────────────────────────────────────────────────


async def test_auto_color_first_tag_uses_first_preset(
    client: AsyncClient, user_asesor: dict
) -> None:
    """El primer tag sin color recibe el primer color del preset (#7C3AED)."""
    r = await client.post("/api/v1/tags", json={"name": "Primero"}, headers=auth(user_asesor))
    assert r.json()["color"] == _PRESET_COLORS[0]


async def test_auto_color_cycles_through_all_presets(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Los colores auto-asignados ciclan a través de los 6 presets en orden."""
    n = len(_PRESET_COLORS)
    colors = []
    for i in range(n):
        r = await client.post(
            "/api/v1/tags", json={"name": f"AutoColor{i}"}, headers=auth(user_asesor)
        )
        assert r.status_code == 201
        colors.append(r.json()["color"])
    assert colors == _PRESET_COLORS


async def test_auto_color_wraps_after_sixth(
    client: AsyncClient, user_asesor: dict
) -> None:
    """El séptimo tag (sin color) vuelve al primer preset — mod 6."""
    for i in range(len(_PRESET_COLORS)):
        await client.post(
            "/api/v1/tags", json={"name": f"Wrap{i}"}, headers=auth(user_asesor)
        )
    r = await client.post("/api/v1/tags", json={"name": "Séptimo"}, headers=auth(user_asesor))
    assert r.json()["color"] == _PRESET_COLORS[0]


async def test_explicit_color_does_not_advance_counter(
    client: AsyncClient, user_asesor: dict
) -> None:
    """
    Un tag con color explícito se cuenta igual para el round-robin.
    Si se crea con color explícito, el siguiente auto-color avanza en la secuencia.
    """
    # First tag: explicit color — counts as 1 existing
    await client.post(
        "/api/v1/tags", json={"name": "Explicit", "color": "#AABBCC"}, headers=auth(user_asesor)
    )
    # Second tag: no color — count=1 → index 1 → PRESET_COLORS[1]
    r = await client.post("/api/v1/tags", json={"name": "Auto"}, headers=auth(user_asesor))
    assert r.json()["color"] == _PRESET_COLORS[1]


# ── GET — /api/v1/tags ────────────────────────────────────────────────────────


async def test_get_tags_empty(client: AsyncClient, user_asesor: dict) -> None:
    """Sin tags en el tenant, retorna lista vacía."""
    r = await client.get("/api/v1/tags", headers=auth(user_asesor))
    assert r.status_code == 200
    assert r.json() == []


async def test_get_tags_returns_created(client: AsyncClient, user_asesor: dict) -> None:
    """GET retorna los tags recién creados."""
    await client.post("/api/v1/tags", json={"name": "TagA"}, headers=auth(user_asesor))
    await client.post("/api/v1/tags", json={"name": "TagB"}, headers=auth(user_asesor))

    r = await client.get("/api/v1/tags", headers=auth(user_asesor))
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "TagA" in names
    assert "TagB" in names


async def test_get_tags_ordered_alphabetically(
    client: AsyncClient, user_asesor: dict
) -> None:
    """Los tags se retornan en orden alfabético por nombre."""
    for name in ("Zapato", "Alfa", "Mango"):
        await client.post("/api/v1/tags", json={"name": name}, headers=auth(user_asesor))

    r = await client.get("/api/v1/tags", headers=auth(user_asesor))
    names = [t["name"] for t in r.json()]
    assert names == sorted(names)


async def test_get_tags_only_own_tenant(
    client: AsyncClient, user_asesor: dict, user_other_tenant: dict
) -> None:
    """GET /tags filtra por tenant — no se mezclan etiquetas de otros tenants."""
    await client.post("/api/v1/tags", json={"name": "Tag Propio"}, headers=auth(user_asesor))
    await client.post(
        "/api/v1/tags", json={"name": "Tag Ajeno"}, headers=auth(user_other_tenant)
    )

    r = await client.get("/api/v1/tags", headers=auth(user_asesor))
    names = [t["name"] for t in r.json()]
    assert "Tag Propio" in names
    assert "Tag Ajeno" not in names


async def test_get_tags_other_tenant_sees_own_only(
    client: AsyncClient, user_asesor: dict, user_other_tenant: dict
) -> None:
    """El tenant externo ve su tag, no el del tenant principal."""
    await client.post("/api/v1/tags", json={"name": "Tag Propio"}, headers=auth(user_asesor))
    await client.post(
        "/api/v1/tags", json={"name": "Tag Ajeno"}, headers=auth(user_other_tenant)
    )

    r_other = await client.get("/api/v1/tags", headers=auth(user_other_tenant))
    names_other = [t["name"] for t in r_other.json()]
    assert "Tag Ajeno" in names_other
    assert "Tag Propio" not in names_other


async def test_get_tags_no_auth(client: AsyncClient) -> None:
    """GET sin token retorna 401."""
    r = await client.get("/api/v1/tags")
    assert r.status_code == 401
