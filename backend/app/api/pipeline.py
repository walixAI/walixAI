"""Pipeline board endpoint for Walix.

GET /api/pipeline/board — returns all active stages with their leads for the kanban view.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.activity import LeadActivity
from app.models.deal import Deal
from app.models.lead import Lead, LeadSentiment, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline, resolve_default_pipeline_id
from app.models.user import User, UserRole

# ── Pydantic schema para listado de usuarios del tenant ───────────────────────


class TenantUserItem(BaseModel):
    id: uuid.UUID
    name: str
    email: str

    model_config = ConfigDict(from_attributes=True)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_MULTI_BRANCH_ROLES = (UserRole.OWNER, UserRole.IT)

# ── Pydantic schemas ───────────────────────────────────────────────────────────


class LeadBoardCard(BaseModel):
    id: uuid.UUID
    name: str | None
    wa_phone: str
    status: LeadStatus
    sentiment: LeadSentiment
    risk_score: float | None
    assigned_to: uuid.UUID | None
    assigned_to_name: str | None
    days_in_stage: int
    qualification_score: float | None
    current_score: int | None = None
    current_score_trend: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PipelineStageBoard(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    color: str | None
    order_index: int
    is_won: bool
    is_lost: bool
    leads: list[LeadBoardCard]
    total: int


class BoardResponse(BaseModel):
    stages: list[PipelineStageBoard]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _days_since(dt: datetime | None) -> int:
    if dt is None:
        return 0
    now = datetime.now(timezone.utc)
    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return max(0, (now - aware).days)


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.get("/board", response_model=BoardResponse)
async def get_pipeline_board(
    branch_id: uuid.UUID | None = Query(default=None),
    limit_per_stage: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BoardResponse:
    """Returns all active pipeline stages with their leads for the kanban board."""

    # Resolve branch
    resolved_branch_id: uuid.UUID | None = branch_id or current_user.branch_id
    if resolved_branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="branch_id is required for users without an assigned branch",
        )

    # Access control: non-owner/IT users can only see their own branch
    if current_user.role not in _MULTI_BRANCH_ROLES:
        if current_user.branch_id != resolved_branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this branch",
            )

    # 1. Load active stages ordered by index
    stages_result = await db.execute(
        select(PipelineStage)
        .where(
            PipelineStage.branch_id == resolved_branch_id,
            PipelineStage.is_active.is_(True),
        )
        .order_by(PipelineStage.order_index)
    )
    stages = stages_result.scalars().all()
    if not stages:
        return BoardResponse(stages=[])

    stage_ids = [s.id for s in stages]
    lost_stage_ids = {s.id for s in stages if s.is_lost}

    # 2. Load all board leads in one query:
    #    - Leads in any active stage of this branch
    #    - For non-lost stages: exclude "perdido" status
    #    - For lost stages:     include only "perdido" status
    #    We load all relevant leads and group in Python.
    leads_result = await db.execute(
        select(Lead).where(
            Lead.branch_id == resolved_branch_id,
            Lead.pipeline_stage_id.in_(stage_ids),
        )
    )
    all_leads: list[Lead] = leads_result.scalars().all()

    # 3. Batch-load assignee names
    assignee_ids = {lead.assigned_to for lead in all_leads if lead.assigned_to}
    assignee_names: dict[uuid.UUID, str] = {}
    if assignee_ids:
        users_result = await db.execute(
            select(User.id, User.name).where(User.id.in_(assignee_ids))
        )
        assignee_names = {row.id: row.name for row in users_result.fetchall()}

    # 4. Group leads per stage with visibility rules
    leads_by_stage: dict[uuid.UUID, list[Lead]] = {s.id: [] for s in stages}
    for lead in all_leads:
        sid = lead.pipeline_stage_id
        if sid not in leads_by_stage:
            continue
        is_lost_stage = sid in lost_stage_ids
        lead_is_perdido = (
            lead.status == LeadStatus.PERDIDO
            or (isinstance(lead.status, str) and lead.status == "perdido")
        )
        # Lost stages show only "perdido" leads; other stages exclude them
        if is_lost_stage and not lead_is_perdido:
            continue
        if not is_lost_stage and lead_is_perdido:
            continue
        leads_by_stage[sid].append(lead)

    # 5. Build response — apply limit_per_stage
    board_stages: list[PipelineStageBoard] = []
    for stage in stages:
        stage_leads = leads_by_stage[stage.id]
        total = len(stage_leads)
        cards = [
            LeadBoardCard(
                id=lead.id,
                name=lead.name,
                wa_phone=lead.wa_phone,
                status=lead.status,
                sentiment=lead.sentiment,
                risk_score=lead.risk_score,
                assigned_to=lead.assigned_to,
                assigned_to_name=assignee_names.get(lead.assigned_to) if lead.assigned_to else None,
                days_in_stage=_days_since(lead.updated_at),
                qualification_score=lead.qualification_score,
                current_score=lead.current_score,
                current_score_trend=lead.current_score_trend,
            )
            for lead in stage_leads[:limit_per_stage]
        ]
        board_stages.append(
            PipelineStageBoard(
                id=stage.id,
                name=stage.name,
                slug=stage.slug,
                color=stage.color,
                order_index=stage.order_index,
                is_won=stage.is_won,
                is_lost=stage.is_lost,
                leads=cards,
                total=total,
            )
        )

    return BoardResponse(stages=board_stages)


# ── Sprint 14A — Deal-based pipeline endpoints ────────────────────────────────


class StageRead(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    is_won: bool
    is_lost: bool
    order_index: int
    default_probability: int
    pipeline_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class DealKanbanItem(BaseModel):
    id: uuid.UUID
    title: str
    amount: Decimal
    probability: int
    pipeline_stage_id: uuid.UUID
    stage_name: str
    lead_id: uuid.UUID
    owner_id: uuid.UUID | None
    source: str | None
    notes: str | None
    expected_close_date: datetime | None
    is_won: bool
    is_lost: bool
    lost_reason: str | None
    lost_comment: str | None
    created_at: datetime
    updated_at: datetime
    contact_last_activity_at: datetime | None


@router.get("/stages", response_model=list[StageRead])
async def get_pipeline_stages(
    pipeline_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if pipeline_id is not None:
        p = await db.get(Pipeline, pipeline_id)
        if p is None or p.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=404, detail="Pipeline no encontrado")
        resolved_id = pipeline_id
    else:
        resolved_id = await resolve_default_pipeline_id(
            current_user.tenant_id, db, user_branch_id=current_user.branch_id
        )

    if resolved_id is None:
        return []

    stages = (
        await db.execute(
            select(PipelineStage)
            .where(
                PipelineStage.tenant_id == current_user.tenant_id,
                PipelineStage.pipeline_id == resolved_id,
                PipelineStage.is_archived.is_(False),
            )
            .order_by(PipelineStage.order_index)
        )
    ).scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "color": s.color,
            "is_won": s.is_won,
            "is_lost": s.is_lost,
            "order_index": s.order_index,
            "default_probability": s.probability_default,
            "pipeline_id": s.pipeline_id,
        }
        for s in stages
    ]


@router.get("/deals", response_model=list[DealKanbanItem])
async def get_pipeline_deals(
    pipeline_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DealKanbanItem]:
    if pipeline_id is not None:
        p = await db.get(Pipeline, pipeline_id)
        if p is None or p.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=404, detail="Pipeline no encontrado")
        resolved_id = pipeline_id
    else:
        resolved_id = await resolve_default_pipeline_id(
            current_user.tenant_id, db, user_branch_id=current_user.branch_id
        )

    if resolved_id is None:
        return []

    # Subquery: MAX(created_at) de lead_activities por lead_id
    last_activity_sq = (
        select(
            LeadActivity.lead_id,
            func.max(LeadActivity.created_at).label("last_at"),
        )
        .where(LeadActivity.tenant_id == current_user.tenant_id)
        .group_by(LeadActivity.lead_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(
                Deal,
                PipelineStage.name.label("stage_name"),
                last_activity_sq.c.last_at.label("contact_last_activity_at"),
            )
            .join(PipelineStage, Deal.pipeline_stage_id == PipelineStage.id)
            .outerjoin(last_activity_sq, Deal.lead_id == last_activity_sq.c.lead_id)
            .where(
                Deal.tenant_id == current_user.tenant_id,
                PipelineStage.pipeline_id == resolved_id,
            )
            .order_by(Deal.updated_at.desc())
        )
    ).fetchall()

    result: list[DealKanbanItem] = []
    for deal, stage_name, last_at in rows:
        result.append(DealKanbanItem(
            id=deal.id,
            title=deal.title,
            amount=deal.amount,
            probability=deal.probability,
            pipeline_stage_id=deal.pipeline_stage_id,
            stage_name=stage_name,
            lead_id=deal.lead_id,
            owner_id=deal.owner_id,
            source=deal.source,
            notes=deal.notes,
            expected_close_date=deal.expected_close_date,
            is_won=deal.is_won,
            is_lost=deal.is_lost,
            lost_reason=deal.lost_reason,
            lost_comment=deal.lost_comment,
            created_at=deal.created_at,
            updated_at=deal.updated_at,
            contact_last_activity_at=last_at,
        ))
    return result


@router.get("/users", response_model=list[TenantUserItem])
async def get_pipeline_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    """Usuarios activos del tenant para el selector de owner y filtro de vendedor."""
    users = (
        await db.execute(
            select(User)
            .where(
                User.tenant_id == current_user.tenant_id,
                User.is_active.is_(True),
            )
            .order_by(User.name)
        )
    ).scalars().all()
    return list(users)
