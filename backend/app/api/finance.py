from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.finance import ExpenseCategory, FinancePermission
from app.models.tenant import Branch
from app.models.user import User, UserRole

router = APIRouter(prefix="/finance", tags=["finance"])

_OWNER_ROLES = (UserRole.OWNER, UserRole.PLATFORM_OWNER)


# ── Access helper ─────────────────────────────────────────────────────────────

async def _require_finance_access(
    current_user: User,
    branch_id: uuid.UUID | None,
    db: AsyncSession,
) -> None:
    if current_user.role in _OWNER_ROLES:
        return
    result = await db.execute(
        select(FinancePermission).where(
            FinancePermission.tenant_id == current_user.tenant_id,
            FinancePermission.user_id == current_user.id,
            or_(
                FinancePermission.branch_id == branch_id,
                FinancePermission.branch_id.is_(None),
            ),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes acceso a finanzas")


def _require_owner(current_user: User) -> None:
    if current_user.role not in _OWNER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario puede gestionar permisos de finanzas")


# ── Schemas ───────────────────────────────────────────────────────────────────

class FinancePermissionOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID | None
    user_id: uuid.UUID
    granted_by: uuid.UUID | None
    user_name: str
    user_email: str
    model_config = {"from_attributes": True}


class FinancePermissionCreate(BaseModel):
    user_id: uuid.UUID
    branch_id: uuid.UUID | None = None


class ExpenseCategoryOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    kind: str
    icon: str | None
    is_active: bool
    model_config = {"from_attributes": True}


class ExpenseCategoryCreate(BaseModel):
    name: str
    kind: Literal["fijo", "variable"]
    icon: str | None = None


class ExpenseCategoryUpdate(BaseModel):
    name: str | None = None
    kind: Literal["fijo", "variable"] | None = None
    icon: str | None = None
    is_active: bool | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/permissions", response_model=list[FinancePermissionOut])
async def list_finance_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FinancePermissionOut]:
    _require_owner(current_user)
    rows = (await db.execute(
        select(FinancePermission, User)
        .join(User, User.id == FinancePermission.user_id)
        .where(FinancePermission.tenant_id == current_user.tenant_id)
        .order_by(FinancePermission.created_at)
    )).all()
    return [
        FinancePermissionOut(
            id=fp.id,
            tenant_id=fp.tenant_id,
            branch_id=fp.branch_id,
            user_id=fp.user_id,
            granted_by=fp.granted_by,
            user_name=u.name,
            user_email=u.email,
        )
        for fp, u in rows
    ]


@router.post("/permissions", response_model=FinancePermissionOut, status_code=status.HTTP_201_CREATED)
async def create_finance_permission(
    body: FinancePermissionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FinancePermissionOut:
    _require_owner(current_user)

    target_user = (await db.execute(
        select(User).where(User.id == body.user_id, User.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado en este tenant")

    if body.branch_id is not None:
        branch = (await db.execute(
            select(Branch).where(Branch.id == body.branch_id, Branch.tenant_id == current_user.tenant_id)
        )).scalar_one_or_none()
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada en este tenant")

    perm = FinancePermission(
        tenant_id=current_user.tenant_id,
        user_id=body.user_id,
        branch_id=body.branch_id,
        granted_by=current_user.id,
    )
    db.add(perm)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este usuario ya tiene ese permiso de finanzas")
    await db.refresh(perm)

    return FinancePermissionOut(
        id=perm.id,
        tenant_id=perm.tenant_id,
        branch_id=perm.branch_id,
        user_id=perm.user_id,
        granted_by=perm.granted_by,
        user_name=target_user.name,
        user_email=target_user.email,
    )


@router.get("/expense-categories", response_model=list[ExpenseCategoryOut])
async def list_expense_categories(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseCategoryOut]:
    await _require_finance_access(current_user, branch_id=None, db=db)
    q = select(ExpenseCategory).where(ExpenseCategory.tenant_id == current_user.tenant_id)
    if not include_inactive:
        q = q.where(ExpenseCategory.is_active.is_(True))
    q = q.order_by(ExpenseCategory.kind, ExpenseCategory.name)
    rows = (await db.execute(q)).scalars().all()
    return [ExpenseCategoryOut.model_validate(r) for r in rows]


@router.post("/expense-categories", response_model=ExpenseCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_expense_category(
    body: ExpenseCategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseCategoryOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    cat = ExpenseCategory(
        tenant_id=current_user.tenant_id,
        name=body.name.strip(),
        kind=body.kind,
        icon=body.icon,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return ExpenseCategoryOut.model_validate(cat)


@router.patch("/expense-categories/{category_id}", response_model=ExpenseCategoryOut)
async def update_expense_category(
    category_id: uuid.UUID,
    body: ExpenseCategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseCategoryOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    cat = (await db.execute(
        select(ExpenseCategory).where(
            ExpenseCategory.id == category_id,
            ExpenseCategory.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
    if body.name is not None:
        cat.name = body.name.strip()
    if body.kind is not None:
        cat.kind = body.kind
    if body.icon is not None:
        cat.icon = body.icon
    if body.is_active is not None:
        cat.is_active = body.is_active
    await db.commit()
    await db.refresh(cat)
    return ExpenseCategoryOut.model_validate(cat)


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_finance_permission(
    permission_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_owner(current_user)
    perm = (await db.execute(
        select(FinancePermission).where(
            FinancePermission.id == permission_id,
            FinancePermission.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if perm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permiso no encontrado")
    await db.delete(perm)
    await db.commit()
