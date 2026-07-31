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


def _run_rate_status(pct_of_goal: float | None) -> str:
    if pct_of_goal is None:
        return "red"
    if pct_of_goal >= 100:
        return "green"
    if pct_of_goal >= 70:
        return "yellow"
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
        pct_of_goal = round(float(run_rate / goal_amount * 100), 2)

    expected_today = 0.0
    gap = 0.0
    if goal_amount and goal_amount > 0:
        expected_today = float(goal_amount) * elapsed / total
        gap = max(0.0, float(goal_amount) - float(won_revenue))

    # Open (active) deals grouped by pipeline stage name
    open_deals_q = await db.execute(
        select(Deal.amount, PipelineStage.name)
        .join(PipelineStage, Deal.pipeline_stage_id == PipelineStage.id)
        .where(
            Deal.tenant_id == tenant.id,
            Deal.is_won.is_(False),
            Deal.is_lost.is_(False),
        )
    )
    open_quotes_amount = 0.0
    open_quotes_count = 0
    negotiation_amount = 0.0
    negotiation_count = 0
    for deal_amount, stage_name in open_deals_q.fetchall():
        sn = (stage_name or "").lower()
        if "cotiz" in sn:
            open_quotes_amount += float(deal_amount or 0)
            open_quotes_count += 1
        elif "negoc" in sn or "propuesta" in sn:
            negotiation_amount += float(deal_amount or 0)
            negotiation_count += 1

    # Won revenue breakdown by deal_type using tenant-configured types
    by_type_q = await db.execute(
        select(Deal.deal_type, func.coalesce(func.sum(Deal.amount), 0))
        .where(
            Deal.tenant_id == tenant.id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
        .group_by(Deal.deal_type)
    )
    deal_type_options = list(tenant.deal_type_options or [])
    sold_by_deal_type: dict[str, float] = {dt: 0.0 for dt in deal_type_options}
    for deal_type, type_total in by_type_q.fetchall():
        key = deal_type if (deal_type and deal_type in deal_type_options) else "sin_tipo"
        sold_by_deal_type[key] = sold_by_deal_type.get(key, 0.0) + float(type_total)

    # Recommendations (port of Lovable useRunRate logic, max 3)
    recommendations: list[str] = []
    remaining_days = total - elapsed
    if not goal_amount or goal_amount <= 0:
        recommendations.append("Define una meta mensual para ver proyecciones de rendimiento")
    elif run_rate >= goal_amount:
        recommendations.append(f"¡Excelente! Estás proyectado a superar tu meta de ${float(goal_amount):,.0f}")
        recommendations.append(f"Llevas ${float(won_revenue):,.0f} vendidos hasta hoy")
        recommendations.append("Considera aumentar tu meta el próximo período")
    else:
        recommendations.append(
            f"Necesitas cerrar ${gap:,.0f} más para alcanzar tu meta de ${float(goal_amount):,.0f}"
        )
        if remaining_days > 0 and gap > 0:
            daily_needed = gap / remaining_days
            recommendations.append(
                f"Necesitas vender ${daily_needed:,.0f} diarios en los {remaining_days} días restantes"
            )
        if open_quotes_amount > 0:
            recommendations.append(
                f"Tienes ${open_quotes_amount:,.0f} en cotizaciones abiertas que podrían cerrar"
            )
    recommendations = recommendations[:3]

    return {
        "year": year,
        "month": month,
        "won_revenue": float(won_revenue),
        "run_rate": float(run_rate),
        "elapsed_days": elapsed,
        "total_days": total,
        "goal_amount": float(goal_amount) if goal_amount is not None else None,
        "pct_of_goal": pct_of_goal,
        "expected_today": round(expected_today, 2),
        "gap": round(gap, 2),
        "status": _run_rate_status(pct_of_goal),
        "open_quotes_amount": round(open_quotes_amount, 2),
        "open_quotes_count": open_quotes_count,
        "negotiation_amount": round(negotiation_amount, 2),
        "negotiation_count": negotiation_count,
        "sold_by_deal_type": sold_by_deal_type,
        "recommendations": recommendations,
    }


async def get_tenant_profitability(
    tenant: Tenant,
    year: int,
    month: int,
    db: AsyncSession,
) -> dict:
    """Revenue minus confirmed expenses for the period, with profit % and label."""
    won_q = await db.execute(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(
            Deal.tenant_id == tenant.id,
            Deal.is_won.is_(True),
            func.extract("year", Deal.updated_at) == year,
            func.extract("month", Deal.updated_at) == month,
        )
    )
    revenue = Decimal(str(won_q.scalar()))

    exp_q = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.tenant_id == tenant.id,
            Expense.status == "confirmed",
            func.extract("year", Expense.incurred_at) == year,
            func.extract("month", Expense.incurred_at) == month,
        )
    )
    expenses = Decimal(str(exp_q.scalar()))

    profit = revenue - expenses
    profit_pct: float | None = None
    if revenue > 0:
        profit_pct = round(float(profit / revenue * 100), 2)

    thresholds = tenant.profit_thresholds or {"green": 20, "yellow": 10, "orange": 0}

    return {
        "year": year,
        "month": month,
        "revenue": float(revenue),
        "expenses": float(expenses),
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
    """Revenue minus confirmed tenant expenses for the period, scoped by user revenue."""
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

    exp_q = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.tenant_id == tenant.id,
            Expense.status == "confirmed",
            func.extract("year", Expense.incurred_at) == year,
            func.extract("month", Expense.incurred_at) == month,
        )
    )
    expenses = Decimal(str(exp_q.scalar()))

    profit = revenue - expenses
    profit_pct: float | None = None
    if revenue > 0:
        profit_pct = round(float(profit / revenue * 100), 2)

    thresholds = tenant.profit_thresholds or {"green": 20, "yellow": 10, "orange": 0}

    return {
        "user_id": str(user_id),
        "year": year,
        "month": month,
        "revenue": float(revenue),
        "expenses": float(expenses),
        "profit": float(profit),
        "profit_pct": profit_pct,
        "label": _profit_label(profit_pct, thresholds),
    }


