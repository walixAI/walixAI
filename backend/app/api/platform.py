"""Platform Owner dashboard endpoints for Walix.

All routes require role="platform_owner" in the authenticated JWT.

Routes:
  GET  /api/platform/stats
  GET  /api/platform/tenants
  GET  /api/platform/tenants/{tenant_id}
  POST /api/platform/impersonate/{tenant_id}
  GET  /api/platform/ai-costs
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.ai_log import AICommandLog
from app.models.conversation import Conversation, Message
from app.models.lead import Lead
from app.models.tenant import Branch, Tenant, TenantPlan
from app.models.user import User, UserRole

router = APIRouter(prefix="/platform", tags=["platform"])
logger = logging.getLogger(__name__)

# ── Pricing ──────────────────────────────────────────────────────────────────

PLAN_MRR: dict[TenantPlan, int] = {
    TenantPlan.STARTER: 29,
    TenantPlan.GROWTH: 79,
    TenantPlan.BUSINESS: 199,
    TenantPlan.ENTERPRISE: 499,
}

# Blended cost per token (input 3:1 output ratio)
# Haiku 4.5:  $0.80/MTok input, $4.00/MTok output  → ~$1.60/MTok blended
# Sonnet 4.6: $3.00/MTok input, $15.00/MTok output → ~$6.00/MTok blended
HAIKU_COST_PER_TOKEN: float = 1.6e-6
SONNET_COST_PER_TOKEN: float = 6.0e-6


def _tokens_to_usd(tokens: int, model: str = "haiku") -> float:
    rate = SONNET_COST_PER_TOKEN if "sonnet" in model.lower() else HAIKU_COST_PER_TOKEN
    return round(tokens * rate, 6)


# ── Auth dependency ───────────────────────────────────────────────────────────

async def require_platform_owner(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.PLATFORM_OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el Platform Owner puede acceder a estos endpoints",
        )
    return current_user


# ── Helpers ──────────────────────────────────────────────────────────────────

def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Returns (first_second_of_current_month, now) in UTC."""
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _renewal_date(created_at: datetime, now: datetime) -> datetime:
    """Approximates next renewal date: same day-of-month, upcoming month."""
    day = created_at.day
    month = now.month
    year = now.year
    # Try same day this month; if already past, advance to next month
    try:
        candidate = now.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        # Day doesn't exist in this month (e.g., Feb 30) — use last day
        import calendar
        last = calendar.monthrange(year, month)[1]
        candidate = now.replace(day=last, hour=0, minute=0, second=0, microsecond=0)
    if candidate <= now:
        # Push to next month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        import calendar
        last = calendar.monthrange(year, month)[1]
        day = min(day, last)
        candidate = candidate.replace(year=year, month=month, day=day)
    return candidate


async def _ai_tokens_by_tenant(
    db: AsyncSession,
    from_dt: datetime,
    to_dt: datetime,
) -> dict[uuid.UUID, int]:
    """Returns {tenant_id: total_tokens} from both messages and ai_command_logs."""
    # Messages: join messages → conversations → branches for tenant_id
    msg_rows = await db.execute(
        select(Branch.tenant_id, func.coalesce(func.sum(Message.tokens_used), 0).label("t"))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(Branch, Conversation.branch_id == Branch.id)
        .where(Message.created_at >= from_dt, Message.created_at < to_dt, Message.tokens_used.isnot(None))
        .group_by(Branch.tenant_id)
    )
    totals: dict[uuid.UUID, int] = {row.tenant_id: int(row.t) for row in msg_rows.fetchall()}

    # AI command logs: direct tenant_id
    log_rows = await db.execute(
        select(AICommandLog.tenant_id, func.coalesce(func.sum(AICommandLog.tokens_used), 0).label("t"))
        .where(
            AICommandLog.created_at >= from_dt,
            AICommandLog.created_at < to_dt,
            AICommandLog.tokens_used.isnot(None),
        )
        .group_by(AICommandLog.tenant_id)
    )
    for row in log_rows.fetchall():
        totals[row.tenant_id] = totals.get(row.tenant_id, 0) + int(row.t)

    return totals


# ── Schemas ───────────────────────────────────────────────────────────────────

class RenewalItem(BaseModel):
    tenant_name: str
    plan: str
    renewal_date: str


