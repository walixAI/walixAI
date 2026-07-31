"""Profitability and run-rate analytics service.

Run-rate: projected revenue for the full month based on deals won so far,
scaled by elapsed business days (or calendar days per tenant setting).
Profitability: (revenue − expenses) / revenue * 100 for a given period.
"""
from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal
from app.models.finance import Expense
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment
from app.models.pipeline import PipelineStage
from app.models.tenant import Tenant
from app.models.user import User


# ── Internal helpers ──────────────────────────────────────────────────────────

def _business_days_in_month(year: int, month: int) -> int:
    total, _ = monthrange(year, month)
    count = 0
    for d in range(1, total + 1):
        if date(year, month, d).weekday() < 5:
            count += 1
    return count


def _elapsed_days(year: int, month: int, count_business: bool, today: date) -> int:
    """Days elapsed in the period up to and including today (minimum 1)."""
    start = date(year, month, 1)
    end = min(today, date(year, month, monthrange(year, month)[1]))
    if not count_business:
        return max(1, (end - start).days + 1)
    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return max(1, count)


def _total_days(year: int, month: int, count_business: bool) -> int:
    if not count_business:
        return monthrange(year, month)[1]
    return _business_days_in_month(year, month)


def _profit_label(profit_pct: float | None, thresholds: dict) -> str:
    """Map profit % to traffic-light label using tenant thresholds."""
    if profit_pct is None:
        return "unknown"
    green = float(thresholds.get("green", 20))
    yellow = float(thresholds.get("yellow", 10))
    orange = float(thresholds.get("orange", 0))
    if profit_pct >= green:
        return "green"
    if profit_pct >= yellow:
        return "yellow"
    if profit_pct >= orange:
        return "orange"
    return "red"


# ── Public service functions ───────────────────────────────────────────────────