async def suggest_goal_split(
    tenant_id: uuid.UUID,
    dimension: str,
    dimension_value_text: str | None,
    dimension_value_uuid: uuid.UUID | None,
    user_ids: list[uuid.UUID],
    db: AsyncSession,
) -> dict[str, Decimal]:
    """Suggest goal distribution based on 3-month trailing sales per user.

    Returns {str(user_id): share_percent}. Equal split when no sales in window.
    Window: [start_of_month - 3 months, start_of_month) — calendar months.
    """
    if not user_ids:
        return {}

    today = date.today()
    window_end = date(today.year, today.month, 1)
    bm = today.month - 3
    by = today.year
    if bm <= 0:
        bm += 12
        by -= 1
    window_start = date(by, bm, 1)

    sales: dict[str, Decimal] = {}
    for uid in user_ids:
        q = (
            select(func.coalesce(func.sum(Deal.amount), 0))
            .where(
                Deal.tenant_id == tenant_id,
                Deal.owner_id == uid,
                Deal.is_won.is_(True),
                Deal.updated_at >= window_start,
                Deal.updated_at < window_end,
            )
        )
        if dimension == "deal_type" and dimension_value_text:
            q = q.where(Deal.deal_type == dimension_value_text)
        elif dimension == "pipeline" and dimension_value_uuid:
            q = q.join(PipelineStage, Deal.pipeline_stage_id == PipelineStage.id).where(
                PipelineStage.pipeline_id == dimension_value_uuid
            )
        elif dimension == "product_category" and dimension_value_uuid:
            q = q.where(Deal.product_category_id == dimension_value_uuid)

        row = await db.execute(q)
        sales[str(uid)] = Decimal(str(row.scalar()))

    total = sum(sales.values())
    if total > 0:
        return {uid_str: round(v / total * Decimal("100"), 2) for uid_str, v in sales.items()}

    # Equal split when nobody sold in the window
    equal = round(Decimal("100") / Decimal(len(user_ids)), 2)
    return {str(uid): equal for uid in user_ids}
