"""Monthly goal upsert — shared business logic for the REST endpoint
(app/api/goals.py::create_or_update_monthly_goal) and the Copiloto tool
(app/ai/copilot_tools.py::set_monthly_goal). Unifies the two previously
duplicated implementations (hallazgo #6 de docs/PERMISSIONS_DRIFT_BACKLOG.md).

Access control (require_finance_access / _require_finance_access) is the
caller's responsibility — this module only executes already-authorized
business logic (validate period, find-or-create, upsert, history entry).
The Copiloto's confirmed=bool confirmation flow also stays with the caller;
it's a UX policy of the tool, not part of the goal business rules.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goals import MonthlyGoal, MonthlyGoalHistory

GoalAction = Literal["created", "updated"]


def is_past_period(year: int, month: int, today: date | None = None) -> bool:
    today = today or date.today()
    return (year, month) < (today.year, today.month)


def goal_as_dict(goal: MonthlyGoal) -> dict:
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


async def find_existing_goal(
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


async def upsert_monthly_goal(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    year: int,
    month: int,
    amount: Decimal,
    user_id: uuid.UUID,
    currency: str = "MXN",
    dimension: str = "global",
    dimension_value_text: str | None = None,
    dimension_value_uuid: uuid.UUID | None = None,
    notes: str | None = None,
    is_draft: bool = False,
) -> tuple[MonthlyGoal, GoalAction]:
    """Create or update a MonthlyGoal and record a MonthlyGoalHistory entry.

    Raises ValueError if year/month is a past period. Does not check access —
    callers must authorize before calling (see module docstring). Commits and
    refreshes the goal before returning.
    """
    if is_past_period(year, month):
        raise ValueError(f"No se puede modificar la meta de un periodo pasado ({year}/{month:02d})")

    existing = await find_existing_goal(
        db,
        tenant_id=tenant_id,
        year=year,
        month=month,
        dimension=dimension,
        value_text=dimension_value_text,
        value_uuid=dimension_value_uuid,
    )

    if existing is not None:
        before = goal_as_dict(existing)
        existing.amount = amount
        existing.currency = currency
        existing.notes = notes
        existing.is_draft = is_draft
        await db.flush()
        after = goal_as_dict(existing)
        db.add(MonthlyGoalHistory(
            tenant_id=tenant_id,
            goal_id=existing.id,
            action="goal_updated",
            before_data=before,
            after_data=after,
            changed_by=user_id,
        ))
        await db.commit()
        await db.refresh(existing)
        return existing, "updated"

    goal = MonthlyGoal(
        tenant_id=tenant_id,
        period_year=year,
        period_month=month,
        amount=amount,
        currency=currency,
        dimension=dimension,
        dimension_value_text=dimension_value_text,
        dimension_value_uuid=dimension_value_uuid,
        notes=notes,
        is_draft=is_draft,
        created_by=user_id,
    )
    db.add(goal)
    await db.flush()  # populate goal.id before building history
    after = goal_as_dict(goal)
    db.add(MonthlyGoalHistory(
        tenant_id=tenant_id,
        goal_id=goal.id,
        action="goal_created",
        before_data=None,
        after_data=after,
        changed_by=user_id,
    ))
    await db.commit()
    await db.refresh(goal)
    return goal, "created"
