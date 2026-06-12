"""
Sprint 7 · P-04 — Bulk actions: reassign, status, tag, delete + authorization
Tests for POST /api/v1/contacts/bulk

Payload fields (snake_case — no camelCase aliases):
  reassign  → payload.user_id  (UUID string)
  status    → payload.status   (lowercase LeadStatus: nuevo | en_calificacion |
                                 calificado | escalado | perdido)
  tag       → payload.tag_id   (UUID string)
  delete    → payload {}       (no payload required)

Authorization:
  - delete  requires _MANAGER_ROLES (OWNER, GERENTE, IT)
  - all other actions are open to any authenticated user in the tenant

Cross-tenant: if ANY id in the batch does not belong to current_user.tenant_id,
the ENTIRE request is rejected with 403 (no partial processing).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.lead import Lead, LeadStatus
from app.models.tag import Tag
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

# ── Auth helper ───────────────────────────────────────────────────────────────


def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['token']}"}


# ── Local fixtures ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def user_asesor(asesor_user: User, asesor_token: str) -> dict:
    return {"id": str(asesor_user.id), "token": asesor_token}


@pytest_asyncio.fixture()
async def user_gerente(manager_user: User, manager_token: str) -> dict:
    return {"id": str(manager_user.id), "token": manager_token}


@pytest_asyncio.fixture()
async def user_asesor_2(
    db: AsyncSession, tenant: Tenant, branch: Branch
) -> dict:
    """A second asesor in the same tenant — target for reassignment tests."""
    u = User(
        tenant_id=tenant.id,
        branch_id=branch.id,
        email=f"asesor2-{uuid.uuid4().hex[:6]}@walix.test",
        name="Asesor Dos",
        hashed_password=hash_password("test1234"),
        role=UserRole.ASESOR,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return {"id": str(u.id), "token": create_access_token({"sub": str(u.id)})}


@pytest_asyncio.fixture()
async def user_other_tenant(db: AsyncSession) -> dict:
    """
    A user who belongs to a completely different tenant.
    Used to verify cross-tenant isolation.
    """
    other_tenant = Tenant(
        name="Tenant Externo SA",
        email=f"externo-{uuid.uuid4().hex[:6]}@test.com",
        plan=TenantPlan.STARTER,
        is_active=True,
    )
    db.add(other_tenant)
    await db.flush()

    other_company = Company(tenant_id=other_tenant.id, name="Externo Corp")
    db.add(other_company)
    await db.flush()

    other_branch = Branch(
        company_id=other_company.id,
        tenant_id=other_tenant.id,
        name="Sucursal Externa",
        is_active=True,
    )
    db.add(other_branch)
    await db.flush()

    other_user = User(
        tenant_id=other_tenant.id,
        branch_id=other_branch.id,
        email=f"externo-user-{uuid.uuid4().hex[:6]}@test.com",
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
        "tenant_id": str(other_tenant.id),
        "branch_id": str(other_branch.id),
    }


@pytest_asyncio.fixture()
async def five_contacts(
    db: AsyncSession,
    tenant: Tenant,
    branch: Branch,
    asesor_user: User,
) -> list[dict]:
    """5 contacts in the test tenant, all assigned to asesor_user."""
    leads = []
    for i in range(5):
        lead = Lead(
            branch_id=branch.id,
            tenant_id=tenant.id,
            wa_phone=f"+5215534560{i:02d}",
            name=f"BulkTest{i:02d}",
            last_name="Prueba",
            status=LeadStatus.NUEVO,
            assigned_to=asesor_user.id,
        )
        db.add(lead)
        leads.append(lead)
    await db.flush()
    return [{"id": str(l.id)} for l in leads]


@pytest_asyncio.fixture()
async def tag_vip(db: AsyncSession, tenant: Tenant) -> dict:
    t = Tag(tenant_id=tenant.id, name="VIP", color="#7C3AED")
    db.add(t)
    await db.flush()
    return {"id": str(t.id), "name": "VIP", "color": "#7C3AED"}


# ── REASSIGN ──────────────────────────────────────────────────────────────────


async def test_bulk_reassign(
    client: AsyncClient,
    five_contacts: list[dict],
    user_gerente: dict,
    user_asesor_2: dict,
) -> None:
    """Reasignar 5 contactos a otro asesor — updated=5, assignedUser cambia."""
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "reassign", "ids": ids, "payload": {"user_id": user_asesor_2["id"]}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 5

    # Verify each contact shows the new assignee
    for cid in ids:
        detail = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_gerente))
        assert detail.status_code == 200
        assert detail.json()["assigned_user"]["id"] == user_asesor_2["id"]


async def test_bulk_reassign_missing_user_id(
    client: AsyncClient, five_contacts: list[dict], user_gerente: dict
) -> None:
    """payload sin user_id en reassign debe fallar con 400."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "reassign", "ids": [five_contacts[0]["id"]], "payload": {}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 400


