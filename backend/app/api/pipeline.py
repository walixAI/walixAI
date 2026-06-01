"""Pipeline board endpoint for Walix.

GET /api/pipeline/board — returns all active stages with their leads for the kanban view.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.lead import Lead, LeadSentiment, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.user import User, UserRole

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
