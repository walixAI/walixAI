from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.saved_view import SavedView
from app.models.tenant import Tenant, TenantPlan
from app.models.user import User
from app.schemas.saved_view import SavedViewCreate, SavedViewRow, SavedViewUpdate

router = APIRouter(prefix="/v1/contacts/views", tags=["saved-views"])

_VIEW_LIMITS: dict[TenantPlan, int] = {
    TenantPlan.STARTER: 10,
    TenantPlan.GROWTH: 10,
    TenantPlan.BUSINESS: 25,
    TenantPlan.ENTERPRISE: 25,
}
_DEFAULT_LIMIT = 10


async def _get_view_or_404(
    db: AsyncSession, view_id: uuid.UUID, user_id: uuid.UUID
) -> SavedView:
    view = await db.get(SavedView, view_id)
    if view is None or view.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vista no encontrada")
    return view


async def _clear_defaults(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(SavedView)
        .where(SavedView.user_id == user_id, SavedView.is_default.is_(True))
        .values(is_default=False)
    )


# ── GET / — list user's saved views ──────────────────────────────────────────

@router.get("", response_model=list[SavedViewRow])
async def list_views(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SavedViewRow]:
    rows = (
        await db.execute(
            select(SavedView)
            .where(
                SavedView.user_id == current_user.id,
                SavedView.tenant_id == current_user.tenant_id,
            )
            .order_by(SavedView.is_default.desc(), SavedView.created_at.asc())
        )
    ).scalars().all()
    return [SavedViewRow.model_validate(r) for r in rows]


# ── POST / — create saved view ────────────────────────────────────────────────

@router.post("", response_model=SavedViewRow, status_code=status.HTTP_201_CREATED)
async def create_view(
    body: SavedViewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedViewRow:
    tenant = await db.get(Tenant, current_user.tenant_id)
    limit = _VIEW_LIMITS.get(tenant.plan, _DEFAULT_LIMIT) if tenant else _DEFAULT_LIMIT

    count = (
        await db.execute(
            select(func.count(SavedView.id)).where(SavedView.user_id == current_user.id)
        )
    ).scalar_one()

    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Límite de vistas alcanzado. Elimina una vista existente para continuar.",
        )

    if body.is_default:
        await _clear_defaults(db, current_user.id)

    view = SavedView(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        name=body.name,
        filters=body.filters,
        view_mode=body.view_mode,
        is_default=body.is_default,
    )
    db.add(view)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes una vista con ese nombre",
        )
    await db.refresh(view)
    return SavedViewRow.model_validate(view)


# ── PATCH /{view_id} — partial update ────────────────────────────────────────

@router.patch("/{view_id}", response_model=SavedViewRow)
async def update_view(
    view_id: uuid.UUID,
    body: SavedViewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedViewRow:
    view = await _get_view_or_404(db, view_id, current_user.id)

    updates = body.model_dump(exclude_unset=True)

    if updates.get("is_default") is True:
        await _clear_defaults(db, current_user.id)

    for field, value in updates.items():
        setattr(view, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes una vista con ese nombre",
        )
    await db.refresh(view)
    return SavedViewRow.model_validate(view)


# ── DELETE /{view_id} ─────────────────────────────────────────────────────────

@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    view_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    view = await _get_view_or_404(db, view_id, current_user.id)
    was_default = view.is_default

    await db.delete(view)
    await db.flush()

    if was_default:
        next_view = (
            await db.execute(
                select(SavedView)
                .where(SavedView.user_id == current_user.id)
                .order_by(SavedView.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if next_view:
            next_view.is_default = True

    await db.commit()


# ── POST /{view_id}/set-default — shortcut ────────────────────────────────────

@router.post("/{view_id}/set-default", response_model=SavedViewRow)
async def set_default_view(
    view_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedViewRow:
    view = await _get_view_or_404(db, view_id, current_user.id)

    await _clear_defaults(db, current_user.id)
    view.is_default = True

    await db.commit()
    await db.refresh(view)
    return SavedViewRow.model_validate(view)
