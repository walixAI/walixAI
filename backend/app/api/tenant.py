"""Tenant-scoped endpoints for Walix (Sprint 9+).

Routes:
  GET   /api/tenant/trial-status
  PATCH /api/tenant/roi-config
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.tenant import Tenant, TenantPlan
from app.models.user import User, UserRole

router = APIRouter(prefix="/tenant", tags=["tenant"])


class TrialStatusOut(BaseModel):
    plan: str
    is_trial: bool
    trial_ends_at: datetime | None
    days_remaining: int
    trial_expired: bool


@router.get("/trial-status", response_model=TrialStatusOut)
async def trial_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrialStatusOut:
    """Return trial status for the authenticated user's tenant."""
    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        return TrialStatusOut(
            plan="unknown",
            is_trial=False,
            trial_ends_at=None,
            days_remaining=0,
            trial_expired=False,
        )

    plan_value = getattr(tenant.plan, "value", str(tenant.plan))
    is_trial = plan_value == TenantPlan.TRIAL.value
    days_remaining = 0
    trial_expired = False

    if is_trial and tenant.trial_ends_at:
        ends = tenant.trial_ends_at
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        delta = ends - datetime.now(timezone.utc)
        days_remaining = max(0, delta.days)
        trial_expired = delta.total_seconds() <= 0

    return TrialStatusOut(
        plan=plan_value,
        is_trial=is_trial,
        trial_ends_at=tenant.trial_ends_at,
        days_remaining=days_remaining,
        trial_expired=trial_expired,
    )


class ROIConfigRequest(BaseModel):
    revenue_per_conversion: float


@router.patch("/roi-config")
async def update_roi_config(
    body: ROIConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.role not in (UserRole.OWNER, UserRole.PLATFORM_OWNER):
        raise HTTPException(status_code=403, detail="Solo el owner puede configurar el ROI")
    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    tenant.roi_revenue_per_conversion = body.revenue_per_conversion
    await db.commit()
    return {"message": "Configuración guardada."}
