from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.finance import Expense, ExpenseCategory, ExpenseRule, FinancePermission, RecurringExpense
from app.services.expense_generation import generate_recurring_expenses
from app.models.tenant import Branch
from app.models.user import User, UserRole

router = APIRouter(prefix="/finance", tags=["finance"])

_OWNER_ROLES = (UserRole.OWNER, UserRole.PLATFORM_OWNER)


# ── Access helpers ────────────────────────────────────────────────────────────

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


async def _get_expense_or_404(expense_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> Expense:
    exp = (await db.execute(
        select(Expense).where(Expense.id == expense_id, Expense.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto no encontrado")
    return exp


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


class ExpenseOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID | None
    category_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    amount: Decimal
    kind: str
    currency: str
    incurred_at: date
    status: str
    source: str
    deal_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    recurring_id: uuid.UUID | None
    receipt_url: str | None
    description: str | None
    model_config = {"from_attributes": True}


class ExpenseCreate(BaseModel):
    branch_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    kind: Literal["fijo", "variable"]
    currency: str = "MXN"
    incurred_at: date | None = None
    deal_id: uuid.UUID | None = None
    receipt_url: str | None = None
    description: str | None = None


class ExpenseUpdate(BaseModel):
    branch_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    kind: Literal["fijo", "variable"] | None = None
    currency: str | None = None
    incurred_at: date | None = None
    status: Literal["draft", "confirmed"] | None = None
    deal_id: uuid.UUID | None = None
    receipt_url: str | None = None
    description: str | None = None


class ExpenseConfirmBody(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)


class RecurringExpenseOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    category_id: uuid.UUID | None
    amount: Decimal
    day_of_month: int
    description: str | None
    is_active: bool
    model_config = {"from_attributes": True}


class RecurringExpenseCreate(BaseModel):
    category_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    day_of_month: int = Field(default=1, ge=1, le=28)
    description: str | None = None


class RecurringExpenseUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    description: str | None = None
    is_active: bool | None = None


class ExpenseRuleOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    rule_type: str
    value: Decimal
    deal_type_filter: str | None  # free string — validated against tenant.deal_type_options in prompt 5
    auto_confirm: bool
    is_active: bool
    model_config = {"from_attributes": True}


class ExpenseRuleCreate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str
    rule_type: Literal["percent_of_deal", "fixed_per_deal", "percent_of_cost"]
    value: Decimal = Field(gt=0)
    deal_type_filter: str | None = None
    auto_confirm: bool = False


class ExpenseRuleUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = None
    rule_type: Literal["percent_of_deal", "fixed_per_deal", "percent_of_cost"] | None = None
    value: Decimal | None = Field(default=None, gt=0)
    deal_type_filter: str | None = None
    auto_confirm: bool | None = None
    is_active: bool | None = None


# ── Finance permissions endpoints ─────────────────────────────────────────────

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


# ── Expense categories endpoints ──────────────────────────────────────────────

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


# ── Expenses endpoints ────────────────────────────────────────────────────────

@router.get("/expenses", response_model=list[ExpenseOut])
async def list_expenses(
    month: date | None = Query(None),
    kind: Literal["fijo", "variable"] | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    status_filter: Literal["draft", "confirmed"] | None = Query(None, alias="status"),
    branch_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseOut]:
    await _require_finance_access(current_user, branch_id=branch_id, db=db)
    q = select(Expense).where(Expense.tenant_id == current_user.tenant_id)
    if branch_id is not None:
        q = q.where(Expense.branch_id == branch_id)
    if month is not None:
        first_day = month.replace(day=1)
        last_day = month.replace(day=monthrange(month.year, month.month)[1])
        q = q.where(Expense.incurred_at.between(first_day, last_day))
    if kind is not None:
        q = q.where(Expense.kind == kind)
    if category_id is not None:
        q = q.where(Expense.category_id == category_id)
    if status_filter is not None:
        q = q.where(Expense.status == status_filter)
    q = q.order_by(Expense.incurred_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return [ExpenseOut.model_validate(r) for r in rows]


@router.post("/expenses/confirm-all", status_code=status.HTTP_200_OK)
async def confirm_all_draft_expenses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_finance_access(current_user, branch_id=None, db=db)
    result = await db.execute(
        update(Expense)
        .where(Expense.tenant_id == current_user.tenant_id, Expense.status == "draft")
        .values(status="confirmed")
    )
    await db.commit()
    return {"updated": result.rowcount}


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseOut:
    await _require_finance_access(current_user, branch_id=body.branch_id, db=db)
    exp = Expense(
        tenant_id=current_user.tenant_id,
        branch_id=body.branch_id,
        category_id=body.category_id,
        owner_id=current_user.id,
        amount=body.amount,
        kind=body.kind,
        currency=body.currency,
        incurred_at=body.incurred_at or date.today(),
        status="confirmed",
        source="manual",
        deal_id=body.deal_id,
        receipt_url=body.receipt_url,
        description=body.description,
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return ExpenseOut.model_validate(exp)


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: uuid.UUID,
    body: ExpenseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseOut:
    exp = await _get_expense_or_404(expense_id, current_user.tenant_id, db)
    await _require_finance_access(current_user, branch_id=exp.branch_id, db=db)
    if body.branch_id is not None:
        exp.branch_id = body.branch_id
    if body.category_id is not None:
        exp.category_id = body.category_id
    if body.amount is not None:
        exp.amount = body.amount
    if body.kind is not None:
        exp.kind = body.kind
    if body.currency is not None:
        exp.currency = body.currency
    if body.incurred_at is not None:
        exp.incurred_at = body.incurred_at
    if body.status is not None:
        exp.status = body.status
    if body.deal_id is not None:
        exp.deal_id = body.deal_id
    if body.receipt_url is not None:
        exp.receipt_url = body.receipt_url
    if body.description is not None:
        exp.description = body.description
    await db.commit()
    await db.refresh(exp)
    return ExpenseOut.model_validate(exp)


@router.post("/expenses/{expense_id}/confirm", response_model=ExpenseOut)
async def confirm_expense(
    expense_id: uuid.UUID,
    body: ExpenseConfirmBody | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseOut:
    exp = await _get_expense_or_404(expense_id, current_user.tenant_id, db)
    await _require_finance_access(current_user, branch_id=exp.branch_id, db=db)
    exp.status = "confirmed"
    if body and body.amount is not None:
        exp.amount = body.amount
    await db.commit()
    await db.refresh(exp)
    return ExpenseOut.model_validate(exp)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    exp = await _get_expense_or_404(expense_id, current_user.tenant_id, db)
    await _require_finance_access(current_user, branch_id=exp.branch_id, db=db)
    await db.delete(exp)
    await db.commit()


# ── Recurring expenses endpoints ──────────────────────────────────────────────

@router.get("/recurring-expenses", response_model=list[RecurringExpenseOut])
async def list_recurring_expenses(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RecurringExpenseOut]:
    await _require_finance_access(current_user, branch_id=None, db=db)
    q = select(RecurringExpense).where(RecurringExpense.tenant_id == current_user.tenant_id)
    if not include_inactive:
        q = q.where(RecurringExpense.is_active.is_(True))
    rows = (await db.execute(q)).scalars().all()
    return [RecurringExpenseOut.model_validate(r) for r in rows]


@router.post("/recurring-expenses", response_model=RecurringExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_recurring_expense(
    body: RecurringExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringExpenseOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    rec = RecurringExpense(
        tenant_id=current_user.tenant_id,
        category_id=body.category_id,
        amount=body.amount,
        day_of_month=body.day_of_month,
        description=body.description,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return RecurringExpenseOut.model_validate(rec)


@router.post("/recurring-expenses/generate")
async def trigger_recurring_expense_generation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_owner(current_user)
    generated = await generate_recurring_expenses(current_user.tenant_id, db)
    return {"generated": generated}


@router.patch("/recurring-expenses/{recurring_id}", response_model=RecurringExpenseOut)
async def update_recurring_expense(
    recurring_id: uuid.UUID,
    body: RecurringExpenseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecurringExpenseOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    rec = (await db.execute(
        select(RecurringExpense).where(
            RecurringExpense.id == recurring_id,
            RecurringExpense.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto recurrente no encontrado")
    if body.category_id is not None:
        rec.category_id = body.category_id
    if body.amount is not None:
        rec.amount = body.amount
    if body.day_of_month is not None:
        rec.day_of_month = body.day_of_month
    if body.description is not None:
        rec.description = body.description
    if body.is_active is not None:
        rec.is_active = body.is_active
    await db.commit()
    await db.refresh(rec)
    return RecurringExpenseOut.model_validate(rec)


@router.delete("/recurring-expenses/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_expense(
    recurring_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_finance_access(current_user, branch_id=None, db=db)
    rec = (await db.execute(
        select(RecurringExpense).where(
            RecurringExpense.id == recurring_id,
            RecurringExpense.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto recurrente no encontrado")
    await db.delete(rec)
    await db.commit()


# ── Expense rules endpoints ───────────────────────────────────────────────────

@router.get("/expense-rules", response_model=list[ExpenseRuleOut])
async def list_expense_rules(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseRuleOut]:
    await _require_finance_access(current_user, branch_id=None, db=db)
    q = select(ExpenseRule).where(ExpenseRule.tenant_id == current_user.tenant_id)
    if not include_inactive:
        q = q.where(ExpenseRule.is_active.is_(True))
    rows = (await db.execute(q)).scalars().all()
    return [ExpenseRuleOut.model_validate(r) for r in rows]


@router.post("/expense-rules", response_model=ExpenseRuleOut, status_code=status.HTTP_201_CREATED)
async def create_expense_rule(
    body: ExpenseRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRuleOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    rule = ExpenseRule(
        tenant_id=current_user.tenant_id,
        category_id=body.category_id,
        name=body.name.strip(),
        rule_type=body.rule_type,
        value=body.value,
        deal_type_filter=body.deal_type_filter,
        auto_confirm=body.auto_confirm,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return ExpenseRuleOut.model_validate(rule)


@router.patch("/expense-rules/{rule_id}", response_model=ExpenseRuleOut)
async def update_expense_rule(
    rule_id: uuid.UUID,
    body: ExpenseRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRuleOut:
    await _require_finance_access(current_user, branch_id=None, db=db)
    rule = (await db.execute(
        select(ExpenseRule).where(
            ExpenseRule.id == rule_id,
            ExpenseRule.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla de gasto no encontrada")
    if body.category_id is not None:
        rule.category_id = body.category_id
    if body.name is not None:
        rule.name = body.name.strip()
    if body.rule_type is not None:
        rule.rule_type = body.rule_type
    if body.value is not None:
        rule.value = body.value
    if body.deal_type_filter is not None:
        rule.deal_type_filter = body.deal_type_filter
    if body.auto_confirm is not None:
        rule.auto_confirm = body.auto_confirm
    if body.is_active is not None:
        rule.is_active = body.is_active
    await db.commit()
    await db.refresh(rule)
    return ExpenseRuleOut.model_validate(rule)


@router.delete("/expense-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_finance_access(current_user, branch_id=None, db=db)
    rule = (await db.execute(
        select(ExpenseRule).where(
            ExpenseRule.id == rule_id,
            ExpenseRule.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla de gasto no encontrada")
    await db.delete(rule)
    await db.commit()
