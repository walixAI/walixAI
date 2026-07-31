"""Profitability and run-rate analytics endpoints.

All 5 endpoints share the /finance prefix (same functional domain)
but live in a separate router to keep finance.py focused on CRUD.

Access control:
  - Tenant-wide endpoints: finance access required (owner or granted user)
  - Per-user endpoints:    a user may see their own data; owners see anyone's
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.finance import _require_finance_access, _require_owner
from app.core.database import get_db
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.profitability import (
    get_tenant_profitability,
    get_tenant_run_rate,
    get_user_profitability,
    get_user_run_rate,
    suggest_goal_split,
)

router = APIRouter(prefix="/finance", tags=["profitability"])

_OWNER_ROLES = (UserRole.OWNER, UserRole.PLATFORM_OWNER)


async def _get_tenant(current_user: User, db: AsyncSession) -> Tenant:
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")
    return tenant


def _current_period() -> tuple[int, int]:
    today = date.today()
    return today.year, today.month


# ── GET /finance/run-rate ─────────────────────────────────────────────────────

@router.get("/run-rate")
async def tenant_run_rate(
    year: int = Query(default=None),
    month: int = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Projected full-month revenue for the tenant based on won deals so far."""
    await _require_finance_access(current_user, None, db)
    tenant = await _get_tenant(current_user, db)
    if year is None or month is None:
        year, month = _current_period()
    return await get_tenant_run_rate(tenant, year, month, db)


# ── GET /finance/profitability ────────────────────────────────────────────────

@router.get("/profitability")
async def tenant_profitability(
    year: int = Query(default=None),
    month: int = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revenue minus costs for the tenant in the given month."""
    await _require_finance_access(current_user, None, db)
    tenant = await _get_tenant(current_user, db)
    if year is None or month is None:
        year, month = _current_period()
    return await get_tenant_profitability(tenant, year, month, db)


# ── GET /finance/run-rate/users/{user_id} ────────────────────────────────────

@router.get("/run-rate/users/{user_id}")
async def user_run_rate(
    user_id: uuid.UUID,
    year: int = Query(default=None),
    month: int = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run-rate for a specific sales rep.

    A user may view their own data; owners may view anyone in the tenant.
    """
    if current_user.id != user_id and current_user.role not in _OWNER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario puede ver el rendimiento de otros usuarios")
    tenant = await _get_tenant(current_user, db)
    if year is None or month is None:
        year, month = _current_period()
    return await get_user_run_rate(tenant, user_id, year, month, db)


# ── GET /finance/profitability/users/{user_id} ────────────────────────────────

@router.get("/profitability/users/{user_id}")
async def user_profitability(
    user_id: uuid.UUID,
    year: int = Query(default=None),
    month: int = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Profitability for a specific sales rep's won deals."""
    if current_user.id != user_id and current_user.role not in _OWNER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario puede ver el rendimiento de otros usuarios")
    tenant = await _get_tenant(current_user, db)
    if year is None or month is None:
        year, month = _current_period()
    return await get_user_profitability(tenant, user_id, year, month, db)


# ── GET /finance/goal-split-suggestion ────────────────────────────────────────

@router.get("/goal-split-suggestion")
async def goal_split_suggestion(
    year: int = Query(default=None),
    month: int = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Suggest equal goal distribution among active reps with recent deals."""
    _require_owner(current_user)
    if year is None or month is None:
        year, month = _current_period()
    return await suggest_goal_split(current_user.tenant_id, year, month, db)
