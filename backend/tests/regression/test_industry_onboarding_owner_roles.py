"""
Regresión — industry_onboarding.py::_OWNER_ROLES ahora incluye
PLATFORM_OWNER (hallazgo #3, docs/PERMISSIONS_DRIFT_BACKLOG.md).

Código auditado:
  - app/api/industry_onboarding.py:48 — _OWNER_ROLES pasó de (OWNER,) a
    (OWNER, PLATFORM_OWNER).
  - get_industry_settings (GET /api/v1/settings/industry) y
    change_industry (POST /api/v1/settings/industry) — ambos llaman
    _require_owner.

Nota de diseño importante (ver mensaje del PR/backlog): NINGUNO de los dos
endpoints acepta un tenant_id objetivo — ambos operan exclusivamente sobre
current_user.tenant_id. A diferencia de app/api/platform.py (donde las
operaciones cross-tenant de PLATFORM_OWNER sí reciben tenant_id explícito
como parámetro), este fix solo permite que un usuario con rol
PLATFORM_OWNER gestione la industria de SU PROPIO tenant — no la de un
tenant ajeno, porque el endpoint no tiene ningún mecanismo para apuntar a
otro tenant. Por eso no hay un test de "PLATFORM_OWNER cambia la industria
de OTRO tenant" acá: sería falso, el endpoint no lo permite con o sin este
fix. Habilitar eso de verdad requeriría rediseñar el endpoint (agregar
tenant_id, mover a platform.py o similar) — fuera de alcance de este
hallazgo puntual.

No había ningún test previo para industry_onboarding.py — se agrega
cobertura nueva, no se ajustó nada existente.
"""
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_platform_owner(db: AsyncSession, tenant: Tenant, branch: Branch) -> str:
    u = User(
        tenant_id=tenant.id, branch_id=branch.id,
        email="po-industry@walix.test", name="Platform Owner",
        hashed_password=hash_password("test1234"),
        role=UserRole.PLATFORM_OWNER, is_active=True,
    )
    db.add(u)
    await db.flush()
    return create_access_token({"sub": str(u.id)})


# ── GET /api/v1/settings/industry ───────────────────────────────────────────────

async def test_platform_owner_can_get_industry_settings(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch,
) -> None:
    po_token = await _make_platform_owner(db, tenant, branch)

    r = await client.get("/api/v1/settings/industry", headers=auth(po_token))
    assert r.status_code == 200, r.text
    assert "current" in r.json()


async def test_asesor_denied_get_industry_settings(
    client: AsyncClient, asesor_token: str,
) -> None:
    r = await client.get("/api/v1/settings/industry", headers=auth(asesor_token))
    assert r.status_code == 403


# ── POST /api/v1/settings/industry ──────────────────────────────────────────────

async def test_platform_owner_change_industry_recreates_pipeline(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch,
    stages: list[PipelineStage],
) -> None:
    """confirm_reset=true debe archivar las etapas viejas y crear las nuevas
    del template — no solo devolver 200."""
    po_token = await _make_platform_owner(db, tenant, branch)
    old_stage_ids = {s.id for s in stages}

    r = await client.post(
        "/api/v1/settings/industry",
        json={"industry_key": "servicios_profesionales", "confirm_reset": True},
        headers=auth(po_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["industry_key"] == "servicios_profesionales"
    assert body["stages_created"] > 0

    await db.refresh(tenant)
    assert tenant.industry_key == "servicios_profesionales"

    old_rows = (
        await db.execute(select(PipelineStage).where(PipelineStage.id.in_(old_stage_ids)))
    ).scalars().all()
    assert len(old_rows) == len(old_stage_ids)
    assert all(s.is_archived for s in old_rows)

    active_rows = (
        await db.execute(
            select(PipelineStage).where(
                PipelineStage.tenant_id == tenant.id,
                PipelineStage.is_archived.is_(False),
            )
        )
    ).scalars().all()
    assert len(active_rows) == body["stages_created"]
    assert all(s.id not in old_stage_ids for s in active_rows)


async def test_gerente_denied_change_industry(
    client: AsyncClient, manager_token: str,
) -> None:
    r = await client.post(
        "/api/v1/settings/industry",
        json={"industry_key": "servicios_profesionales", "confirm_reset": True},
        headers=auth(manager_token),
    )
    assert r.status_code == 403
