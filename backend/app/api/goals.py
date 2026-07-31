from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.finance import _require_finance_access, _require_owner
from app.core.database import get_db
from app.models.goals import MonthlyGoal, MonthlyGoalHistory, ProductCategory
from app.models.user import User

router = APIRouter(prefix="/goals", tags=["goals"])


# ── Business-rule helpers ─────────────────────────────────────────────────────

def _is_past_period(year: int, month: int) -> bool:
    today = date.today()
    return (year, month) < (today.year, today.month)


def _goal_as_dict(goal: MonthlyGoal) -> dict:
    """Serialize a MonthlyGoal to a JSON-safe dict for history before/after data."""
    return jsonable_encoder({
        "id": goal.id,
        "period_year": goal.period_year,
        "period_month": goal.period_month,
        "amount": goal.amount,
        "currency": goal.currency,
        "dimension": goal.dimension,
        "dimension_value_text": goal.dimension_value_text,
        "dimension_value_uuid": goal.dimension_value_uuid,
        "notes": goal.notes,
        "is_draft": goal.is_draft,
    })


async def _find_existing_goal(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    year: int,
    month: int,
    dimension: str,
    value_text: str | None,
    value_uuid: uuid.UUID | None,
) -> MonthlyGoal | None:
    """Look up an existing goal matching all dimension keys, treating NULL == NULL."""
    q = select(MonthlyGoal).where(
        MonthlyGoal.tenant_id == tenant_id,
        MonthlyGoal.period_year == year,
        MonthlyGoal.period_month == month,
        MonthlyGoal.dimension == dimension,
    )
    if value_text is None:
        q = q.where(MonthlyGoal.dimension_value_text.is_(None))
    else:
        q = q.where(MonthlyGoal.dimension_value_text == value_text)
    if value_uuid is None:
        q = q.where(MonthlyGoal.dimension_value_uuid.is_(None))
    else:
        q = q.where(MonthlyGoal.dimension_value_uuid == value_uuid)
    return (await db.execute(q)).scalar_one_or_none()


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


class MonthlyGoalOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    period_year: int
    period_month: int
    amount: Decimal
    currency: str
    dimension: str
    dimension_value_text: str | None
    dimension_value_uuid: uuid.UUID | None
    notes: str | None
    is_draft: bool
    created_by: uuid.UUID | None
    model_config = {"from_attributes": True}


class MonthlyGoalCreate(BaseModel):
    period_year: int
    period_month: int = Field(ge=1, le=12)
    amount: Decimal = Field(ge=0)
    currency: str = "MXN"
    dimension: Literal["global", "deal_type", "pipeline", "product_category"]
    dimension_value_text: str | None = None
    dimension_value_uuid: uuid.UUID | None = None
    notes: str | None = None
    is_draft: bool = False

    @model_validator(mode="after")
    def _validate_dimension_values(self) -> MonthlyGoalCreate:
        d = self.dimension
        if d == "global":
            if self.dimension_value_text is not None or self.dimension_value_uuid is not None:
                raise ValueError("dimension 'global' no admite dimension_value_text ni dimension_value_uuid")
        elif d == "deal_type":
            if not self.dimension_value_text:
                raise ValueError("dimension 'deal_type' requiere dimension_value_text")
            if self.dimension_value_uuid is not None:
                raise ValueError("dimension 'deal_type' no admite dimension_value_uuid")
        elif d in ("pipeline", "product_category"):
            if self.dimension_value_uuid is None:
                raise ValueError(f"dimension '{d}' requiere dimension_value_uuid")
            if self.dimension_value_text is not None:
                raise ValueError(f"dimension '{d}' no admite dimension_value_text")
        return self


class MonthlyGoalUpdate(BaseModel):
    # dimension/dimension_value_*/period_year/period_month cannot be changed —
    # a new period or dimension is a conceptually distinct goal (use POST instead)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    notes: str | None = None
    is_draft: bool | None = None


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


# ── Monthly goals endpoints ───────────────────────────────────────────────────

