"""
Regresión — Nomenclatura vertical por tenant (Sprint 8B: Industry Templates).

Código auditado: app/models/tenant.py (columnas entity_name/entity_plural/
deal_name/deal_plural/contact_statuses_config), app/api/auth.py (GET /api/auth/me
expone estos campos vía MeResponse.tenant — TenantOut, auth.py:207-215).

Un tenant con labels custom no debe romper ningún endpoint existente: se monta
un tenant completo con labels no-default y se ejercitan los endpoints
principales (auth/me, contactos, deals, paneles de dashboard, dashboard
role-based) end-to-end.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def custom_labels_ctx(db: AsyncSession) -> dict:
    """Tenant completo con nomenclatura no-default (vertical inmobiliaria, por ejemplo)."""
    t = Tenant(
        name=f"Inmobiliaria Test {uuid.uuid4().hex[:6]}",
        email=f"inmo-{uuid.uuid4().hex[:6]}@walix.test",
        plan=TenantPlan.STARTER,
        is_active=True,
        industry_key="inmobiliaria",
        industry_label="Bienes Raíces",
        entity_name="Prospecto",
        entity_plural="Prospectos",
        deal_name="Propiedad",
        deal_plural="Propiedades",
        contact_statuses_config=[
            {"key": "nuevo", "label": "Nuevo contacto"},
            {"key": "visitando", "label": "Visitando propiedades"},
        ],
    )
    db.add(t)
    await db.flush()

    company = Company(tenant_id=t.id, name="Inmobiliaria Test S.A.")
    db.add(company)
    await db.flush()

    branch = Branch(company_id=company.id, tenant_id=t.id, name="Sucursal Centro", is_active=True)
    db.add(branch)
    await db.flush()

    owner = User(
        tenant_id=t.id, branch_id=branch.id,
        email=f"owner-{uuid.uuid4().hex[:6]}@walix.test", name="Owner Inmobiliaria",
        hashed_password=hash_password("test1234"), role=UserRole.OWNER, is_active=True,
    )
    db.add(owner)
    await db.flush()

    return {
        "tenant": t, "company": company, "branch": branch, "owner": owner,
        "token": create_access_token({"sub": str(owner.id)}),
    }


async def test_me_endpoint_reflects_custom_tenant_labels(
    client: AsyncClient, custom_labels_ctx: dict,
) -> None:
    r = await client.get("/api/auth/me", headers=auth(custom_labels_ctx["token"]))
    assert r.status_code == 200, r.text
    tenant_out = r.json()["tenant"]
    assert tenant_out["entity_name"] == "Prospecto"
    assert tenant_out["entity_plural"] == "Prospectos"
    assert tenant_out["deal_name"] == "Propiedad"
    assert tenant_out["deal_plural"] == "Propiedades"
    assert len(tenant_out["contact_statuses"]) == 2


async def test_custom_labels_tenant_core_endpoints_do_not_break(
    client: AsyncClient, custom_labels_ctx: dict,
) -> None:
    """Smoke end-to-end: un tenant con labels no-default no rompe endpoints core."""
    headers = auth(custom_labels_ctx["token"])

    endpoints = [
        "/api/v1/contacts",
        "/api/deals",
        "/api/dashboard/panels",
        "/api/dashboard",
    ]
    for path in endpoints:
        r = await client.get(path, headers=headers)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text}"


async def test_default_tenant_labels_unaffected(client: AsyncClient, owner_token: str) -> None:
    """Control: el tenant por defecto (fixture `tenant`) conserva los labels genéricos."""
    r = await client.get("/api/auth/me", headers=auth(owner_token))
    assert r.status_code == 200, r.text
    tenant_out = r.json()["tenant"]
    assert tenant_out["entity_name"] == "Contacto"
    assert tenant_out["deal_name"] == "Oportunidad"
