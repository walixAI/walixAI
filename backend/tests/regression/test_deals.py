"""
Regresión — Deal / Pipeline (Sprint 13-14).

Código auditado: app/api/deals.py, app/models/deal.py, app/models/deal_stage_history.py,
app/models/pipeline.py, app/schemas/deal.py.

Notas de auditoría (leídas del código real, no asumidas):
  - Deal NO tiene campos de monto en Lead — `amount`/`probability` viven en Deal.
  - Al crear un Deal sin `owner_id` en el body, se autoasigna a `current_user.id`
    (deals.py:100-104).
  - Al reasignar `owner_id` en un PATCH, el código NO aplica ninguna restricción
    de rol (deals.py:282-285) — cualquier usuario autenticado del mismo tenant
    puede reasignar. Se cubre explícitamente como regresión (no se asume que
    deba requerir gerente+).
  - DealStageHistory usa la columna `changed_at` (server_default=now()), NO
    `updated_at` — confirmado en app/models/deal_stage_history.py.
  - Cuando cambia `pipeline_stage_id` en un PATCH y el body NO trae
    `probability`, el código hereda `new_stage.probability_default` en
    `deal.probability` (deals.py:260-261).
  - Los badges de salud (Hot/Cold/Stale/Overdue) NO existen en el backend:
    viven enteramente en el frontend (frontend/src/lib/dealHealth.ts,
    función pura `computeDealHealth`), usando `deal.updatedAt` para
    `daysInStage` y `contactLastActivityAt` para hot/cold — NO usan
    DealStageHistory.changed_at como podría asumirse. Se cubren como test E2E
    de Playwright (ver e2e/regression/dashboard_intelligence.spec.ts no aplica;
    la cobertura de badges vive en e2e/regression/pipeline_kanban.spec.ts),
    no aquí — no hay endpoint de backend que testear para esta pieza.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal
from app.models.deal_stage_history import DealStageHistory
from app.models.pipeline import PipelineStage
from app.models.user import User, UserRole


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Creación ──────────────────────────────────────────────────────────────────

async def test_create_deal_auto_assigns_owner_to_caller(
    client: AsyncClient, contact, stages: list[PipelineStage], owner_token: str, owner_user: User,
) -> None:
    """POST /api/deals sin owner_id se autoasigna al usuario autenticado."""
    r = await client.post(
        "/api/deals",
        json={
            "lead_id": str(contact.id),
            "pipeline_stage_id": str(stages[0].id),
            "title": "Deal sin owner explícito",
            "amount": "5000",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["owner_id"] == str(owner_user.id)
    # amount/probability viven en Deal, no en Lead — confirmado por schema DealRead
    assert "amount" in body and "probability" in body


async def test_create_deal_respects_explicit_owner(
    client: AsyncClient, db: AsyncSession, contact, stages, tenant, branch, owner_token: str,
) -> None:
    """Si el body trae owner_id, se usa ese valor (validado contra el tenant)."""
    other = User(
        tenant_id=tenant.id, branch_id=branch.id,
        email=f"otro-{uuid.uuid4().hex[:6]}@walix.test", name="Otro Asesor",
        hashed_password="x", role=UserRole.ASESOR, is_active=True,
    )
    db.add(other)
    await db.flush()

    r = await client.post(
        "/api/deals",
        json={
            "lead_id": str(contact.id),
            "pipeline_stage_id": str(stages[0].id),
            "title": "Deal con owner explícito",
            "amount": "1000",
            "owner_id": str(other.id),
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["owner_id"] == str(other.id)


# ── Reasignación de owner (sin restricción de rol incorrecta) ────────────────

async def test_deal_owner_reassignable_by_any_tenant_role(
    client: AsyncClient, db: AsyncSession, deal: Deal, tenant, branch, asesor_token: str,
) -> None:
    """Regresión: reasignar owner_id vía PATCH no está bloqueado por rol.

    El código real (deals.py update_deal) no aplica ningún chequeo de rol al
    tocar owner_id — solo valida que el nuevo owner pertenezca al tenant. Este
    test documenta ese comportamiento tal como existe; si en el futuro se
    agrega una restricción de rol, este test fallará y habrá que decidir
    conscientemente el nuevo contrato.
    """
    new_owner = User(
        tenant_id=tenant.id, branch_id=branch.id,
        email=f"nuevo-owner-{uuid.uuid4().hex[:6]}@walix.test", name="Nuevo Owner",
        hashed_password="x", role=UserRole.ASESOR, is_active=True,
    )
    db.add(new_owner)
    await db.flush()

    r = await client.patch(
        f"/api/deals/{deal.id}",
        json={"owner_id": str(new_owner.id)},
        headers=auth(asesor_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["owner_id"] == str(new_owner.id)


async def test_deal_owner_reassign_rejects_user_from_other_tenant(
    client: AsyncClient, deal: Deal, owner_token: str, other_tenant_ctx: dict,
) -> None:
    """El nuevo owner_id debe pertenecer al mismo tenant (422 si no)."""
    r = await client.patch(
        f"/api/deals/{deal.id}",
        json={"owner_id": other_tenant_ctx["user"].id.__str__()},
        headers=auth(owner_token),
    )
    assert r.status_code == 422, r.text


# ── Stage change → herencia de probability ────────────────────────────────────

async def test_stage_change_inherits_probability_default_when_not_provided(
    client: AsyncClient, deal: Deal, stages: list[PipelineStage], owner_token: str,
) -> None:
    """Cambiar de etapa sin mandar `probability` hereda `new_stage.probability_default`."""
    target_stage = stages[1]  # Negociación, probability_default=60
    assert deal.probability != target_stage.probability_default

    r = await client.patch(
        f"/api/deals/{deal.id}",
        json={"pipeline_stage_id": str(target_stage.id)},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pipeline_stage_id"] == str(target_stage.id)
    assert body["probability"] == target_stage.probability_default


async def test_stage_change_with_explicit_probability_does_not_inherit(
    client: AsyncClient, deal: Deal, stages: list[PipelineStage], owner_token: str,
) -> None:
    """Si el body SÍ trae `probability`, no se sobreescribe con el default de la etapa."""
    target_stage = stages[1]
    r = await client.patch(
        f"/api/deals/{deal.id}",
        json={"pipeline_stage_id": str(target_stage.id), "probability": 33},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["probability"] == 33


# ── Historial de stage — changed_at, no updated_at ────────────────────────────

async def test_stage_change_writes_history_with_changed_at(
    client: AsyncClient, db: AsyncSession, deal: Deal, stages: list[PipelineStage], owner_token: str,
) -> None:
    """DealStageHistory se registra con `changed_at` como timestamp de negocio.

    Nota: `updated_at` SÍ existe como columna heredada de app.models.base.Base
    (toda tabla la tiene), pero el código de deals.py nunca la usa para estas
    filas — son inmutables, solo se insertan. `changed_at` es la columna que
    realmente importa para ordenar/leer el historial (ver deals.py:223,
    `.order_by(DealStageHistory.changed_at.desc())`).
    """
    target_stage = stages[1]
    r = await client.patch(
        f"/api/deals/{deal.id}",
        json={"pipeline_stage_id": str(target_stage.id)},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text

    hist_row = (
        await db.execute(
            select(DealStageHistory).where(DealStageHistory.deal_id == deal.id)
        )
    ).scalar_one()
    assert hist_row.changed_at is not None
    assert hist_row.from_stage_id == stages[0].id
    assert hist_row.to_stage_id == target_stage.id

    # También vía API
    r2 = await client.get(f"/api/deals/{deal.id}/stage-history", headers=auth(owner_token))
    assert r2.status_code == 200, r2.text
    items = r2.json()
    assert len(items) == 1
    assert "changed_at" in items[0]


async def test_deal_not_found_returns_404(client: AsyncClient, owner_token: str) -> None:
    fake_id = str(uuid.uuid4())
    r = await client.get(f"/api/deals/{fake_id}", headers=auth(owner_token))
    assert r.status_code == 404