@router.get("/monthly-goals", response_model=list[MonthlyGoalOut])
async def list_monthly_goals(
    period_year: int | None = Query(None),
    period_month: int | None = Query(None),
    dimension: str | None = Query(None),
    include_draft: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MonthlyGoalOut]:
    await _require_finance_access(current_user, branch_id=None, db=db)
    q = select(MonthlyGoal).where(MonthlyGoal.tenant_id == current_user.tenant_id)
    if period_year is not None:
        q = q.where(MonthlyGoal.period_year == period_year)
    if period_month is not None:
        q = q.where(MonthlyGoal.period_month == period_month)
    if dimension is not None:
        q = q.where(MonthlyGoal.dimension == dimension)
    if not include_draft:
        q = q.where(MonthlyGoal.is_draft.is_(False))
    q = q.order_by(MonthlyGoal.period_year.desc(), MonthlyGoal.period_month.desc(), MonthlyGoal.dimension)
    rows = (await db.execute(q)).scalars().all()
    return [MonthlyGoalOut.model_validate(r) for r in rows]


@router.post("/monthly-goals", response_model=MonthlyGoalOut)
async def create_or_update_monthly_goal(
    body: MonthlyGoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonthlyGoalOut:
    await _require_finance_access(current_user, branch_id=None, db=db)

    if _is_past_period(body.period_year, body.period_month):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No se puede crear una meta para un periodo pasado ({body.period_year}/{body.period_month:02d})",
        )

    existing = await _find_existing_goal(
        db,
        tenant_id=current_user.tenant_id,
        year=body.period_year,
        month=body.period_month,
        dimension=body.dimension,
        value_text=body.dimension_value_text,
        value_uuid=body.dimension_value_uuid,
    )

    if existing is not None:
        # Upsert: update the existing goal instead of creating a duplicate
        before = _goal_as_dict(existing)
        existing.amount = body.amount
        existing.currency = body.currency
        existing.notes = body.notes
        existing.is_draft = body.is_draft
        await db.flush()
        after = _goal_as_dict(existing)
        db.add(MonthlyGoalHistory(
            tenant_id=current_user.tenant_id,
            goal_id=existing.id,
            action="goal_updated",
            before_data=before,
            after_data=after,
            changed_by=current_user.id,
        ))
        await db.commit()
        await db.refresh(existing)
        return MonthlyGoalOut.model_validate(existing)

    goal = MonthlyGoal(
        tenant_id=current_user.tenant_id,
        period_year=body.period_year,
        period_month=body.period_month,
        amount=body.amount,
        currency=body.currency,
        dimension=body.dimension,
        dimension_value_text=body.dimension_value_text,
        dimension_value_uuid=body.dimension_value_uuid,
        notes=body.notes,
        is_draft=body.is_draft,
        created_by=current_user.id,
    )
    db.add(goal)
    await db.flush()  # populate goal.id before building history
    after = _goal_as_dict(goal)
    db.add(MonthlyGoalHistory(
        tenant_id=current_user.tenant_id,
        goal_id=goal.id,
        action="goal_created",
        before_data=None,
        after_data=after,
        changed_by=current_user.id,
    ))
    await db.commit()
    await db.refresh(goal)
    return MonthlyGoalOut.model_validate(goal)


@router.patch("/monthly-goals/{goal_id}", response_model=MonthlyGoalOut)
async def update_monthly_goal(
    goal_id: uuid.UUID,
    body: MonthlyGoalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonthlyGoalOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    goal = (await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.id == goal_id,
            MonthlyGoal.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meta mensual no encontrada")

    if _is_past_period(goal.period_year, goal.period_month):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No se puede editar una meta de un periodo pasado ({goal.period_year}/{goal.period_month:02d})",
        )

    before = _goal_as_dict(goal)
    if body.amount is not None:
        goal.amount = body.amount
    if body.currency is not None:
        goal.currency = body.currency
    if body.notes is not None:
        goal.notes = body.notes
    if body.is_draft is not None:
        goal.is_draft = body.is_draft
    await db.flush()
    after = _goal_as_dict(goal)
    db.add(MonthlyGoalHistory(
        tenant_id=current_user.tenant_id,
        goal_id=goal.id,
        action="goal_updated",
        before_data=before,
        after_data=after,
        changed_by=current_user.id,
    ))
    await db.commit()
    await db.refresh(goal)
    return MonthlyGoalOut.model_validate(goal)
