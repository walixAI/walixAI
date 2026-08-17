from __future__ import annotations

import logging
import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_tenant_context
from app.models.deal import Deal
from app.models.finance import Expense, ExpenseRule, RecurringExpense

logger = logging.getLogger(__name__)


async def generate_deal_expense_drafts(deal: Deal, db: AsyncSession) -> list[Expense]:
    """Create Expense drafts for each active ExpenseRule that matches the deal.

    Does NOT commit — caller is responsible for the transaction so the expenses
    are created atomically with the deal update that triggered this.
    """
    rules = (await db.execute(
        select(ExpenseRule).where(
            ExpenseRule.tenant_id == deal.tenant_id,
            ExpenseRule.is_active.is_(True),
        )
    )).scalars().all()

    created: list[Expense] = []
    for rule in rules:
        # Apply deal_type_filter: None means applies to all deal types
        if rule.deal_type_filter is not None and rule.deal_type_filter != deal.deal_type:
            continue

        if rule.rule_type == "percent_of_deal":
            raw = deal.amount * Decimal(str(rule.value)) / Decimal("100")
        elif rule.rule_type == "fixed_per_deal":
            raw = Decimal(str(rule.value))
        elif rule.rule_type == "percent_of_cost":
            cost = deal.cost_amount or Decimal("0")
            raw = cost * Decimal(str(rule.value)) / Decimal("100")
        else:
            logger.warning("[expense_gen] unknown rule_type %s on rule %s", rule.rule_type, rule.id)
            continue

        amount = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amount <= 0:
            continue

        expense = Expense(
            tenant_id=deal.tenant_id,
            branch_id=None,  # Deal has no branch_id — set None (see prompt 5 note)
            owner_id=deal.owner_id,
            category_id=rule.category_id,
            amount=amount,
            kind="variable",
            currency="MXN",
            incurred_at=date.today(),
            status="confirmed" if rule.auto_confirm else "draft",
            source="rule",
            deal_id=deal.id,
            rule_id=rule.id,
            description=f"{rule.name} (auto por deal ganado)",
        )
        db.add(expense)
        created.append(expense)

    logger.info(
        "[expense_gen] deal %s closed → %d expense draft(s) created (%d rules evaluated)",
        deal.id, len(created), len(rules),
    )
    return created


async def generate_recurring_expenses(
    tenant_id: uuid.UUID | None,
    db: AsyncSession,
) -> int:
    """Generate monthly Expense records from active RecurringExpense templates.

    If tenant_id is None, processes all tenants (global job use case — Celery
    beat, run_generate_recurring_expenses). Idempotent: skips a template if an
    Expense with that recurring_id already exists for the current month.
    Commits at the end of the function.

    expenses tiene RLS (migración p1q2r3s4t5u6) — recurring_expenses no, así
    que enumerar las plantillas cross-tenant no necesita función SECURITY
    DEFINER, pero cada lectura/escritura de Expense sí necesita
    set_tenant_context() con el tenant correcto primero. Cuando tenant_id ya
    viene fijo (llamado desde un endpoint, con la sesión ya scopeada a ese
    tenant por el flujo normal) el set_tenant_context es un no-op idempotente.
    """
    today = date.today()
    first_day = today.replace(day=1)
    last_day = today.replace(day=monthrange(today.year, today.month)[1])

    q = select(RecurringExpense).where(RecurringExpense.is_active.is_(True))
    if tenant_id is not None:
        q = q.where(RecurringExpense.tenant_id == tenant_id)
    templates = (await db.execute(q)).scalars().all()

    templates_by_tenant: dict[uuid.UUID, list[RecurringExpense]] = {}
    for rec in templates:
        templates_by_tenant.setdefault(rec.tenant_id, []).append(rec)

    count = 0
    for tid, recs in templates_by_tenant.items():
        await set_tenant_context(db, tid)

        for rec in recs:
            # Idempotency check: skip if already generated this month
            existing = (await db.execute(
                select(Expense).where(
                    Expense.recurring_id == rec.id,
                    Expense.incurred_at.between(first_day, last_day),
                )
            )).scalar_one_or_none()
            if existing is not None:
                continue

            incurred_at = date(today.year, today.month, rec.day_of_month)

            expense = Expense(
                tenant_id=rec.tenant_id,
                branch_id=None,
                category_id=rec.category_id,
                amount=rec.amount,
                kind="fijo",
                currency="MXN",
                incurred_at=incurred_at,
                status="confirmed",
                source="recurring",
                recurring_id=rec.id,
                description=rec.description or "Gasto mensual recurrente",
            )
            db.add(expense)
            count += 1

    if count:
        await db.commit()
        logger.info("[expense_gen] recurring: %d expense(s) generated for %s", count, tenant_id or "all tenants")

    return count
