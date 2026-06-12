from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.tag import Tag
from app.models.user import User
from app.schemas.contact import TagRow

router = APIRouter(prefix="/v1/tags", tags=["tags"])

_PRESET_COLORS = ["#7C3AED", "#0891B2", "#059669", "#D97706", "#DC2626", "#DB2777"]


class TagCreate(BaseModel):
    name: str
    color: str | None = None


# ── GET / — list tags for the authenticated tenant ────────────────────────────

@router.get("", response_model=list[TagRow])
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TagRow]:
    rows = (
        await db.execute(
            select(Tag)
            .where(Tag.tenant_id == current_user.tenant_id)
            .order_by(Tag.name)
        )
    ).scalars().all()
    return [TagRow.model_validate(t) for t in rows]


# ── POST / — create tag with round-robin color auto-assignment ────────────────

@router.post("", response_model=TagRow, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagRow:
    color = body.color
    if not color:
        count = (
            await db.execute(
                select(func.count(Tag.id)).where(Tag.tenant_id == current_user.tenant_id)
            )
        ).scalar_one()
        color = _PRESET_COLORS[count % len(_PRESET_COLORS)]

    tag = Tag(
        tenant_id=current_user.tenant_id,
        name=body.name.strip(),
        color=color,
    )
    db.add(tag)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un tag con el nombre '{body.name}' en tu cuenta",
        )
    await db.refresh(tag)
    return TagRow.model_validate(tag)
