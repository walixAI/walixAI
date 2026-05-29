import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

MX_TZ = ZoneInfo("America/Mexico_City")

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.conversation import (
    Conversation,
    ConversationHandler,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.user import User  # noqa: F401  (also used by get_current_user)

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadListItem(BaseModel):
    id: uuid.UUID
    wa_phone: str
    name: str | None
    status: LeadStatus
    sentiment: LeadSentiment
    source: LeadSource
    assigned_to: uuid.UUID | None
    contact_phone: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadListResponse(BaseModel):
    items: list[LeadListItem]
    total: int
    limit: int
    offset: int


class LeadDetail(LeadListItem):
    branch_id: uuid.UUID
    tenant_id: uuid.UUID
    qualification_data: dict[str, Any]
    qualification_score: float | None = None
    assigned_to_name: str | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    tokens_used: int | None
    latency_ms: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationOut(BaseModel):
    conversation_id: uuid.UUID | None
    status: ConversationStatus | None
    handled_by: ConversationHandler | None
    messages: list[MessageOut]


class LeadStatusUpdate(BaseModel):
    status: LeadStatus
    note: str | None = None


def _require_branch(user: User) -> uuid.UUID:
    if user.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no branch assigned",
        )
    return user.branch_id


async def _get_lead_in_branch(
    db: AsyncSession, lead_id: uuid.UUID, branch_id: uuid.UUID
) -> Lead:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.get("", response_model=LeadListResponse)
async def list_leads(
    status_filter: LeadStatus | None = Query(default=None, alias="status"),
    on_date: date | None = Query(default=None, alias="date"),
    all_dates: bool = Query(default=False, alias="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadListResponse:
    branch_id = _require_branch(current_user)

    base = select(Lead).where(Lead.branch_id == branch_id)

    if not all_dates:
        target_date = on_date or datetime.now(MX_TZ).date()
        start = datetime.combine(target_date, time.min, tzinfo=MX_TZ)
        end = start + timedelta(days=1)
        base = base.where(Lead.created_at >= start, Lead.created_at < end)

    if status_filter is not None:
        base = base.where(Lead.status == status_filter)

    total_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = total_result.scalar_one()

    rows = await db.execute(
        base.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    )
    items = [LeadListItem.model_validate(lead) for lead in rows.scalars().all()]

    return LeadListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadDetail:
    branch_id = _require_branch(current_user)
    lead = await _get_lead_in_branch(db, lead_id, branch_id)
    detail = LeadDetail.model_validate(lead)
    if lead.assigned_to:
        assignee = await db.get(User, lead.assigned_to)
        detail.assigned_to_name = assignee.name if assignee else None
    return detail


@router.get("/{lead_id}/conversation", response_model=ConversationOut)
async def get_lead_conversation(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    branch_id = _require_branch(current_user)
    await _get_lead_in_branch(db, lead_id, branch_id)

    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead_id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.started_at.desc())
    )
    conversation = conv_result.scalars().first()
    if conversation is None:
        return ConversationOut(
            conversation_id=None, status=None, handled_by=None, messages=[]
        )

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    messages = [MessageOut.model_validate(m) for m in msg_result.scalars().all()]
    return ConversationOut(
        conversation_id=conversation.id,
        status=conversation.status,
        handled_by=conversation.handled_by,
        messages=messages,
    )


@router.put("/{lead_id}/status", response_model=LeadDetail)
async def update_lead_status(
    lead_id: uuid.UUID,
    body: LeadStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadDetail:
    branch_id = _require_branch(current_user)
    lead = await _get_lead_in_branch(db, lead_id, branch_id)

    previous = lead.status
    history_entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "from_status": previous.value,
        "to_status": body.status.value,
        "note": body.note,
        "by_user_id": str(current_user.id),
    }
    # JSONB columns aren't mutation-tracked by default — reassign so SQLAlchemy
    # emits an UPDATE.
    existing = dict(lead.qualification_data or {})
    existing["status_history"] = [
        *existing.get("status_history", []),
        history_entry,
    ]
    lead.qualification_data = existing
    lead.status = body.status

    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)


@router.post("/{lead_id}/return-to-bot", response_model=LeadDetail)
async def return_to_bot(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadDetail:
    branch_id = _require_branch(current_user)
    lead = await _get_lead_in_branch(db, lead_id, branch_id)

    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead.id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.started_at.desc())
    )
    conversation = conv_result.scalars().first()
    if conversation is not None:
        conversation.handled_by = ConversationHandler.BOT
        conversation.status = ConversationStatus.ACTIVE

    lead.status = LeadStatus.EN_CALIFICACION

    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)


@router.post("/{lead_id}/handoff", response_model=LeadDetail)
async def handoff_lead(
    lead_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadDetail:
    branch_id = _require_branch(current_user)
    lead = await _get_lead_in_branch(db, lead_id, branch_id)

    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead.id,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.started_at.desc())
    )
    conversation = conv_result.scalars().first()
    if conversation is not None:
        conversation.handled_by = ConversationHandler.HUMAN
        conversation.status = ConversationStatus.HANDOFF

    lead.status = LeadStatus.ESCALADO

    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)