async def test_bulk_reassign_available_to_asesor(
    client: AsyncClient,
    five_contacts: list[dict],
    user_asesor: dict,
    user_asesor_2: dict,
) -> None:
    """Un asesor SÍ puede hacer bulk reassign (solo delete requiere gerente+)."""
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "reassign", "ids": ids, "payload": {"user_id": user_asesor_2["id"]}},
        headers=auth(user_asesor),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 5


# ── STATUS ────────────────────────────────────────────────────────────────────


async def test_bulk_change_status(
    client: AsyncClient, five_contacts: list[dict], user_gerente: dict
) -> None:
    """Cambiar status de 5 contactos a 'calificado'."""
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "status", "ids": ids, "payload": {"status": "calificado"}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 5

    # ContactRow doesn't expose status; verify via status filter
    r_list = await client.get(
        "/api/v1/contacts?status=calificado", headers=auth(user_gerente)
    )
    assert r_list.json()["total"] == 5


async def test_bulk_invalid_status_returns_400(
    client: AsyncClient, five_contacts: list[dict], user_gerente: dict
) -> None:
    """Valor de status fuera del enum retorna 400."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={
            "action": "status",
            "ids": [five_contacts[0]["id"]],
            "payload": {"status": "estado_invalido"},
        },
        headers=auth(user_gerente),
    )
    assert r.status_code == 400


async def test_bulk_status_missing_payload_field(
    client: AsyncClient, five_contacts: list[dict], user_gerente: dict
) -> None:
    """payload sin 'status' en action=status retorna 400."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "status", "ids": [five_contacts[0]["id"]], "payload": {}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 400


# ── TAG ───────────────────────────────────────────────────────────────────────


async def test_bulk_tag(
    client: AsyncClient,
    five_contacts: list[dict],
    tag_vip: dict,
    user_gerente: dict,
) -> None:
    """Etiquetar 5 contactos — cada uno debe tener el tag después."""
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "tag", "ids": ids, "payload": {"tag_id": tag_vip["id"]}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 5

    for cid in ids:
        detail = await client.get(f"/api/v1/contacts/{cid}", headers=auth(user_gerente))
        assert detail.status_code == 200
        tag_ids = [t["id"] for t in detail.json()["tags"]]
        assert tag_vip["id"] in tag_ids


async def test_bulk_tag_no_duplicate(
    client: AsyncClient,
    five_contacts: list[dict],
    tag_vip: dict,
    user_gerente: dict,
) -> None:
    """Etiquetar dos veces el mismo tag no genera duplicados (ON CONFLICT DO NOTHING)."""
    payload = {"action": "tag", "ids": [five_contacts[0]["id"]], "payload": {"tag_id": tag_vip["id"]}}
    await client.post("/api/v1/contacts/bulk", json=payload, headers=auth(user_gerente))
    await client.post("/api/v1/contacts/bulk", json=payload, headers=auth(user_gerente))

    detail = await client.get(
        f"/api/v1/contacts/{five_contacts[0]['id']}", headers=auth(user_gerente)
    )
    vip_tags = [t for t in detail.json()["tags"] if t["id"] == tag_vip["id"]]
    assert len(vip_tags) == 1


