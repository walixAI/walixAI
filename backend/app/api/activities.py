from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.activity import Activity
from app.models.lead import Lead
from app.models.user import User
from app.schemas.activity import ActivityCreate, ActivityRow

# Nested under the contacts path — FastAPI resolves {lead_id} from the prefix
router = APIRouter(prefix="/v1/contacts/{lead_id}/activities", tags=["activities"])

PAGE_SIZE = 20


# ── Extended row that carries the creator's display name ─────────────────────

class ActivityRowOut(ActivityRow):
    created_by_name: str | None = None


class ActivityUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None
    extra_data: dict | None = None
    # ── Etapa 5 task extensions ──────────────────────────────────────────────
    task_kind: str | None = None
    assignee_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    closed_via: str | None = None
    closed_note: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_lead_or_404(
    db: AsyncSession, lead_id: uuid.UUID, tenant_id: uuid.UUID
) -> Lead:
    lead = (
        await db.execute(
            select(Lead).where(
                Lead.id == lead_id,
                Lead.tenant_id == tenant_id,
                Lead.deleted_at.is_(None),
            )
        )
    ).scalars().first()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    return lead


async def _enrich_with_name(
    activity: Activity, db: AsyncSession
) -> ActivityRowOut:
    name: str | None = None
    if activity.created_by:
        user = await db.get(User, activity.created_by)
        name = user.name if user else None
    return ActivityRowOut(**ActivityRow.model_validate(activity).model_dump(), created_by_name=name)


# ── 1. GET — paginated list ───────────────────────────────────────────────────

@router.get("", response_model=dict)
async def list_activities(
    lead_id: uuid.UUID,
    type_filter: list[str] = Query(default=[], alias="type"),
    page: int = Query(default=1, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_lead_or_404(db, lead_id, current_user.tenant_id)

    base = select(Activity).where(Activity.lead_id == lead_id)
    if type_filter:
        base = base.where(Activity.activity_type.in_(type_filter))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    activities = (
        await db.execute(
            base.order_by(Activity.created_at.desc())
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
    ).scalars().all()

    # Batch-load creator names
    user_ids = {a.created_by for a in activities if a.created_by}
    user_map: dict[uuid.UUID, str] = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            user_map[u.id] = u.name or ""

    items = [
        ActivityRowOut(
            **ActivityRow.model_validate(a).model_dump(),
            created_by_name=user_map.get(a.created_by) if a.created_by else None,
        )
        for a in activities
    ]

    return {"items": items, "total": total, "page": page}


# ── 2. POST — create activity ─────────────────────────────────────────────────

@router.post("", response_model=ActivityRowOut, status_code=status.HTTP_201_CREATED)
async def create_activity(
    lead_id: uuid.UUID,
    body: ActivityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityRowOut:
    if body.activity_type == "system":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El tipo 'system' está reservado para el sistema",
        )

    lead = await _get_lead_or_404(db, lead_id, current_user.tenant_id)

    activity = Activity(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        activity_type=body.activity_type,
        title=body.title,
        body=body.body,
        extra_data=body.extra_data,
        due_date=body.due_date,
        completed_at=body.completed_at,
        created_by=current_user.id,
        task_kind=body.task_kind,
        assignee_id=body.assignee_id,
        deal_id=body.deal_id,
        closed_via=body.closed_via,
        closed_note=body.closed_note,
    )
    db.add(activity)
    await db.flush()

    # Update lead's last activity summary (also bumps updated_at via onupdate)
    summary = body.title or body.body or body.activity_type
    lead.last_activity_summary = summary[:255]

    await db.commit()
    await db.refresh(activity)

    return ActivityRowOut(
        **ActivityRow.model_validate(activity).model_dump(),
        created_by_name=current_user.name,
    )


# ── 3. PATCH — edit activity ──────────────────────────────────────────────────

@router.patch("/{activity_id}", response_model=ActivityRowOut)
async def update_activity(
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    body: ActivityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityRowOut:
    await _get_lead_or_404(db, lead_id, current_user.tenant_id)

    activity = await db.get(Activity, activity_id)
    if (
        activity is None
        or activity.lead_id != lead_id
        or activity.tenant_id != current_user.tenant_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actividad no encontrada")

    if activity.activity_type == "system":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Las actividades del sistema son inmutables",
        )

    if activity.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el creador puede editar esta actividad",
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(activity, field, value)

    await db.commit()
    await db.refresh(activity)

    return await _enrich_with_name(activity, db)
