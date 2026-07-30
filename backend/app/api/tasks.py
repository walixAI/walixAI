"""GET /api/tasks/today — tareas del usuario para hoy (vencidas + vencen hoy).

Scope: activity_type='task', completed_at IS NULL, due_date <= fin del día MX.
Incluye tareas donde assignee_id == current_user.id, o (assignee_id IS NULL
AND created_by == current_user.id) como fallback para tareas sin asignar.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.activity import Activity
from app.models.deal import Deal
from app.models.lead import Lead
from app.models.user import User

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


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.get("/today", response_model=TaskTodayResponse)
async def get_tasks_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskTodayResponse:
    # End of today in MX time → UTC for comparison with stored timestamps
    now_mx = datetime.now(_MX)
    end_of_today_mx = datetime.combine(now_mx.date(), time.max, tzinfo=_MX)
    end_of_today_utc = end_of_today_mx.astimezone(timezone.utc)

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

    now_utc = datetime.now(timezone.utc)

    items: list[TaskTodayItem] = []
    for activity, lead_name, lead_last_name, deal_title, deal_amount in rows:
        due = activity.due_date
        overdue = due is not None and due.replace(tzinfo=timezone.utc if due.tzinfo is None else due.tzinfo) < now_utc

        full_lead_name = " ".join(filter(None, [lead_name, lead_last_name])) or None

        items.append(TaskTodayItem(
            id=activity.id,
            title=activity.title,
            task_kind=activity.task_kind,
            due_date=activity.due_date,
            overdue=overdue,
            lead_id=activity.lead_id,
            lead_name=full_lead_name,
            deal_id=activity.deal_id,
            deal_title=deal_title,
            deal_amount=float(deal_amount) if deal_amount is not None else None,
        ))

    # ── Totals ─────────────────────────────────────────────────────────────────
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
