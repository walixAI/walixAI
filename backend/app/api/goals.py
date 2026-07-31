from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.finance import _require_finance_access, _require_owner
from app.core.database import get_db
from app.models.goals import ProductCategory
from app.models.user import User

router = APIRouter(prefix="/goals", tags=["goals"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProductCategoryOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    is_active: bool
    position: int
    model_config = {"from_attributes": True}


class ProductCategoryCreate(BaseModel):
    name: str
    position: int = 0


class ProductCategoryUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    position: int | None = None


# ── Product categories endpoints ──────────────────────────────────────────────

@router.get("/product-categories", response_model=list[ProductCategoryOut])
async def list_product_categories(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProductCategoryOut]:
    await _require_finance_access(current_user, branch_id=None, db=db)
    q = select(ProductCategory).where(ProductCategory.tenant_id == current_user.tenant_id)
    if not include_inactive:
        q = q.where(ProductCategory.is_active.is_(True))
    q = q.order_by(ProductCategory.position, ProductCategory.name)
    rows = (await db.execute(q)).scalars().all()
    return [ProductCategoryOut.model_validate(r) for r in rows]


@router.post("/product-categories", response_model=ProductCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_product_category(
    body: ProductCategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductCategoryOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    cat = ProductCategory(
        tenant_id=current_user.tenant_id,
        name=body.name.strip(),
        position=body.position,
    )
    db.add(cat)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una categoría de producto con el nombre '{body.name}' en tu cuenta",
        )
    await db.refresh(cat)
    return ProductCategoryOut.model_validate(cat)


@router.patch("/product-categories/{category_id}", response_model=ProductCategoryOut)
async def update_product_category(
    category_id: uuid.UUID,
    body: ProductCategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductCategoryOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    cat = (await db.execute(
        select(ProductCategory).where(
            ProductCategory.id == category_id,
            ProductCategory.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría de producto no encontrada")
    if body.name is not None:
        cat.name = body.name.strip()
    if body.is_active is not None:
        cat.is_active = body.is_active
    if body.position is not None:
        cat.position = body.position
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una categoría de producto con el nombre '{body.name}' en tu cuenta",
        )
    await db.refresh(cat)
    return ProductCategoryOut.model_validate(cat)