async def get_current_month_goal(
    tenant_id: uuid.UUID,
    year: int,
    month: int,
    db: AsyncSession,
) -> MonthlyGoal | None:
    """Return the 'global' dimension goal for (year, month), or None."""
    result = await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.tenant_id == tenant_id,
            MonthlyGoal.period_year == year,
            MonthlyGoal.period_month == month,
            MonthlyGoal.dimension == "global",
            MonthlyGoal.is_draft.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_tenant_run_rate(
    tenant: Tenant,
    year: int,
    month: int,
    db: AsyncSession,
) -> dict:
    """Projected full-month revenue based on won deals so far."""
    today = date.today()

    # Sum of amount for deals won this month (updated_at as proxy for close date)
    won_q = await db.execute(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(
            Deal.tenant_id == tenant.id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
    )
    won_revenue: Decimal = Decimal(str(won_q.scalar()))

    count_biz = bool(tenant.count_business_days)
    elapsed = _elapsed_days(year, month, count_biz, today)
    total = _total_days(year, month, count_biz)

    run_rate = won_revenue * Decimal(total) / Decimal(elapsed) if elapsed > 0 else Decimal("0")

    goal = await get_current_month_goal(tenant.id, year, month, db)
    goal_amount = Decimal(str(goal.amount)) if goal else None

    pct_of_goal: float | None = None
    if goal_amount and goal_amount > 0:
        pct_of_goal = float(run_rate / goal_amount * 100)

    return {
        "year": year,
        "month": month,
        "won_revenue": float(won_revenue),
        "run_rate": float(run_rate),
        "elapsed_days": elapsed,
        "total_days": total,
        "goal_amount": float(goal_amount) if goal_amount is not None else None,
        "pct_of_goal": round(pct_of_goal, 2) if pct_of_goal is not None else None,
    }


async def get_tenant_profitability(
    tenant: Tenant,
    year: int,
    month: int,
    db: AsyncSession,
) -> dict:
    """Revenue - confirmed expenses for the period, with profit % and label."""
    won_q = await db.execute(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(
            Deal.tenant_id == tenant.id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
    )
    revenue = Decimal(str(won_q.scalar()))

    cost_q = await db.execute(
        select(func.coalesce(func.sum(Deal.cost_amount), 0)).where(
            Deal.tenant_id == tenant.id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
    )
    deal_costs = Decimal(str(cost_q.scalar()))

    exp_q = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.tenant_id == tenant.id,
            Expense.status == "confirmed",
            func.extract("year", Expense.incurred_at) == year,
            func.extract("month", Expense.incurred_at) == month,
        )
    )
    expenses = Decimal(str(exp_q.scalar()))

    total_costs = deal_costs + expenses
    profit = revenue - total_costs
    profit_pct: float | None = None
    if revenue > 0:
        profit_pct = round(float(profit / revenue * 100), 2)

    thresholds = tenant.profit_thresholds or {"green": 20, "yellow": 10, "orange": 0}

    return {
        "year": year,
        "month": month,
        "revenue": float(revenue),
        "deal_costs": float(deal_costs),
        "expenses": float(expenses),
        "total_costs": float(total_costs),
        "profit": float(profit),
        "profit_pct": profit_pct,
        "label": _profit_label(profit_pct, thresholds),
    }


async def get_user_run_rate(
    tenant: Tenant,
    user_id: uuid.UUID,
    year: int,
    month: int,
    db: AsyncSession,
) -> dict:
    """Run-rate for a specific sales rep based on their owned+won deals."""
    today = date.today()

    won_q = await db.execute(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(
            Deal.tenant_id == tenant.id,
            Deal.owner_id == user_id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
    )
    won_revenue = Decimal(str(won_q.scalar()))

    count_biz = bool(tenant.count_business_days)
    elapsed = _elapsed_days(year, month, count_biz, today)
    total = _total_days(year, month, count_biz)
    run_rate = won_revenue * Decimal(total) / Decimal(elapsed) if elapsed > 0 else Decimal("0")

    # User's assigned share of global goal
    goal = await get_current_month_goal(tenant.id, year, month, db)
    user_goal: Decimal | None = None
    if goal:
        assign_q = await db.execute(
            select(MonthlyGoalAssignment).where(
                MonthlyGoalAssignment.goal_id == goal.id,
                MonthlyGoalAssignment.user_id == user_id,
            )
        )
        assignment = assign_q.scalar_one_or_none()
        if assignment:
            user_goal = Decimal(str(assignment.amount))

    pct_of_goal: float | None = None
    if user_goal and user_goal > 0:
        pct_of_goal = round(float(run_rate / user_goal * 100), 2)

    return {
        "user_id": str(user_id),
        "year": year,
        "month": month,
        "won_revenue": float(won_revenue),
        "run_rate": float(run_rate),
        "elapsed_days": elapsed,
        "total_days": total,
        "user_goal": float(user_goal) if user_goal is not None else None,
        "pct_of_goal": pct_of_goal,
    }


async def get_user_profitability(
    tenant: Tenant,
    user_id: uuid.UUID,
    year: int,
    month: int,
    db: AsyncSession,
) -> dict:
    """Revenue and deal costs for a user's won deals in a period."""
    won_q = await db.execute(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(
            Deal.tenant_id == tenant.id,
            Deal.owner_id == user_id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
    )
    revenue = Decimal(str(won_q.scalar()))

    cost_q = await db.execute(
        select(func.coalesce(func.sum(Deal.cost_amount), 0)).where(
            Deal.tenant_id == tenant.id,
            Deal.owner_id == user_id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
    )
    deal_costs = Decimal(str(cost_q.scalar()))

    profit = revenue - deal_costs
    profit_pct: float | None = None
    if revenue > 0:
        profit_pct = round(float(profit / revenue * 100), 2)

    thresholds = tenant.profit_thresholds or {"green": 20, "yellow": 10, "orange": 0}

    return {
        "user_id": str(user_id),
        "year": year,
        "month": month,
        "revenue": float(revenue),
        "deal_costs": float(deal_costs),
        "profit": float(profit),
        "profit_pct": profit_pct,
        "label": _profit_label(profit_pct, thresholds),
    }


async def suggest_goal_split(
    tenant_id: uuid.UUID,
    year: int,
    month: int,
    db: AsyncSession,
) -> list[dict]:
    """Suggest equal goal distribution among active users with deals.

    Returns a list of {user_id, name, suggested_pct, suggested_amount}
    for the global goal of the given period.
    """
    goal = await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.tenant_id == tenant_id,
            MonthlyGoal.period_year == year,
            MonthlyGoal.period_month == month,
            MonthlyGoal.dimension == "global",
        )
    )
    goal_row = goal.scalar_one_or_none()
    if goal_row is None:
        return []

    # Active users who own at least one deal in the last 3 months
    active_users_q = await db.execute(
        select(User.id, User.name).where(
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            User.id.in_(
                select(Deal.owner_id).where(
                    Deal.tenant_id == tenant_id,
                    Deal.owner_id.isnot(None),
                ).distinct()
            ),
        )
    )
    users = active_users_q.fetchall()
    if not users:
        return []

    n = len(users)
    base_pct = round(Decimal("100") / Decimal(n), 3)
    # Give remainder to first user to ensure sum = 100
    remainder = Decimal("100") - base_pct * n
    total_goal = Decimal(str(goal_row.amount))

    result = []
    for i, (uid, uname) in enumerate(users):
        pct = base_pct + (remainder if i == 0 else Decimal("0"))
        result.append({
            "user_id": str(uid),
            "name": uname,
            "suggested_pct": float(pct),
            "suggested_amount": float(total_goal * pct / Decimal("100")),
        })
    return result
