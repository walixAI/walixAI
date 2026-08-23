"""
Regresión — users.py::_require_owner ahora incluye PLATFORM_OWNER
(hallazgo #2, docs/PERMISSIONS_DRIFT_BACKLOG.md).

Código auditado:
  - app/api/users.py::_require_owner (líneas 106-111) — antes exigía
    exactamente UserRole.OWNER, excluyendo PLATFORM_OWNER, a diferencia de
    todos los demás _require_owner/_OWNER_ROLES del código (billing.py,
    finance.py, profitability.py, walix_builder.py, tenant.py — todos
    {OWNER, PLATFORM_OWNER}).
  - Usada en create_team_member (POST /api/branches/{branch_id}/team,
    línea 163) y toggle_active (PATCH /api/users/{user_id}/toggle,
    línea 280).

No se creó una constante compartida en app/core/roles.py para este fix —
el patrón {OWNER, PLATFORM_OWNER} está duplicado en muchos otros archivos
(billing.py, finance.py, profitability.py, walix_builder.py, tenant.py),
consolidar todos esos es un refactor mucho más grande que este hallazgo
puntual; se dejó como decisión aparte para el chat, no se hizo acá.

No había ningún test previo que asumiera que PLATFORM_OWNER NO podía crear
team members o hacer toggle — solo se agregó cobertura nueva.
"""
from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_platform_owner(db: AsyncSession, tenant: Tenant, branch: Branch) -> str:
    u = User(
        tenant_id=tenant.id, branch_id=branch.id,
        email=f"po-{uuid.uuid4().hex[:6]}@walix.test", name="Platform Owner",
        hashed_password=hash_password("test1234"),
        role=UserRole.PLATFORM_OWNER, is_active=True,
    )
    db.add(u)
    await db.flush()
    return create_access_token({"sub": str(u.id)})


# ── PLATFORM_OWNER ahora puede crear team members ───────────────────────────────

async def test_platform_owner_can_create_team_member(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch,
) -> None:
    po_token = await _make_platform_owner(db, tenant, branch)

    r = await client.post(
        f"/api/branches/{branch.id}/team",
        json={
            "name": "Nuevo Vendedor", "email": f"nuevo-{uuid.uuid4().hex[:6]}@walix.test",
            "role": "asesor", "password": "test1234",
        },
        headers=auth(po_token),
    )
    assert r.status_code == 201, r.text


async def test_asesor_denied_create_team_member(
    client: AsyncClient, branch: Branch, asesor_token: str,
) -> None:
    r = await client.post(
        f"/api/branches/{branch.id}/team",
        json={
            "name": "Nuevo Vendedor", "email": f"nuevo-{uuid.uuid4().hex[:6]}@walix.test",
            "role": "asesor", "password": "test1234",
        },
        headers=auth(asesor_token),
    )
    assert r.status_code == 403


# ── PLATFORM_OWNER ahora puede hacer toggle_active ──────────────────────────────

async def test_platform_owner_can_toggle_active(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, asesor_user: User,
) -> None:
    po_token = await _make_platform_owner(db, tenant, branch)

    r = await client.patch(f"/api/users/{asesor_user.id}/toggle", headers=auth(po_token))
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


async def test_gerente_denied_toggle_active(
    client: AsyncClient, manager_token: str, asesor_user: User,
) -> None:
    r = await client.patch(f"/api/users/{asesor_user.id}/toggle", headers=auth(manager_token))
    assert r.status_code == 403
