"""Módulo Oportunidades — CRUD + Kanban Board + Forecast + CSV.

Patrón: idéntico a app/api/leads.py.
  - Todo query filtra por tenant_id del JWT primero; RLS es la segunda línea.
  - deleted_at IS NULL en toda lectura.
  - Cada mutación crea una OpportunityActivity y actualiza last_activity_at.
  - Claude NO se invoca aquí (eso es el Prompt 5).
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.opportunity_activity import OpportunityActivity
from app.models.opportunity_stage_history import OpportunityStageHistory
from app.models.pipeline import PipelineStage
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _require_branch(user: User) -> uuid.UUID:
    if user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no tiene una sucursal asignada",
        )
    return user.branch_id


def _resolve_branch(user: User, branch_id_param: uuid.UUID | None) -> uuid.UUID:
    """Resuelve el branch para la solicitud.

    Owner/IT pueden pasar branch_id en query; otros usan su propio branch.
    """
    if user.role in _MULTI_BRANCH_ROLES:
        if branch_id_param:
            return branch_id_param
        if user.branch_id:
            return user.branch_id
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pasa branch_id para usuarios con acceso multi-sucursal",
        )
    return _require_branch(user)


def _days_since(dt: datetime | None) -> int:
    if dt is None:
        return 0
    now = datetime.now(timezone.utc)
    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return max(0, (now - aware).days)


async def _get_opportunity(
    db: AsyncSession, opp_id: uuid.UUID, user: User
) -> Opportunity:
    """Carga una oportunidad validando tenant y que no esté soft-deleted."""
    opp = await db.get(Opportunity, opp_id)
    if opp is None or opp.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidad no encontrada",
        )
    if opp.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidad no encontrada",
        )
    if user.role not in _MULTI_BRANCH_ROLES and opp.branch_id != user.branch_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidad no encontrada",
        )
    return opp


async def _get_stage_in_branch(
    db: AsyncSession, stage_id: uuid.UUID, branch_id: uuid.UUID, tenant_id: uuid.UUID
) -> PipelineStage:
    stage = await db.get(PipelineStage, stage_id)
    if (
        stage is None
        or stage.tenant_id != tenant_id
        or stage.branch_id != branch_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Etapa no encontrada en esta sucursal",
        )
    return stage


def _opp_read(
    opp: Opportunity,
    stage: PipelineStage | None = None,
    lead: "Lead | None" = None,
    assigned_to_name: str | None = None,
) -> OppRead:
    """Serializa Opportunity → OppRead sin acceder a relaciones lazy.

    SQLAlchemy async levanta MissingGreenlet si Pydantic accede a atributos
    lazy (opp.stage, opp.lead) fuera de un await. Construimos OppRead
    directamente desde atributos de columna y objetos ya cargados.
    """
    return OppRead(
        id=opp.id,
        tenant_id=opp.tenant_id,
        branch_id=opp.branch_id,
        title=opp.title,
        amount=opp.amount,
        currency=opp.currency,
        probability=opp.probability,
        close_date=opp.close_date,
        source=opp.source,
        status=opp.status,
        won_at=opp.won_at,
        lost_at=opp.lost_at,
        lost_reason=opp.lost_reason,
        stage_entered_at=opp.stage_entered_at,
        last_activity_at=opp.last_activity_at,
        ai_suggestion=opp.ai_suggestion,
        ai_suggestion_urgency=opp.ai_suggestion_urgency,
        urgency_score=opp.urgency_score,
        notes=opp.notes,
        assigned_to=opp.assigned_to,
        created_at=opp.created_at,
        updated_at=opp.updated_at,
        stage=StageOut.model_validate(stage) if stage else None,
        lead=LeadOut.model_validate(lead) if lead else None,
        assigned_to_name=assigned_to_name,
        days_in_stage=_days_since(opp.stage_entered_at),
    )


async def _add_activity(
    db: AsyncSession,
    opportunity_id: uuid.UUID,
    tenant_id: uuid.UUID,
    type_: str,
    description: str,
    created_by: uuid.UUID | None = None,
) -> None:
    db.add(OpportunityActivity(
        opportunity_id=opportunity_id,
        tenant_id=tenant_id,
        type=type_,
        description=description,
        created_by=created_by,
    ))


async def _move_stage(
    db: AsyncSession,
    opp: Opportunity,
    stage: PipelineStage,
    changed_by: uuid.UUID | None,
) -> None:
    """Aplica el cambio de etapa, historial y actualiza timestamps.

    No hace flush ni commit — el caller decide cuándo persistir.
    """
    old_stage_id = opp.stage_id
    now = datetime.now(timezone.utc)

    opp.stage_id = stage.id
    opp.stage_entered_at = now
    opp.last_activity_at = now

    db.add(OpportunityStageHistory(
        opportunity_id=opp.id,
        tenant_id=opp.tenant_id,
        from_stage_id=old_stage_id,
        to_stage_id=stage.id,
        changed_by=changed_by,
    ))

    from_name = "(sin etapa)"
    if old_stage_id:
        old_stage = await db.get(PipelineStage, old_stage_id)
        if old_stage:
            from_name = old_stage.name

    await _add_activity(
        db, opp.id, opp.tenant_id, "stage_change",
        f"Etapa cambiada de {from_name} a {stage.name}",
        created_by=changed_by,
    )


# ── Pydantic response schemas (locales, complementan los de schemas/opportunity.py) ─

class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    color: str | None = None
    order_index: int
    is_won: bool
    is_lost: bool
    probability_default: int | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str | None = None
    last_name: str | None = None
    wa_phone: str | None = None
    company: str | None = None


class OppRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    title: str
    amount: Decimal | None = None
    currency: str
    probability: int | None = None
    close_date: date | None = None
    source: str | None = None
    status: str
    won_at: datetime | None = None
    lost_at: datetime | None = None
    lost_reason: str | None = None
    stage_entered_at: datetime
    last_activity_at: datetime | None = None
    ai_suggestion: str | None = None
    ai_suggestion_urgency: str | None = None
    urgency_score: int | None = None
    notes: str | None = None
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    created_at: datetime
    updated_at: datetime
    lead: LeadOut | None = None
    stage: StageOut | None = None
    days_in_stage: int = 0


class OppActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    description: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class OppHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    from_stage_id: uuid.UUID | None = None
    to_stage_id: uuid.UUID
    changed_by: uuid.UUID | None = None
    created_at: datetime


class OppDetail(OppRead):
    activities: list[OppActivityOut] = []
    history: list[OppHistoryOut] = []


class OppListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    amount: Decimal | None = None
    currency: str
    probability: int | None = None
    close_date: date | None = None
    status: str
    source: str | None = None
    stage_entered_at: datetime
    last_activity_at: datetime | None = None
    ai_suggestion_urgency: str | None = None
    urgency_score: int | None = None
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    lead_name: str | None = None
    lead_wa_phone: str | None = None
    stage_name: str | None = None
    stage_color: str | None = None
    days_in_stage: int = 0
    created_at: datetime
    updated_at: datetime


class OppListResponse(BaseModel):
    items: list[OppListItem]
    total: int


# Board schemas
class BoardCard(BaseModel):
    id: uuid.UUID
    title: str
    amount: Decimal | None = None
    currency: str
    probability: int | None = None
    close_date: date | None = None
    stage_entered_at: datetime
    last_activity_at: datetime | None = None
    ai_suggestion: str | None = None
    ai_suggestion_urgency: str | None = None
    urgency_score: int | None = None
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    lead_name: str | None = None
    days_in_stage: int = 0


class BoardStageOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    color: str | None = None
    order_index: int
    is_won: bool
    is_lost: bool
    probability_default: int | None = None
    opportunities: list[BoardCard]
    total: int
    total_amount: Decimal


class BoardOut(BaseModel):
    stages: list[BoardStageOut]
    currency: str = "MXN"


# Forecast
class ForecastOut(BaseModel):
    pipeline_total: Decimal
    active_count: int
    weighted_total: Decimal
    closing_this_month: Decimal
    closing_change_pct: float | None = None
    trend: str  # up | down | flat
    currency: str = "MXN"


# Stale
class StaleOut(BaseModel):
    count: int
    total_amount: Decimal
    items: list[OppListItem]


# Request bodies
class OppCreateBody(BaseModel):
    title: str
    lead_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    amount: Decimal | None = None
    currency: str = "MXN"
    probability: int | None = None
    close_date: date | None = None
    source: str | None = None
    notes: str | None = None
    branch_id: uuid.UUID | None = None  # solo para owner/IT


class OppUpdateBody(BaseModel):
    title: str | None = None
    lead_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    amount: Decimal | None = None
    currency: str | None = None
    probability: int | None = None
    close_date: date | None = None
    source: str | None = None
    notes: str | None = None


class OppMoveBody(BaseModel):
    stage_id: uuid.UUID
    moved_by: str = "manual"


class OppMarkLostBody(BaseModel):
    lost_reason: str | None = None
    reason_code: str | None = None


class BulkStageBody(BaseModel):
    ids: list[uuid.UUID]
    stage_id: uuid.UUID


class BulkDeleteBody(BaseModel):
    ids: list[uuid.UUID]


# ── Helpers for serialization ──────────────────────────────────────────────────

async def _enrich_opp(
    opp: Opportunity,
    db: AsyncSession,
    assignee_cache: dict[uuid.UUID, str] | None = None,
) -> dict[str, Any]:
    """Carga lead y etapa en el objeto opp para serialización."""
    assignee_name: str | None = None
    if opp.assigned_to:
        if assignee_cache is not None and opp.assigned_to in assignee_cache:
            assignee_name = assignee_cache[opp.assigned_to]
        else:
            user = await db.get(User, opp.assigned_to)
            assignee_name = user.name if user else None
            if assignee_cache is not None:
                assignee_cache[opp.assigned_to] = assignee_name  # type: ignore[assignment]

    lead_name: str | None = None
    lead_wa_phone: str | None = None
    if opp.lead_id:
        lead = await db.get(Lead, opp.lead_id)
        if lead:
            parts = [p for p in [lead.name, lead.last_name] if p]
            lead_name = " ".join(parts) if parts else None
            lead_wa_phone = lead.wa_phone

    stage_name: str | None = None
    stage_color: str | None = None
    if opp.stage_id:
        stage = await db.get(PipelineStage, opp.stage_id)
        if stage:
            stage_name = stage.name
            stage_color = stage.color

    return {
        "assigned_to_name": assignee_name,
        "lead_name": lead_name,
        "lead_wa_phone": lead_wa_phone,
        "stage_name": stage_name,
        "stage_color": stage_color,
        "days_in_stage": _days_since(opp.stage_entered_at),
    }


# ── GET /board ─────────────────────────────────────────────────────────────────

@router.get("/board", response_model=BoardOut)
async def get_opportunities_board(
    branch_id: uuid.UUID | None = Query(default=None),
    limit_per_stage: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BoardOut:
    resolved_branch = _resolve_branch(current_user, branch_id)

    stages_result = await db.execute(
        select(PipelineStage)
        .where(
            PipelineStage.branch_id == resolved_branch,
            PipelineStage.tenant_id == current_user.tenant_id,
            PipelineStage.is_active.is_(True),
            PipelineStage.is_archived.is_(False),
        )
        .order_by(PipelineStage.order_index)
    )
    stages = stages_result.scalars().all()
    if not stages:
        return BoardOut(stages=[], currency="MXN")

    stage_ids = [s.id for s in stages]

    opps_result = await db.execute(
        select(Opportunity).where(
            Opportunity.tenant_id == current_user.tenant_id,
            Opportunity.branch_id == resolved_branch,
            Opportunity.stage_id.in_(stage_ids),
            Opportunity.status == "open",
            Opportunity.deleted_at.is_(None),
        )
    )
    all_opps = opps_result.scalars().all()

    # Batch-load assignees
    assignee_ids = {o.assigned_to for o in all_opps if o.assigned_to}
    assignee_names: dict[uuid.UUID, str] = {}
    if assignee_ids:
        users_result = await db.execute(
            select(User.id, User.name).where(User.id.in_(assignee_ids))
        )
        assignee_names = {row.id: row.name for row in users_result.fetchall()}

    # Batch-load leads for names
    lead_ids = {o.lead_id for o in all_opps if o.lead_id}
    lead_names: dict[uuid.UUID, str | None] = {}
    if lead_ids:
        leads_result = await db.execute(
            select(Lead.id, Lead.name, Lead.last_name).where(Lead.id.in_(lead_ids))
        )
        for row in leads_result.fetchall():
            parts = [p for p in [row.name, row.last_name] if p]
            lead_names[row.id] = " ".join(parts) if parts else None

    opps_by_stage: dict[uuid.UUID, list[Opportunity]] = {s.id: [] for s in stages}
    for opp in all_opps:
        if opp.stage_id in opps_by_stage:
            opps_by_stage[opp.stage_id].append(opp)

    board_stages: list[BoardStageOut] = []
    for stage in stages:
        stage_opps = opps_by_stage[stage.id]
        total_amount = sum(
            (o.amount or Decimal("0")) for o in stage_opps
        )
        cards = [
            BoardCard(
                id=opp.id,
                title=opp.title,
                amount=opp.amount,
                currency=opp.currency,
                probability=opp.probability,
                close_date=opp.close_date,
                stage_entered_at=opp.stage_entered_at,
                last_activity_at=opp.last_activity_at,
                ai_suggestion=opp.ai_suggestion,
                ai_suggestion_urgency=opp.ai_suggestion_urgency,
                urgency_score=opp.urgency_score,
                assigned_to=opp.assigned_to,
                assigned_to_name=assignee_names.get(opp.assigned_to) if opp.assigned_to else None,
                lead_name=lead_names.get(opp.lead_id) if opp.lead_id else None,
                days_in_stage=_days_since(opp.stage_entered_at),
            )
            for opp in stage_opps[:limit_per_stage]
        ]
        board_stages.append(BoardStageOut(
            id=stage.id,
            name=stage.name,
            slug=stage.slug,
            color=stage.color,
            order_index=stage.order_index,
            is_won=stage.is_won,
            is_lost=stage.is_lost,
            probability_default=stage.probability_default,
            opportunities=cards,
            total=len(stage_opps),
            total_amount=total_amount,
        ))

    return BoardOut(stages=board_stages)


# ── GET / (lista plana) ────────────────────────────────────────────────────────

@router.get("", response_model=OppListResponse)
async def list_opportunities(
    branch_id: uuid.UUID | None = Query(default=None),
    stage_id: uuid.UUID | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default="open", alias="status"),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    amount_min: Decimal | None = Query(default=None),
    amount_max: Decimal | None = Query(default=None),
    close_before: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OppListResponse:
    resolved_branch = _resolve_branch(current_user, branch_id)

    base = select(Opportunity).where(
        Opportunity.tenant_id == current_user.tenant_id,
        Opportunity.branch_id == resolved_branch,
        Opportunity.deleted_at.is_(None),
    )

    if status_filter and status_filter != "all":
        base = base.where(Opportunity.status == status_filter)
    if stage_id:
        base = base.where(Opportunity.stage_id == stage_id)
    if assigned_to:
        base = base.where(Opportunity.assigned_to == assigned_to)
    if source:
        base = base.where(Opportunity.source == source)
    if amount_min is not None:
        base = base.where(Opportunity.amount >= amount_min)
    if amount_max is not None:
        base = base.where(Opportunity.amount <= amount_max)
    if close_before:
        base = base.where(Opportunity.close_date < close_before)

    if q:
        q_like = f"%{q}%"
        # Join with leads is expensive in async SQLAlchemy; filter on title/notes
        # and lead name via subquery
        lead_ids_subq = select(Lead.id).where(
            Lead.tenant_id == current_user.tenant_id,
            Lead.deleted_at.is_(None),
            or_(
                Lead.name.ilike(q_like),
                Lead.last_name.ilike(q_like),
            ),
        ).scalar_subquery()
        base = base.where(or_(
            Opportunity.title.ilike(q_like),
            Opportunity.notes.ilike(q_like),
            Opportunity.lead_id.in_(lead_ids_subq),
        ))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    rows = await db.execute(
        base.order_by(Opportunity.updated_at.desc()).limit(limit).offset(offset)
    )
    opps = rows.scalars().all()

    # Batch-load supporting data
    assignee_ids = {o.assigned_to for o in opps if o.assigned_to}
    lead_ids = {o.lead_id for o in opps if o.lead_id}
    stage_ids = {o.stage_id for o in opps if o.stage_id}

    assignee_map: dict[uuid.UUID, str] = {}
    if assignee_ids:
        r = await db.execute(select(User.id, User.name).where(User.id.in_(assignee_ids)))
        assignee_map = {row.id: row.name for row in r.fetchall()}

    lead_map: dict[uuid.UUID, tuple[str | None, str | None]] = {}
    if lead_ids:
        r = await db.execute(
            select(Lead.id, Lead.name, Lead.last_name, Lead.wa_phone)
            .where(Lead.id.in_(lead_ids))
        )
        for row in r.fetchall():
            parts = [p for p in [row.name, row.last_name] if p]
            lead_map[row.id] = (" ".join(parts) if parts else None, row.wa_phone)

    stage_map: dict[uuid.UUID, tuple[str, str | None]] = {}
    if stage_ids:
        r = await db.execute(
            select(PipelineStage.id, PipelineStage.name, PipelineStage.color)
            .where(PipelineStage.id.in_(stage_ids))
        )
        stage_map = {row.id: (row.name, row.color) for row in r.fetchall()}

    items: list[OppListItem] = []
    for opp in opps:
        lead_name, lead_wa = lead_map.get(opp.lead_id, (None, None)) if opp.lead_id else (None, None)
        sname, scolor = stage_map.get(opp.stage_id, (None, None)) if opp.stage_id else (None, None)
        items.append(OppListItem(
            id=opp.id,
            title=opp.title,
            amount=opp.amount,
            currency=opp.currency,
            probability=opp.probability,
            close_date=opp.close_date,
            status=opp.status,
            source=opp.source,
            stage_entered_at=opp.stage_entered_at,
            last_activity_at=opp.last_activity_at,
            ai_suggestion_urgency=opp.ai_suggestion_urgency,
            urgency_score=opp.urgency_score,
            assigned_to=opp.assigned_to,
            assigned_to_name=assignee_map.get(opp.assigned_to) if opp.assigned_to else None,
            lead_name=lead_name,
            lead_wa_phone=lead_wa,
            stage_name=sname,
            stage_color=scolor,
            days_in_stage=_days_since(opp.stage_entered_at),
            created_at=opp.created_at,
            updated_at=opp.updated_at,
        ))

    return OppListResponse(items=items, total=total)


# ── POST / ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=OppRead, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    body: OppCreateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OppRead:
    resolved_branch = _resolve_branch(current_user, body.branch_id)

    # Validate lead if provided
    if body.lead_id:
        lead = await db.get(Lead, body.lead_id)
        if lead is None or lead.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contacto no encontrado",
            )
        if lead.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El contacto está eliminado y no puede vincularse a una oportunidad",
            )

    # Validate stage and inherit probability
    probability = body.probability
    if body.stage_id:
        stage = await _get_stage_in_branch(
            db, body.stage_id, resolved_branch, current_user.tenant_id
        )
        if probability is None and stage.probability_default is not None:
            probability = stage.probability_default

    opp = Opportunity(
        tenant_id=current_user.tenant_id,
        branch_id=resolved_branch,
        lead_id=body.lead_id,
        stage_id=body.stage_id,
        assigned_to=body.assigned_to,
        title=body.title,
        amount=body.amount,
        currency=body.currency.upper(),
        probability=probability,
        close_date=body.close_date,
        source=body.source,
        notes=body.notes,
        status="open",
        stage_entered_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.flush()  # genera el id

    await _add_activity(
        db, opp.id, opp.tenant_id, "created",
        f'Oportunidad "{opp.title}" creada',
        created_by=current_user.id,
    )

    if body.stage_id:
        db.add(OpportunityStageHistory(
            opportunity_id=opp.id,
            tenant_id=opp.tenant_id,
            from_stage_id=None,
            to_stage_id=body.stage_id,
            changed_by=current_user.id,
        ))

    await db.commit()
    await db.refresh(opp)

    stage_obj = await db.get(PipelineStage, opp.stage_id) if opp.stage_id else None
    assignee_name: str | None = None
    if opp.assigned_to:
        assignee = await db.get(User, opp.assigned_to)
        assignee_name = assignee.name if assignee else None
    return _opp_read(opp, stage=stage_obj, assigned_to_name=assignee_name)


# ── GET /forecast — ANTES de /{opp_id} para evitar captura UUID ───────────────

@router.get("/forecast", response_model=ForecastOut)
async def get_forecast(
    branch_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastOut:
    resolved_branch = _resolve_branch(current_user, branch_id)
    now = datetime.now(timezone.utc)
    today = now.date()
    month_start = today.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

    base_filter = [
        Opportunity.tenant_id == current_user.tenant_id,
        Opportunity.branch_id == resolved_branch,
        Opportunity.deleted_at.is_(None),
        Opportunity.status == "open",
    ]

    agg_result = await db.execute(
        select(
            func.count(Opportunity.id),
            func.coalesce(func.sum(Opportunity.amount), 0),
        ).where(*base_filter)
    )
    active_count, pipeline_total = agg_result.one()
    pipeline_total = Decimal(str(pipeline_total))

    weighted_result = await db.execute(
        select(
            func.coalesce(
                func.sum(Opportunity.amount * Opportunity.probability / 100), 0
            )
        ).where(
            *base_filter,
            Opportunity.amount.isnot(None),
            Opportunity.probability.isnot(None),
        )
    )
    weighted_total = Decimal(str(weighted_result.scalar_one()))

    closing_result = await db.execute(
        select(func.coalesce(func.sum(Opportunity.amount), 0)).where(
            *base_filter,
            Opportunity.close_date >= month_start,
            Opportunity.close_date < next_month,
        )
    )
    closing_this_month = Decimal(str(closing_result.scalar_one()))

    prev_closing_result = await db.execute(
        select(func.coalesce(func.sum(Opportunity.amount), 0)).where(
            Opportunity.tenant_id == current_user.tenant_id,
            Opportunity.branch_id == resolved_branch,
            Opportunity.deleted_at.is_(None),
            Opportunity.status == "open",
            Opportunity.close_date >= prev_month_start,
            Opportunity.close_date < month_start,
        )
    )
    prev_closing = Decimal(str(prev_closing_result.scalar_one()))

    closing_change_pct: float | None = None
    trend = "flat"
    if prev_closing > 0:
        change = float((closing_this_month - prev_closing) / prev_closing * 100)
        closing_change_pct = round(change, 1)
        trend = "up" if change > 2 else ("down" if change < -2 else "flat")

    return ForecastOut(
        pipeline_total=pipeline_total,
        active_count=int(active_count),
        weighted_total=weighted_total,
        closing_this_month=closing_this_month,
        closing_change_pct=closing_change_pct,
        trend=trend,
    )


# ── GET /stale — ANTES de /{opp_id} ───────────────────────────────────────────

@router.get("/stale", response_model=StaleOut)
async def get_stale_opportunities(
    branch_id: uuid.UUID | None = Query(default=None),
    days: int = Query(default=10, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StaleOut:
    resolved_branch = _resolve_branch(current_user, branch_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stale_filter = [
        Opportunity.tenant_id == current_user.tenant_id,
        Opportunity.branch_id == resolved_branch,
        Opportunity.deleted_at.is_(None),
        Opportunity.status == "open",
        or_(
            Opportunity.last_activity_at < cutoff,
            (Opportunity.last_activity_at.is_(None) & (Opportunity.created_at < cutoff)),
        ),
    ]

    count_result = await db.execute(
        select(
            func.count(Opportunity.id),
            func.coalesce(func.sum(Opportunity.amount), 0),
        ).where(*stale_filter)
    )
    count, total_amount = count_result.one()

    rows = await db.execute(
        select(Opportunity).where(*stale_filter)
        .order_by(Opportunity.last_activity_at.asc().nulls_first())
        .limit(50)
    )
    opps = rows.scalars().all()

    stage_ids = {o.stage_id for o in opps if o.stage_id}
    stage_map: dict[uuid.UUID, tuple[str, str | None]] = {}
    if stage_ids:
        r = await db.execute(
            select(PipelineStage.id, PipelineStage.name, PipelineStage.color)
            .where(PipelineStage.id.in_(stage_ids))
        )
        stage_map = {row.id: (row.name, row.color) for row in r.fetchall()}

    items = [
        OppListItem(
            id=o.id,
            title=o.title,
            amount=o.amount,
            currency=o.currency,
            probability=o.probability,
            close_date=o.close_date,
            status=o.status,
            source=o.source,
            stage_entered_at=o.stage_entered_at,
            last_activity_at=o.last_activity_at,
            ai_suggestion_urgency=o.ai_suggestion_urgency,
            urgency_score=o.urgency_score,
            assigned_to=o.assigned_to,
            stage_name=stage_map.get(o.stage_id, (None, None))[0] if o.stage_id else None,
            stage_color=stage_map.get(o.stage_id, (None, None))[1] if o.stage_id else None,
            days_in_stage=_days_since(o.stage_entered_at),
            created_at=o.created_at,
            updated_at=o.updated_at,
        )
        for o in opps
    ]

    return StaleOut(
        count=int(count),
        total_amount=Decimal(str(total_amount)),
        items=items,
    )


# ── GET /export.csv — ANTES de /{opp_id} ──────────────────────────────────────

@router.get("/export.csv")
async def export_csv(
    branch_id: uuid.UUID | None = Query(default=None),
    stage_id: uuid.UUID | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default="open", alias="status"),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    amount_min: Decimal | None = Query(default=None),
    amount_max: Decimal | None = Query(default=None),
    close_before: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    resolved_branch = _resolve_branch(current_user, branch_id)

    base = select(Opportunity).where(
        Opportunity.tenant_id == current_user.tenant_id,
        Opportunity.branch_id == resolved_branch,
        Opportunity.deleted_at.is_(None),
    )
    if status_filter and status_filter != "all":
        base = base.where(Opportunity.status == status_filter)
    if stage_id:
        base = base.where(Opportunity.stage_id == stage_id)
    if assigned_to:
        base = base.where(Opportunity.assigned_to == assigned_to)
    if source:
        base = base.where(Opportunity.source == source)
    if amount_min is not None:
        base = base.where(Opportunity.amount >= amount_min)
    if amount_max is not None:
        base = base.where(Opportunity.amount <= amount_max)
    if close_before:
        base = base.where(Opportunity.close_date < close_before)
    if q:
        q_like = f"%{q}%"
        base = base.where(or_(
            Opportunity.title.ilike(q_like),
            Opportunity.notes.ilike(q_like),
        ))

    rows = await db.execute(base.order_by(Opportunity.updated_at.desc()).limit(5000))
    opps = rows.scalars().all()

    lead_ids = {o.lead_id for o in opps if o.lead_id}
    stage_ids_csv = {o.stage_id for o in opps if o.stage_id}
    assignee_ids = {o.assigned_to for o in opps if o.assigned_to}

    lead_map: dict[uuid.UUID, str] = {}
    if lead_ids:
        r = await db.execute(select(Lead.id, Lead.name, Lead.last_name).where(Lead.id.in_(lead_ids)))
        for row in r.fetchall():
            parts = [p for p in [row.name, row.last_name] if p]
            lead_map[row.id] = " ".join(parts) if parts else ""

    stage_map_csv: dict[uuid.UUID, str] = {}
    if stage_ids_csv:
        r = await db.execute(select(PipelineStage.id, PipelineStage.name).where(PipelineStage.id.in_(stage_ids_csv)))
        stage_map_csv = {row.id: row.name for row in r.fetchall()}

    assignee_map_csv: dict[uuid.UUID, str] = {}
    if assignee_ids:
        r = await db.execute(select(User.id, User.name).where(User.id.in_(assignee_ids)))
        assignee_map_csv = {row.id: row.name for row in r.fetchall()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Oportunidad", "Contacto", "Monto", "Etapa",
        "Probabilidad", "Vendedor", "Días en etapa", "Fecha cierre",
    ])
    for opp in opps:
        writer.writerow([
            opp.title,
            lead_map.get(opp.lead_id, "") if opp.lead_id else "",
            str(opp.amount or ""),
            stage_map_csv.get(opp.stage_id, "") if opp.stage_id else "",
            f"{opp.probability}%" if opp.probability is not None else "",
            assignee_map_csv.get(opp.assigned_to, "") if opp.assigned_to else "",
            str(_days_since(opp.stage_entered_at)),
            str(opp.close_date) if opp.close_date else "",
        ])

    content = "﻿" + output.getvalue()  # BOM utf-8-sig para Excel en español

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oportunidades.csv"'},
    )


# ── GET /{id} ──────────────────────────────────────────────────────────────────

@router.get("/{opp_id}", response_model=OppDetail)
async def get_opportunity(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OppDetail:
    opp = await _get_opportunity(db, opp_id, current_user)

    # Load lead
    lead_obj: Lead | None = None
    if opp.lead_id:
        lead_obj = await db.get(Lead, opp.lead_id)

    # Load stage
    stage_obj: PipelineStage | None = None
    if opp.stage_id:
        stage_obj = await db.get(PipelineStage, opp.stage_id)

    # Load activities (last 50)
    acts_result = await db.execute(
        select(OpportunityActivity)
        .where(OpportunityActivity.opportunity_id == opp_id)
        .order_by(OpportunityActivity.created_at.desc())
        .limit(50)
    )
    activities = [OppActivityOut.model_validate(a) for a in acts_result.scalars().all()]

    # Load stage history
    hist_result = await db.execute(
        select(OpportunityStageHistory)
        .where(OpportunityStageHistory.opportunity_id == opp_id)
        .order_by(OpportunityStageHistory.created_at.desc())
        .limit(20)
    )
    history = [OppHistoryOut.model_validate(h) for h in hist_result.scalars().all()]

    detail = OppDetail(
        **OppRead.model_validate(opp).model_dump(),
        activities=activities,
        history=history,
    )
    detail.days_in_stage = _days_since(opp.stage_entered_at)
    if opp.assigned_to:
        user = await db.get(User, opp.assigned_to)
        detail.assigned_to_name = user.name if user else None
    if lead_obj:
        detail.lead = LeadOut.model_validate(lead_obj)
    if stage_obj:
        detail.stage = StageOut.model_validate(stage_obj)

    return detail


# ── PATCH /{id} ────────────────────────────────────────────────────────────────

@router.patch("/{opp_id}", response_model=OppRead)
async def update_opportunity(
    opp_id: uuid.UUID,
    body: OppUpdateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OppRead:
    opp = await _get_opportunity(db, opp_id, current_user)
    now = datetime.now(timezone.utc)
    changes: list[str] = []

    if body.title is not None:
        opp.title = body.title
        changes.append("título")
    if body.lead_id is not None:
        lead = await db.get(Lead, body.lead_id)
        if lead is None or lead.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
        if lead.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El contacto está eliminado")
        opp.lead_id = body.lead_id
        changes.append("contacto")
    if body.stage_id is not None:
        stage = await _get_stage_in_branch(db, body.stage_id, opp.branch_id, opp.tenant_id)
        await _move_stage(db, opp, stage, current_user.id)
        changes.append("etapa")
    if body.assigned_to is not None:
        opp.assigned_to = body.assigned_to
        changes.append("vendedor")
    if body.amount is not None:
        opp.amount = body.amount
        changes.append("monto")
    if body.currency is not None:
        opp.currency = body.currency.upper()
    if body.probability is not None:
        opp.probability = body.probability
        changes.append("probabilidad")
    if body.close_date is not None:
        opp.close_date = body.close_date
        changes.append("fecha de cierre")
    if body.source is not None:
        opp.source = body.source
    if body.notes is not None:
        opp.notes = body.notes
        changes.append("notas")

    if changes:
        opp.last_activity_at = now
        await _add_activity(
            db, opp.id, opp.tenant_id, "note",
            f"Actualizado: {', '.join(changes)}",
            created_by=current_user.id,
        )

    await db.commit()
    await db.refresh(opp)

    stage_obj = await db.get(PipelineStage, opp.stage_id) if opp.stage_id else None
    assignee_name: str | None = None
    if opp.assigned_to:
        assignee = await db.get(User, opp.assigned_to)
        assignee_name = assignee.name if assignee else None
    return _opp_read(opp, stage=stage_obj, assigned_to_name=assignee_name)


# ── PATCH /{id}/stage ──────────────────────────────────────────────────────────

@router.patch("/{opp_id}/stage", response_model=OppRead)
async def move_opportunity_stage(
    opp_id: uuid.UUID,
    body: OppMoveBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OppRead:
    opp = await _get_opportunity(db, opp_id, current_user)
    stage = await _get_stage_in_branch(db, body.stage_id, opp.branch_id, opp.tenant_id)

    # Mover a etapa "perdido" requiere motivo → el front abre el modal
    if stage.is_lost:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"requires_reason": True, "message": "Esta etapa requiere un motivo de pérdida"},
        )

    await _move_stage(db, opp, stage, current_user.id)

    if stage.is_won:
        opp.status = "won"
        opp.probability = 100
        opp.won_at = datetime.now(timezone.utc)
        await _add_activity(
            db, opp.id, opp.tenant_id, "won",
            f'Oportunidad ganada en etapa "{stage.name}"',
            created_by=current_user.id,
        )

    await db.commit()
    await db.refresh(opp)

    assignee_name: str | None = None
    if opp.assigned_to:
        assignee = await db.get(User, opp.assigned_to)
        assignee_name = assignee.name if assignee else None
    return _opp_read(opp, stage=stage, assigned_to_name=assignee_name)


# ── POST /{id}/lost ────────────────────────────────────────────────────────────

@router.post("/{opp_id}/lost", response_model=OppRead)
async def mark_lost(
    opp_id: uuid.UUID,
    body: OppMarkLostBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OppRead:
    opp = await _get_opportunity(db, opp_id, current_user)
    now = datetime.now(timezone.utc)

    # Find the lost stage in the branch
    lost_stage_result = await db.execute(
        select(PipelineStage).where(
            PipelineStage.branch_id == opp.branch_id,
            PipelineStage.tenant_id == opp.tenant_id,
            PipelineStage.is_lost.is_(True),
            PipelineStage.is_active.is_(True),
        ).limit(1)
    )
    lost_stage = lost_stage_result.scalar_one_or_none()

    opp.status = "lost"
    opp.lost_at = now
    opp.lost_reason = body.lost_reason
    opp.last_activity_at = now

    if lost_stage:
        await _move_stage(db, opp, lost_stage, current_user.id)
    elif opp.stage_id:
        # No lost stage configured but opp has a stage — record history in-place
        db.add(OpportunityStageHistory(
            opportunity_id=opp.id,
            tenant_id=opp.tenant_id,
            from_stage_id=opp.stage_id,
            to_stage_id=opp.stage_id,
            changed_by=current_user.id,
        ))

    reason_str = body.lost_reason or body.reason_code or "Sin motivo"
    await _add_activity(
        db, opp.id, opp.tenant_id, "lost",
        f"Oportunidad perdida. Motivo: {reason_str}",
        created_by=current_user.id,
    )

    await db.commit()
    await db.refresh(opp)

    return _opp_read(opp, stage=lost_stage)


# ── POST /{id}/won ─────────────────────────────────────────────────────────────

@router.post("/{opp_id}/won", response_model=OppRead)
async def mark_won(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OppRead:
    opp = await _get_opportunity(db, opp_id, current_user)
    now = datetime.now(timezone.utc)

    won_stage_result = await db.execute(
        select(PipelineStage).where(
            PipelineStage.branch_id == opp.branch_id,
            PipelineStage.tenant_id == opp.tenant_id,
            PipelineStage.is_won.is_(True),
            PipelineStage.is_active.is_(True),
        ).limit(1)
    )
    won_stage = won_stage_result.scalar_one_or_none()

    opp.status = "won"
    opp.probability = 100
    opp.won_at = now
    opp.last_activity_at = now

    if won_stage:
        await _move_stage(db, opp, won_stage, current_user.id)

    await _add_activity(
        db, opp.id, opp.tenant_id, "won",
        "Oportunidad marcada como ganada",
        created_by=current_user.id,
    )

    await db.commit()
    await db.refresh(opp)

    return _opp_read(opp, stage=won_stage)


# ── POST /bulk/stage ───────────────────────────────────────────────────────────

@router.post("/bulk/stage", response_model=list[OppRead])
async def bulk_move_stage(
    body: BulkStageBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OppRead]:
    if not body.ids:
        return []

    results: list[OppRead] = []
    for opp_id in body.ids:
        try:
            opp = await _get_opportunity(db, opp_id, current_user)
        except HTTPException:
            continue

        stage = await _get_stage_in_branch(db, body.stage_id, opp.branch_id, opp.tenant_id)

        if stage.is_lost:
            # Skip lost stages in bulk — caller should use POST /{id}/lost individually
            continue

        await _move_stage(db, opp, stage, current_user.id)

        if stage.is_won:
            opp.status = "won"
            opp.probability = 100
            opp.won_at = datetime.now(timezone.utc)

        results.append(_opp_read(opp, stage=stage))

    await db.commit()
    return results


# ── POST /bulk/delete ──────────────────────────────────────────────────────────

@router.post("/bulk/delete", response_model=dict)
async def bulk_delete(
    body: BulkDeleteBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.ids:
        return {"deleted": 0}

    now = datetime.now(timezone.utc)
    deleted = 0
    for opp_id in body.ids:
        try:
            opp = await _get_opportunity(db, opp_id, current_user)
        except HTTPException:
            continue
        opp.deleted_at = now
        deleted += 1

    await db.commit()
    return {"deleted": deleted}


# ── DELETE /{id} ───────────────────────────────────────────────────────────────

@router.delete("/{opp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    opp = await _get_opportunity(db, opp_id, current_user)
    opp.deleted_at = datetime.now(timezone.utc)
    await db.commit()