class PlatformStats(BaseModel):
    total_tenants: int
    active_tenants: int
    trials: int
    churned_this_month: int
    mrr_by_plan: dict[str, int]
    total_mrr: int
    renewals_next_30_days: list[RenewalItem]
    ai_costs_this_month: float


class TenantListItem(BaseModel):
    id: uuid.UUID
    name: str
    plan: str
    is_active: bool
    created_at: str
    leads_count: int
    ai_cost_this_month: float


class TenantDetail(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    plan: str
    industry: str | None
    is_active: bool
    created_at: str
    stats_last_month: dict[str, Any]
    ai_by_day: list[dict[str, Any]]


class ImpersonateOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    tenant_id: uuid.UUID


class AICostTenantRow(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tokens_messages: int
    tokens_commands: int
    total_tokens: int
    cost_usd: float


class AICostsOut(BaseModel):
    from_date: str
    to_date: str
    tenants: list[AICostTenantRow]
    grand_total_tokens: int
    grand_total_cost_usd: float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=PlatformStats)
async def platform_stats(
    _: User = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
) -> PlatformStats:
    now = datetime.now(timezone.utc)
    month_start, _ = _month_bounds(now)
    next_30 = now + timedelta(days=30)

    # Tenant counts
    all_tenants_result = await db.execute(select(Tenant))
    all_tenants = all_tenants_result.scalars().all()

    total = len(all_tenants)
    active = [t for t in all_tenants if t.is_active]
    active_count = len(active)

    # Trials: active tenants created within the last 30 days
    trial_cutoff = now - timedelta(days=30)
    trials_count = sum(
        1 for t in all_tenants
        if t.is_active and t.created_at.replace(tzinfo=timezone.utc) >= trial_cutoff
    )

    # Churned this month: became inactive this month
    churned = sum(
        1 for t in all_tenants
        if not t.is_active and t.updated_at.replace(tzinfo=timezone.utc) >= month_start
    )

    # MRR by plan (active tenants only)
    mrr_by_plan: dict[str, int] = {p.value: 0 for p in TenantPlan}
    for t in active:
        plan_key = getattr(t.plan, "value", str(t.plan))
        price = PLAN_MRR.get(TenantPlan(plan_key), 0)
        mrr_by_plan[plan_key] = mrr_by_plan.get(plan_key, 0) + price
    total_mrr = sum(mrr_by_plan.values())

    # Renewals in next 30 days
    renewals: list[RenewalItem] = []
    for t in active:
        rdate = _renewal_date(t.created_at.replace(tzinfo=timezone.utc), now)
        if rdate <= next_30:
            renewals.append(
                RenewalItem(
                    tenant_name=t.name,
                    plan=getattr(t.plan, "value", str(t.plan)),
                    renewal_date=rdate.date().isoformat(),
                )
            )
    renewals.sort(key=lambda r: r.renewal_date)

    # AI costs this month (all tenants combined)
    token_map = await _ai_tokens_by_tenant(db, month_start, now)
    ai_cost = round(sum(_tokens_to_usd(v) for v in token_map.values()), 4)

    return PlatformStats(
        total_tenants=total,
        active_tenants=active_count,
        trials=trials_count,
        churned_this_month=churned,
        mrr_by_plan=mrr_by_plan,
        total_mrr=total_mrr,
        renewals_next_30_days=renewals,
        ai_costs_this_month=ai_cost,
    )


@router.get("/tenants", response_model=list[TenantListItem])
async def list_tenants(
    status_filter: str | None = Query(None, alias="status"),
    plan_filter: str | None = Query(None, alias="plan"),
    _: User = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
) -> list[TenantListItem]:
    now = datetime.now(timezone.utc)
    month_start, _ = _month_bounds(now)
    trial_cutoff = now - timedelta(days=30)

    stmt = select(Tenant)
    if status_filter == "active":
        stmt = stmt.where(Tenant.is_active.is_(True))
    elif status_filter == "churned":
        stmt = stmt.where(Tenant.is_active.is_(False))
    elif status_filter == "trial":
        stmt = stmt.where(
            Tenant.is_active.is_(True),
            Tenant.created_at >= trial_cutoff,
        )
    if plan_filter:
        stmt = stmt.where(Tenant.plan == plan_filter)

    result = await db.execute(stmt)
    tenants = result.scalars().all()
    tenant_ids = [t.id for t in tenants]

    if not tenant_ids:
        return []

    # Batch leads count per tenant
    leads_rows = await db.execute(
        select(Lead.tenant_id, func.count(Lead.id).label("c"))
        .where(Lead.tenant_id.in_(tenant_ids))
        .group_by(Lead.tenant_id)
    )
    leads_map: dict[uuid.UUID, int] = {row.tenant_id: row.c for row in leads_rows.fetchall()}

    # Batch AI costs per tenant this month
    token_map = await _ai_tokens_by_tenant(db, month_start, now)

    items: list[TenantListItem] = []
    for t in tenants:
        items.append(
            TenantListItem(
                id=t.id,
                name=t.name,
                plan=getattr(t.plan, "value", str(t.plan)),
                is_active=t.is_active,
                created_at=t.created_at.isoformat(),
                leads_count=leads_map.get(t.id, 0),
                ai_cost_this_month=_tokens_to_usd(token_map.get(t.id, 0)),
            )
        )
    return items


@router.get("/tenants/{tenant_id}", response_model=TenantDetail)
async def get_tenant_detail(
    tenant_id: uuid.UUID,
    _: User = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
) -> TenantDetail:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")

    now = datetime.now(timezone.utc)
    last_month_start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Branch ids for this tenant
    branches_result = await db.execute(
        select(Branch.id).where(Branch.tenant_id == tenant_id)
    )
    branch_ids = [row[0] for row in branches_result.fetchall()]

    # Last-month stats
    leads_count = 0
    convs_count = 0
    msgs_count = 0
    total_latency_ms = 0
    latency_samples = 0

    if branch_ids:
        leads_r = await db.execute(
            select(func.count(Lead.id)).where(
                Lead.branch_id.in_(branch_ids),
                Lead.created_at >= last_month_start,
            )
        )
        leads_count = leads_r.scalar_one() or 0

        convs_r = await db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.branch_id.in_(branch_ids),
                Conversation.started_at >= last_month_start,
            )
        )
        convs_count = convs_r.scalar_one() or 0

        msgs_r = await db.execute(
            select(func.count(Message.id), func.sum(Message.latency_ms))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.branch_id.in_(branch_ids),
                Message.created_at >= last_month_start,
            )
        )
        msgs_row = msgs_r.one()
        msgs_count = msgs_row[0] or 0
        total_latency_ms = msgs_row[1] or 0
        latency_samples = msgs_count

    avg_latency_ms = (total_latency_ms // latency_samples) if latency_samples else None

    # AI consumption per day (last 30 days) — from messages
    daily_map: dict[str, int] = {}
    if branch_ids:
        daily_r = await db.execute(
            select(
                func.date_trunc("day", Message.created_at).label("day"),
                func.coalesce(func.sum(Message.tokens_used), 0).label("tokens"),
            )
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.branch_id.in_(branch_ids),
                Message.created_at >= last_month_start,
                Message.tokens_used.isnot(None),
            )
            .group_by(func.date_trunc("day", Message.created_at))
            .order_by(func.date_trunc("day", Message.created_at))
        )
        for row in daily_r.fetchall():
            date_str = row.day.date().isoformat() if hasattr(row.day, "date") else str(row.day)[:10]
            daily_map[date_str] = int(row.tokens)

    # Merge ai_command_logs daily (same tenant_id)
    cmd_daily_r = await db.execute(
        select(
            func.date_trunc("day", AICommandLog.created_at).label("day"),
            func.coalesce(func.sum(AICommandLog.tokens_used), 0).label("tokens"),
        )
        .where(
            AICommandLog.tenant_id == tenant_id,
            AICommandLog.created_at >= last_month_start,
            AICommandLog.tokens_used.isnot(None),
        )
        .group_by(func.date_trunc("day", AICommandLog.created_at))
    )
    for row in cmd_daily_r.fetchall():
        date_str = row.day.date().isoformat() if hasattr(row.day, "date") else str(row.day)[:10]
        daily_map[date_str] = daily_map.get(date_str, 0) + int(row.tokens)

    ai_by_day = [
        {"date": d, "tokens": t, "cost_usd": _tokens_to_usd(t)}
        for d, t in sorted(daily_map.items())
    ]

    return TenantDetail(
        id=tenant.id,
        name=tenant.name,
        email=tenant.email,
        plan=getattr(tenant.plan, "value", str(tenant.plan)),
        industry=tenant.industry,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
        stats_last_month={
            "leads_count": leads_count,
            "conversations_count": convs_count,
            "messages_count": msgs_count,
            "avg_latency_ms": avg_latency_ms,
        },
        ai_by_day=ai_by_day,
    )