async def test_bulk_tag_missing_tag_id(
    client: AsyncClient, five_contacts: list[dict], user_gerente: dict
) -> None:
    """payload sin tag_id en action=tag retorna 400."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "tag", "ids": [five_contacts[0]["id"]], "payload": {}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 400


# ── DELETE ────────────────────────────────────────────────────────────────────


async def test_bulk_delete_soft(
    client: AsyncClient,
    five_contacts: list[dict],
    user_gerente: dict,
    db: AsyncSession,
) -> None:
    """Bulk delete hace soft delete — los registros tienen deleted_at y no aparecen en lista."""
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "delete", "ids": ids, "payload": {}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 5

    # Verify disappear from list endpoint
    r_list = await client.get("/api/v1/contacts", headers=auth(user_gerente))
    list_ids = {c["id"] for c in r_list.json()["items"]}
    for cid in ids:
        assert cid not in list_ids

    # Verify soft-deleted rows still exist in DB with deleted_at set
    for cid in ids:
        row = (
            await db.execute(
                text("SELECT deleted_at FROM leads WHERE id = :id"),
                {"id": uuid.UUID(cid)},
            )
        ).fetchone()
        assert row is not None
        assert row[0] is not None, f"deleted_at should be set for {cid}"


async def test_bulk_delete_requires_gerente(
    client: AsyncClient,
    five_contacts: list[dict],
    user_asesor: dict,
) -> None:
    """Un asesor NO puede hacer bulk delete — debe recibir 403."""
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "delete", "ids": ids, "payload": {}},
        headers=auth(user_asesor),
    )
    assert r.status_code == 403


async def test_bulk_delete_leaves_contacts_intact_after_403(
    client: AsyncClient,
    five_contacts: list[dict],
    user_asesor: dict,
    user_gerente: dict,
) -> None:
    """Cuando un asesor intenta bulk delete y recibe 403, los contactos no se modifican."""
    ids = [c["id"] for c in five_contacts]
    await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "delete", "ids": ids, "payload": {}},
        headers=auth(user_asesor),
    )
    # Contacts must still be accessible
    r_list = await client.get("/api/v1/contacts", headers=auth(user_gerente))
    assert r_list.json()["total"] == 5


# ── CROSS-TENANT ISOLATION ───────────────────────────────────────────────────


async def test_bulk_rejects_ids_from_other_tenant(
    client: AsyncClient,
    five_contacts: list[dict],
    user_gerente: dict,
    user_other_tenant: dict,
    db: AsyncSession,
) -> None:
    """
    Batch que incluye un ID de otro tenant se rechaza COMPLETO con 403.
    No hay procesamiento parcial — o todos son válidos o falla.
    """
    # Create a contact in the other tenant directly via DB
    other_tenant_id = uuid.UUID(user_other_tenant["tenant_id"])
    other_branch_id = uuid.UUID(user_other_tenant["branch_id"])
    external_lead = Lead(
        branch_id=other_branch_id,
        tenant_id=other_tenant_id,
        wa_phone="+5215599990001",
        name="Externo",
        status=LeadStatus.NUEVO,
    )
    db.add(external_lead)
    await db.flush()

    ids = [c["id"] for c in five_contacts] + [str(external_lead.id)]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "status", "ids": ids, "payload": {"status": "calificado"}},
        headers=auth(user_gerente),
    )
    # The entire batch is rejected because one ID doesn't belong to current user's tenant
    assert r.status_code == 403

    # Own contacts remain unchanged (still "nuevo")
    r_calificado = await client.get(
        "/api/v1/contacts?status=calificado", headers=auth(user_gerente)
    )
    assert r_calificado.json()["total"] == 0


async def test_bulk_only_sees_own_tenant(
    client: AsyncClient,
    five_contacts: list[dict],
    user_gerente: dict,
    user_other_tenant: dict,
    db: AsyncSession,
) -> None:
    """
    Pasar IDs válidos del propio tenant (sin IDs externos) funciona correctamente
    incluso si existen contactos en otros tenants con IDs distintos.
    """
    # Create a contact in the other tenant (different ID)
    other_tenant_id = uuid.UUID(user_other_tenant["tenant_id"])
    other_branch_id = uuid.UUID(user_other_tenant["branch_id"])
    other_lead = Lead(
        branch_id=other_branch_id,
        tenant_id=other_tenant_id,
        wa_phone="+5215599990002",
        name="Externo2",
        status=LeadStatus.NUEVO,
    )
    db.add(other_lead)
    await db.flush()

    # Bulk on own tenant's contacts only — should succeed
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "status", "ids": ids, "payload": {"status": "calificado"}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 5


# ── EDGE CASES ────────────────────────────────────────────────────────────────


async def test_bulk_empty_ids_returns_zero(
    client: AsyncClient, user_gerente: dict
) -> None:
    """Lista de IDs vacía retorna updated=0 sin errores."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "status", "ids": [], "payload": {"status": "calificado"}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 0


async def test_bulk_invalid_action_returns_422(
    client: AsyncClient, user_gerente: dict
) -> None:
    """action con valor no permitido retorna 422 (Pydantic Literal validation)."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "publish", "ids": [], "payload": {}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 422


async def test_bulk_unauthenticated_returns_401(client: AsyncClient) -> None:
    """Sin token de autenticación retorna 401."""
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "delete", "ids": [], "payload": {}},
    )
    assert r.status_code == 401


async def test_bulk_deleted_ids_rejected(
    client: AsyncClient,
    five_contacts: list[dict],
    user_gerente: dict,
) -> None:
    """IDs que ya fueron soft-deleted no son encontrados — el batch se rechaza con 403."""
    cid = five_contacts[0]["id"]

    # Soft-delete one contact first
    await client.delete(f"/api/v1/contacts/{cid}", headers=auth(user_gerente))

    # Now try to bulk-act on all 5 including the deleted one
    ids = [c["id"] for c in five_contacts]
    r = await client.post(
        "/api/v1/contacts/bulk",
        json={"action": "status", "ids": ids, "payload": {"status": "calificado"}},
        headers=auth(user_gerente),
    )
    assert r.status_code == 403
