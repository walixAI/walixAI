"""Tasks API — /api/tasks/today, /api/tasks, /api/tasks/{id}

/today  → dashboard rápido (TaskTodayResponse con totals)
/       → lista general filtrable (view, mine_only, lead_id)
/{id}   → DELETE hard-delete de tarea
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.activity import Activity
from app.models.deal import Deal
from app.models.lead import Lead
from app.models.user import User

from zoneinfo import ZoneInfo

router = APIRouter(prefix="/tasks", tags=["tasks"])

_MX = ZoneInfo("America/Mexico_City")

TASK_KINDS = (
    "cobro", "cotizacion", "servicio", "seguimiento",
    "queja", "refaccion", "facturacion", "devolucion", "otro",
)

# ── Schemas ────────────────────────────────────────────────────────────────────

class TaskTodayItem(BaseModel):
    id: uuid.UUID
    title: str | None
    task_kind: str | None
    due_date: datetime | None
    overdue: bool
    lead_id: uuid.UUID
    lead_name: str | None
    deal_id: uuid.UUID | None
    deal_title: str | None
    deal_amount: float | None


class TaskTodayTotals(BaseModel):
    total: int
    overdue: int
    by_kind: dict[str, int]
    collect_amount: float


class TaskTodayResponse(BaseModel):
    items: list[TaskTodayItem]
    totals: TaskTodayTotals


class TaskGeneralItem(BaseModel):
    id: uuid.UUID
    title: str | None
    task_kind: str | None
    due_date: datetime | None
    overdue: bool
    completed_at: datetime | None
    lead_id: uuid.UUID
    lead_name: str | None
    deal_id: uuid.UUID | None
    deal_title: str | None
    deal_amount: float | None
    assignee_id: uuid.UUID | None
    assignee_name: str | None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mx_end_of_today() -> tuple[datetime, datetime]:
    """Return (end_of_today_utc, now_utc)."""
    now_mx = datetime.now(_MX)
    end_mx = datetime.combine(now_mx.date(), time.max, tzinfo=_MX)
    return end_mx.astimezone(timezone.utc), datetime.now(timezone.utc)


def _is_overdue(due: datetime | None, completed_at: datetime | None, now_utc: datetime) -> bool:
    if completed_at is not None or due is None:
        return False
    aware = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
    return aware < now_utc


# ── GET /api/tasks/today ───────────────────────────────────────────────────────

@router.get("/today", response_model=TaskTodayResponse)
async def get_tasks_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskTodayResponse:
    end_of_today_utc, now_utc = _mx_end_of_today()

    rows = (
        await db.execute(
            select(Activity, Lead.name, Lead.last_name, Deal.title, Deal.amount)
            .join(Lead, Activity.lead_id == Lead.id)
            .outerjoin(Deal, Activity.deal_id == Deal.id)
            .where(
                Activity.tenant_id == current_user.tenant_id,
                Activity.activity_type == "task",
                Activity.completed_at.is_(None),
                Activity.due_date <= end_of_today_utc,
                or_(
                    Activity.assignee_id == current_user.id,
                    and_(
                        Activity.assignee_id.is_(None),
                        Activity.created_by == current_user.id,
                    ),
                ),
            )
            .order_by(Activity.due_date.asc())
        )
    ).fetchall()

    items: list[TaskTodayItem] = []
    for activity, lead_name, lead_last_name, deal_title, deal_amount in rows:
        full_name = " ".join(filter(None, [lead_name, lead_last_name])) or None
        items.append(TaskTodayItem(
            id=activity.id,
            title=activity.title,
            task_kind=activity.task_kind,
            due_date=activity.due_date,
            overdue=_is_overdue(activity.due_date, activity.completed_at, now_utc),
            lead_id=activity.lead_id,
            lead_name=full_name,
            deal_id=activity.deal_id,
            deal_title=deal_title,
            deal_amount=float(deal_amount) if deal_amount is not None else None,
        ))

    total = len(items)
    overdue_count = sum(1 for t in items if t.overdue)
    by_kind: dict[str, int] = {k: 0 for k in TASK_KINDS}
    for t in items:
        if t.task_kind in by_kind:
            by_kind[t.task_kind] += 1
    collect_amount = sum(
        t.deal_amount for t in items
        if t.task_kind == "cobro" and t.deal_amount is not None
    )

    return TaskTodayResponse(
        items=items,
        totals=TaskTodayTotals(
            total=total,
            overdue=overdue_count,
            by_kind=by_kind,
            collect_amount=collect_amount,
        ),
    )


# ── GET /api/tasks ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[TaskGeneralItem])
async def get_tasks(
    view: Literal["today", "upcoming", "overdue", "completed", "all"] = Query(default="today"),
    mine_only: bool = Query(default=True),
    lead_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TaskGeneralItem]:
    end_of_today_utc, now_utc = _mx_end_of_today()

    AssigneeAlias = aliased(User)

    stmt = (
        select(Activity, Lead.name, Lead.last_name, Deal.title, Deal.amount, AssigneeAlias.name)
        .join(Lead, Activity.lead_id == Lead.id)
        .outerjoin(Deal, Activity.deal_id == Deal.id)
        .outerjoin(AssigneeAlias, Activity.assignee_id == AssigneeAlias.id)
        .where(
            Activity.tenant_id == current_user.tenant_id,
            Activity.activity_type == "task",
        )
    )

    if view == "today":
        stmt = stmt.where(Activity.completed_at.is_(None), Activity.due_date <= end_of_today_utc)
    elif view == "upcoming":
        stmt = stmt.where(Activity.completed_at.is_(None), Activity.due_date > end_of_today_utc)
    elif view == "overdue":
        stmt = stmt.where(Activity.completed_at.is_(None), Activity.due_date < now_utc)
    elif view == "completed":
        stmt = stmt.where(Activity.completed_at.isnot(None))
    # "all" → no extra filter

    if mine_only:
        stmt = stmt.where(
            or_(
                Activity.assignee_id == current_user.id,
                and_(Activity.assignee_id.is_(None), Activity.created_by == current_user.id),
            )
        )

    if lead_id is not None:
        stmt = stmt.where(Activity.lead_id == lead_id)

    stmt = stmt.order_by(Activity.due_date.asc())

    rows = (await db.execute(stmt)).fetchall()
    items: list[TaskGeneralItem] = []
    for activity, lead_name, lead_last_name, deal_title, deal_amount, assignee_name in rows:
        full_name = " ".join(filter(None, [lead_name, lead_last_name])) or None
        items.append(TaskGeneralItem(
            id=activity.id,
            title=activity.title,
            task_kind=activity.task_kind,
            due_date=activity.due_date,
            overdue=_is_overdue(activity.due_date, activity.completed_at, now_utc),
            completed_at=activity.completed_at,
            lead_id=activity.lead_id,
            lead_name=full_name,
            deal_id=activity.deal_id,
            deal_title=deal_title,
            deal_amount=float(deal_amount) if deal_amount is not None else None,
            assignee_id=activity.assignee_id,
            assignee_name=assignee_name,
        ))

    return items


# ── DELETE /api/tasks/{activity_id} ───────────────────────────────────────────

@router.delete("/{activity_id}", status_code=204)
async def delete_task(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    activity = await db.get(Activity, activity_id)
    if (
        activity is None
        or activity.tenant_id != current_user.tenant_id
        or activity.activity_type != "task"
    ):
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    if activity.created_by != current_user.id and activity.assignee_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Solo el creador o el asignado puede eliminar esta tarea",
        )

    await db.delete(activity)
    await db.commit()