@router.post("/impersonate/{tenant_id}", response_model=ImpersonateOut)
async def impersonate_tenant(
    tenant_id: uuid.UUID,
    current_user: User = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
) -> ImpersonateOut:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=4)

    access_token = create_access_token(
        data={
            "sub": str(current_user.id),
            "tenant_id": str(tenant_id),
            "read_only_impersonation": True,
        },
        expires_at=expires_at,
    )

    # Audit log
    log = AICommandLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        message=f"Platform owner impersonation of tenant {tenant_id}",
        intent_type="impersonate",
        actions_taken={"action": "impersonate", "target_tenant_id": str(tenant_id)},
    )
    db.add(log)
    await db.commit()

    logger.info(
        "platform: impersonation token issued for tenant=%s by platform_owner=%s",
        tenant_id, current_user.id,
    )
    return ImpersonateOut(
        access_token=access_token,
        expires_at=expires_at.isoformat(),
        tenant_id=tenant_id,
    )


@router.get("/ai-costs", response_model=AICostsOut)
async def ai_costs(
    from_date: str | None = Query(None, description="ISO date YYYY-MM-DD, defaults to start of current month"),
    to_date: str | None = Query(None, description="ISO date YYYY-MM-DD, defaults to today"),
    _: User = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
) -> AICostsOut:
    now = datetime.now(timezone.utc)
    month_start, _ = _month_bounds(now)

    from_dt = (
        datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
        if from_date else month_start
    )
    to_dt = (
        datetime.fromisoformat(to_date).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        if to_date else now
    )

    # Tokens from messages per tenant
    msg_rows = await db.execute(
        select(Branch.tenant_id, func.coalesce(func.sum(Message.tokens_used), 0).label("t"))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(Branch, Conversation.branch_id == Branch.id)
        .where(Message.created_at >= from_dt, Message.created_at <= to_dt, Message.tokens_used.isnot(None))
        .group_by(Branch.tenant_id)
    )
    msg_tokens: dict[uuid.UUID, int] = {row.tenant_id: int(row.t) for row in msg_rows.fetchall()}

    # Tokens from ai_command_logs per tenant
    cmd_rows = await db.execute(
        select(AICommandLog.tenant_id, func.coalesce(func.sum(AICommandLog.tokens_used), 0).label("t"))
        .where(
            AICommandLog.created_at >= from_dt,
            AICommandLog.created_at <= to_dt,
            AICommandLog.tokens_used.isnot(None),
        )
        .group_by(AICommandLog.tenant_id)
    )
    cmd_tokens: dict[uuid.UUID, int] = {row.tenant_id: int(row.t) for row in cmd_rows.fetchall()}

    all_tenant_ids = set(msg_tokens) | set(cmd_tokens)
    if not all_tenant_ids:
        return AICostsOut(
            from_date=from_dt.date().isoformat(),
            to_date=to_dt.date().isoformat(),
            tenants=[],
            grand_total_tokens=0,
            grand_total_cost_usd=0.0,
        )

    # Load tenant names in one query
    tenants_result = await db.execute(
        select(Tenant.id, Tenant.name).where(Tenant.id.in_(all_tenant_ids))
    )
    name_map: dict[uuid.UUID, str] = {row.id: row.name for row in tenants_result.fetchall()}

    rows: list[AICostTenantRow] = []
    grand_tokens = 0
    grand_cost = 0.0

    for tid in sorted(all_tenant_ids, key=lambda x: name_map.get(x, "")):
        t_msg = msg_tokens.get(tid, 0)
        t_cmd = cmd_tokens.get(tid, 0)
        total = t_msg + t_cmd
        cost = _tokens_to_usd(total)
        grand_tokens += total
        grand_cost += cost
        rows.append(
            AICostTenantRow(
                tenant_id=tid,
                tenant_name=name_map.get(tid, str(tid)),
                tokens_messages=t_msg,
                tokens_commands=t_cmd,
                total_tokens=total,
                cost_usd=round(cost, 6),
            )
        )

    return AICostsOut(
        from_date=from_dt.date().isoformat(),
        to_date=to_dt.date().isoformat(),
        tenants=rows,
        grand_total_tokens=grand_tokens,
        grand_total_cost_usd=round(grand_cost, 4),
    )
