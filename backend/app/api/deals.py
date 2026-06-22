"""Sprint 13A — CRUD API para Deals.

Reglas:
- Siempre filtrar por tenant_id del JWT (RLS es segunda línea de defensa).
- Un Deal pertenece a un Lead; el Lead debe existir en el mismo tenant.
- El pipeline_stage debe existir en el mismo tenant.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.deal import Deal
from app.models.deal_stage_history import DealStageHistory
from app.models.lead import Lead
from app.models.pipeline import PipelineStage
from app.models.user import User
from app.schemas.deal import DealCreate, DealListResponse, DealRead, DealUpdate


class StageHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    from_stage_name: str | None
    to_stage_id: uuid.UUID
    to_stage_name: str
    changed_at: datetime

_UNSET = object()  # sentinel para distinguir owner_id=None explícito vs no enviado

router = APIRouter(prefix="/deals", tags=["deals"])

PAGE_SIZE = 25


async def _get_deal_or_404(
    deal_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> Deal:
    row = await db.get(Deal, deal_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal no encontrado")
    return row


async def _validate_lead(lead_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> None:
    lead = await db.get(Lead, lead_id)
    if not lead or lead.tenant_id != tenant_id or lead.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lead no encontrado en este tenant",
        )


async def _get_owner_or_422(owner_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> User:
    user = await db.get(User, owner_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Usuario (owner) no encontrado en este tenant",
        )
    return user


async def _get_stage_or_422(stage_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> PipelineStage:
    stage = await db.get(PipelineStage, stage_id)
    if not stage or stage.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Etapa de pipeline no encontrada en este tenant",
        )
    return stage


# ── POST /api/deals ───────────────────────────────────────────────────────────

@router.post("", response_model=DealRead, status_code=status.HTTP_201_CREATED)
async def create_deal(
    body: DealCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Deal:
    await _validate_lead(body.lead_id, current_user.tenant_id, db)
    await _get_stage_or_422(body.pipeline_stage_id, current_user.tenant_id, db)

    # owner_id: usa el del body si viene, si no se autoasigna al usuario autenticado
    if body.owner_id is not None:
        await _get_owner_or_422(body.owner_id, current_user.tenant_id, db)
        resolved_owner_id = body.owner_id
    else:
        resolved_owner_id = current_user.id

    deal = Deal(
        tenant_id=current_user.tenant_id,
        lead_id=body.lead_id,
        pipeline_stage_id=body.pipeline_stage_id,
        title=body.title,
        amount=body.amount,
        probability=body.probability,
        expected_close_date=body.expected_close_date,
        source=body.source,
        notes=body.notes,
        owner_id=resolved_owner_id,
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return deal


# ── GET /api/deals ────────────────────────────────────────────────────────────

@router.get("", response_model=DealListResponse)
async def list_deals(
    pipeline_stage_id: uuid.UUID | None = Query(default=None),
    lead_id: uuid.UUID | None = Query(default=None),
    is_won: bool | None = Query(default=None),
    is_lost: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DealListResponse:
    base = select(Deal).where(Deal.tenant_id == current_user.tenant_id)

    if pipeline_stage_id is not None:
        base = base.where(Deal.pipeline_stage_id == pipeline_stage_id)
    if lead_id is not None:
        base = base.where(Deal.lead_id == lead_id)
    if is_won is not None:
        base = base.where(Deal.is_won == is_won)
    if is_lost is not None:
        base = base.where(Deal.is_lost == is_lost)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(Deal.created_at.desc())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
    ).scalars().all()

    return DealListResponse(items=list(rows), total=total, page=page, page_size=PAGE_SIZE)


# ── GET /api/deals/{id} ───────────────────────────────────────────────────────

@router.get("/{deal_id}", response_model=DealRead)
async def get_deal(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Deal:
    return await _get_deal_or_404(deal_id, current_user.tenant_id, db)


# ── GET /api/deals/{id}/stage-history ────────────────────────────────────────

@router.get("/{deal_id}/stage-history", response_model=list[StageHistoryItem])
async def get_deal_stage_history(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StageHistoryItem]:
    await _get_deal_or_404(deal_id, current_user.tenant_id, db)

    FromStage = aliased(PipelineStage)
    ToStage   = aliased(PipelineStage)

    rows = (
        await db.execute(
            select(
                DealStageHistory,
                FromStage.name.label("from_stage_name"),
                ToStage.name.label("to_stage_name"),
            )
            .outerjoin(FromStage, DealStageHistory.from_stage_id == FromStage.id)
            .join(ToStage, DealStageHistory.to_stage_id == ToStage.id)
            .where(
                DealStageHistory.deal_id == deal_id,
                DealStageHistory.tenant_id == current_user.tenant_id,
            )
            .order_by(DealStageHistory.changed_at.desc())
        )
    ).fetchall()

    return [
        StageHistoryItem(
            id=h.id,
            from_stage_id=h.from_stage_id,
            from_stage_name=from_name,
            to_stage_id=h.to_stage_id,
            to_stage_name=to_name,
            changed_at=h.changed_at,
        )
        for h, from_name, to_name in rows
    ]


# ── PATCH /api/deals/{id} ─────────────────────────────────────────────────────

@router.patch("/{deal_id}", response_model=DealRead)
async def update_deal(
    deal_id: uuid.UUID,
    body: DealUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Deal:
    deal = await _get_deal_or_404(deal_id, current_user.tenant_id, db)

    prev_stage_id = deal.pipeline_stage_id
    stage_changed = False

    if body.pipeline_stage_id is not None and body.pipeline_stage_id != prev_stage_id:
        new_stage = await _get_stage_or_422(body.pipeline_stage_id, current_user.tenant_id, db)
        deal.pipeline_stage_id = body.pipeline_stage_id
        stage_changed = True
        if body.probability is None:
            deal.probability = new_stage.probability_default
    if body.title is not None:
        deal.title = body.title
    if body.amount is not None:
        deal.amount = body.amount
    if body.probability is not None:
        deal.probability = body.probability
    if body.expected_close_date is not None:
        deal.expected_close_date = body.expected_close_date
    if body.is_won is not None:
        deal.is_won = body.is_won
    if body.is_lost is not None:
        deal.is_lost = body.is_lost
    if body.source is not None:
        deal.source = body.source
    if body.notes is not None:
        deal.notes = body.notes
    if body.lost_reason is not None:
        deal.lost_reason = body.lost_reason
    if body.lost_comment is not None:
        deal.lost_comment = body.lost_comment
    if "owner_id" in body.model_fields_set:
        if body.owner_id is not None:
            await _get_owner_or_422(body.owner_id, current_user.tenant_id, db)
        deal.owner_id = body.owner_id

    if stage_changed:
        db.add(DealStageHistory(
            tenant_id=current_user.tenant_id,
            deal_id=deal.id,
            from_stage_id=prev_stage_id,
            to_stage_id=deal.pipeline_stage_id,
        ))

    await db.commit()
    await db.refresh(deal)
    return deal


# ── DELETE /api/deals/{id} ────────────────────────────────────────────────────

@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    deal = await _get_deal_or_404(deal_id, current_user.tenant_id, db)
    await db.delete(deal)
    await db.commit()
