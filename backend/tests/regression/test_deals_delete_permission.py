"""
Regresión — DELETE /api/deals/{deal_id}: restricción de rol (hallazgo #5,
docs/PERMISSIONS_DRIFT_BACKLOG.md).

Código auditado:
  - app/api/deals.py::delete_deal — antes no tenía ningún check de rol;
    ahora exige current_user.role in _MANAGER_ROLES (OWNER, GERENTE, IT)
    O deal.owner_id == current_user.id, mismo criterio que
    app/api/contacts.py::delete_contact (_MANAGER_ROLES + ownership).
  - create_deal y update_deal quedan fuera de alcance a propósito — no se
    tocaron y no se prueban acá.
"""
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.deal import Deal
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_deal(
    db: AsyncSession, tenant: Tenant, contact, stages: list[PipelineStage], owner: User,
) -> Deal:
    d = Deal(
        tenant_id=tenant.id,
        lead_id=contact.id,
        pipeline_stage_id=stages[0].id,
        title="Deal de prueba",
        amount=10_000,
        probability=stages[0].probability_default,
        owner_id=owner.id,
    )
    db.add(d)
    await db.flush()
    return d


async def _make_second_asesor(db: AsyncSession, tenant: Tenant, branch: Branch) -> tuple[User, str]:
    """Un segundo ASESOR, distinto del fixture asesor_user — para probar que un
    no-manager no puede borrar un deal ajeno (ni siquiera si comparte rol con
    el dueño real)."""
    u = User(
        tenant_id=tenant.id,
        branch_id=branch.id,
        email="otro-asesor@walix.test",
        name="Otro Asesor",
        hashed_password=hash_password("test1234"),
        role=UserRole.ASESOR,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    token = create_access_token({"sub": str(u.id)})
    return u, token


# ── Manager-tier puede borrar un deal ajeno ─────────────────────────────────────

async def test_manager_can_delete_others_deal(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, contact,
    stages: list[PipelineStage], asesor_user: User, manager_token: str,
) -> None:
    """GERENTE (_MANAGER_ROLES) borra un deal asignado a otro usuario (asesor)."""
    d = await _make_deal(db, tenant, contact, stages, owner=asesor_user)
    deal_id = d.id

    r = await client.delete(f"/api/deals/{deal_id}", headers=auth(manager_token))
    assert r.status_code == 204

    still_there = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
    assert still_there is None  # hard delete real, no soft delete


# ── El usuario asignado puede borrar su propio deal aunque no sea manager ──────

async def test_assigned_owner_can_delete_own_deal(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, contact,
    stages: list[PipelineStage], asesor_user: User, asesor_token: str,
) -> None:
    """ASESOR (no manager-tier) borra un deal cuyo owner_id es su propio id."""
    d = await _make_deal(db, tenant, contact, stages, owner=asesor_user)
    deal_id = d.id

    r = await client.delete(f"/api/deals/{deal_id}", headers=auth(asesor_token))
    assert r.status_code == 204

    still_there = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
    assert still_there is None


# ── No-manager y no-asignado recibe 403 ─────────────────────────────────────────

async def test_non_manager_non_owner_gets_403(
    client: AsyncClient, db: AsyncSession, tenant: Tenant, branch: Branch, contact,
    stages: list[PipelineStage], asesor_user: User,
) -> None:
    """Un segundo ASESOR (ni manager-tier ni asignado) no puede borrar el deal."""
    d = await _make_deal(db, tenant, contact, stages, owner=asesor_user)
    deal_id = d.id
    _, other_token = await _make_second_asesor(db, tenant, branch)

    r = await client.delete(f"/api/deals/{deal_id}", headers=auth(other_token))
    assert r.status_code == 403

    still_there = (await db.execute(select(Deal).where(Deal.id == deal_id))).scalar_one_or_none()
    assert still_there is not None  # no se borró
