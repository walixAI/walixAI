"""seed_utel_demo_b.py — Prompt Utel Demo B: Deals + Finanzas + Metas mensuales.

Puebla el tenant "Universidad Utel" con Deals ligados a los 65 Leads de Demo A
que ya avanzaron a appointment/follow_up/docs/enrolled/lost, más catálogos y
datos de Finanzas (categorías, gastos, gastos recurrentes, 1 regla) y 3
MonthlyGoal con su reparto entre los 3 asesores.

VALORES REALES CONFIRMADOS ANTES DE ESCRIBIR ESTE SCRIPT — lección aplicada
del prompt anterior (Demo A descubrió en runtime que "meta_ads" no era un
valor válido de prospection_source pese a que el prompt lo pedía). Esta vez
se verificó ANTES, consultando pg_constraint directamente (fuente de verdad
real, no los comentarios del modelo ni grep de migraciones) más los
Literal[...] de los schemas Pydantic reales en app/api/finance.py y
app/api/goals.py:
  - expenses / expense_categories / expense_rules / recurring_expenses /
    monthly_goals / monthly_goal_assignments / product_categories: CERO
    CHECK constraints a nivel BD (confirmado con una query a pg_constraint).
    Los valores abajo igual respetan los Literal[...] reales de los
    schemas Pydantic, aunque no haya un CHECK que los fuerce, para que la
    demo se vea coherente con lo que la UI/API esperan.
  - deals SÍ tiene 2 CHECK reales: ck_deals_amount_non_negative (amount>=0)
    y ck_deals_probability (0<=probability<=100) — confirmado, respetados.
  - ExpenseCategory.kind: "fijo" | "variable" (Literal real en
    app/api/finance.py::ExpenseCategoryCreate).
  - Expense.status: "draft" | "confirmed" (Literal real en
    app/api/finance.py::ExpenseUpdate — ExpenseCreate no expone status,
    siempre nace "confirmed" salvo que se toque directo, como acá).
  - Expense.source: sin Literal en el schema (ExpenseCreate no lo expone,
    el server_default es "manual") — se confirmó por grep de USOS reales
    en app/services/expense_generation.py: "rule" y "recurring" sí se usan
    en código real: se usan acá con ese mismo criterio (source="rule" para
    los gastos de comisión ligados a un Deal, "manual" para el resto).
  - ExpenseRule.rule_type: "percent_of_deal" | "fixed_per_deal" |
    "percent_of_cost" (Literal real en app/api/finance.py::ExpenseRuleCreate).
  - MonthlyGoal.dimension: "global" | "deal_type" | "pipeline" |
    "product_category" (Literal real en app/api/goals.py::MonthlyGoalCreate)
    — OJO: el prompt pedía "dimension_value_uuid apuntando a la branch
    principal de Utel", pero MonthlyGoal NO tiene ningún dimension tipo
    "branch" — los 4 valores reales son los de arriba, y el propio
    model_validator de MonthlyGoalCreate PROHÍBE explícitamente pasar
    dimension_value_text/dimension_value_uuid cuando dimension="global"
    (ValueError si se intenta). Como Utel tiene una sola branch, dimension
    "global" (tenant-wide) ES efectivamente el equivalente de "por branch"
    acá — se usa dimension="global" con dimension_value_text=None y
    dimension_value_uuid=None, documentado acá en vez de forzar un valor
    que el propio schema real rechazaría.

Idempotente: si ya existe scripts/admin/.utel_demo_manifest_b.json, aborta
sin crear nada.

Uso:
    .venv/Scripts/python.exe scripts/admin/seed_utel_demo_b.py
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.deal import Deal
from app.models.finance import Expense, ExpenseCategory, ExpenseRule, RecurringExpense
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment, ProductCategory
from app.models.lead import Lead, LeadSource
from app.models.pipeline import PipelineStage
from app.models.tag import Tag, lead_tags_table
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.tenant_setup import _find_principal_branch

UTEL_EMAIL = "admin@utel.walix.mx"
TAG_NAME = "Demo — Borrable"
MANIFEST_PATH = Path(__file__).resolve().parent / ".utel_demo_manifest_b.json"

# Mismo catálogo placeholder que qualification_data.carrera_interes de Demo A
# — sigue siendo ficticio, PENDIENTE del catálogo real de licenciaturas de
# Utel (Prompt de Knowledge Base).
CARRERAS_PLACEHOLDER_DEMO = [
    "Administración de Empresas", "Mercadotecnia Digital", "Psicología",
    "Derecho", "Ingeniería Industrial", "Contaduría Pública",
]

DEAL_STAGES = {"appointment", "follow_up", "docs", "enrolled", "lost"}
PROBABILITY_BY_STAGE = {"appointment": 30, "follow_up": 50, "docs": 75, "enrolled": 100, "lost": 0}
LOST_REASONS = ["precio", "eligió otra universidad", "dejó de responder"]

EXPENSE_CATEGORY_SPECS = [
    ("Meta Ads", "variable"),
    ("Google Ads", "variable"),
    ("Nómina Asesores", "fijo"),
    ("Software y Herramientas", "fijo"),
    ("Renta y Operación", "fijo"),
]


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _prev_year_month(year: int, month: int, back: int) -> tuple[int, int]:
    m = month - back
    while m <= 0:
        m += 12
        year -= 1
    return year, m


async def main() -> int:
    print("=" * 70)
    print("  seed_utel_demo_b.py — Deals + Finanzas + Metas mensuales (Utel)")
    print("=" * 70)

    if MANIFEST_PATH.exists():
        print(f"\nYa existe el manifiesto {MANIFEST_PATH} — no se crea nada de nuevo.")
        print("Correr purge_utel_demo_data_b.py primero si querés regenerar la demo.")
        return 0

    rng = random.Random(20260825)
    today = date.today()

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.email == UTEL_EMAIL))).scalar_one_or_none()
        if tenant is None:
            print(f"\nNo existe el tenant Utel ({UTEL_EMAIL!r}). Correr create_tenant_utel.py primero.")
            return 1

        branch = await _find_principal_branch(tenant.id, db)
        if branch is None:
            print(f"\nEl tenant Utel (id={tenant.id}) no tiene ninguna branch activa.")
            return 1

        owner = (await db.execute(
            select(User).where(User.tenant_id == tenant.id, User.role == UserRole.OWNER)
        )).scalar_one_or_none()

        asesores = (await db.execute(
            select(User).where(User.tenant_id == tenant.id, User.role == UserRole.ASESOR)
        )).scalars().all()
        if len(asesores) != 3:
            print(f"\nSe esperaban exactamente 3 ASESOR de Demo A, se encontraron {len(asesores)}. ¿Se corrió seed_utel_demo_a.py?")
            return 1

        tag = (await db.execute(select(Tag).where(Tag.tenant_id == tenant.id, Tag.name == TAG_NAME))).scalar_one_or_none()
        if tag is None:
            print(f"\nNo existe el tag {TAG_NAME!r} de Demo A — correr seed_utel_demo_a.py primero.")
            return 1

        stage_rows = (await db.execute(
            select(PipelineStage).where(PipelineStage.tenant_id == tenant.id, PipelineStage.is_archived.is_(False))
        )).scalars().all()
        stages_by_id = {s.id: s for s in stage_rows}

        # ── a) Product Categories ────────────────────────────────────────────
        product_categories = [ProductCategory(tenant_id=tenant.id, name=name, position=i) for i, name in enumerate(CARRERAS_PLACEHOLDER_DEMO)]
        db.add_all(product_categories)
        await db.flush()
        product_cat_by_name = {pc.name: pc for pc in product_categories}

        # ── b) Deals ──────────────────────────────────────────────────────────
        deal_leads = (await db.execute(
            select(Lead)
            .join(lead_tags_table, lead_tags_table.c.lead_id == Lead.id)
            .join(PipelineStage, PipelineStage.id == Lead.pipeline_stage_id)
            .where(lead_tags_table.c.tag_id == tag.id, PipelineStage.stage_key.in_(DEAL_STAGES))
        )).scalars().all()

        deals: list[Deal] = []
        deals_by_stage_key: dict[uuid.UUID, str] = {}
        for lead in deal_leads:
            stage = stages_by_id[lead.pipeline_stage_id]
            stage_key = stage.stage_key
            carrera = (lead.qualification_data or {}).get("carrera_interes")
            product_cat = product_cat_by_name.get(carrera)

            # PLACEHOLDER de demo — NO es el pricing real de Utel, pendiente de
            # que Walix confirme el costo real de las licenciaturas híbridas.
            amount = Decimal(rng.randint(35_000, 65_000))

            lead_created = lead.created_at
            if lead_created.tzinfo is None:
                lead_created = lead_created.replace(tzinfo=timezone.utc)

            if stage_key in ("enrolled", "lost"):
                # Deal (app/models/deal.py) no tiene un campo de fecha de
                # cierre real (ej. closed_at) — confirmado leyendo el modelo,
                # no asumido. Se reusa expected_close_date como proxy de
                # "cuándo se resolvió", acotado a que no caiga en el futuro.
                resolved_at = lead_created + timedelta(days=rng.randint(10, 40))
                close_date = min(resolved_at.date(), today)
            else:
                close_date = lead_created.date() + timedelta(days=rng.randint(15, 60))

            is_won = stage_key == "enrolled"
            is_lost = stage_key == "lost"

            deal = Deal(
                tenant_id=tenant.id,
                lead_id=lead.id,
                pipeline_stage_id=stage.id,
                title=f"Inscripción — {lead.name} {lead.last_name}",
                amount=amount,
                probability=PROBABILITY_BY_STAGE[stage_key],
                expected_close_date=close_date,
                is_won=is_won,
                is_lost=is_lost,
                lost_reason=rng.choice(LOST_REASONS) if is_lost else None,
                source=lead.source.value,  # mismo criterio que el lead — se lee, no se re-tira random
                deal_type="licenciatura_hibrida",
                product_category_id=product_cat.id if product_cat else None,
                owner_id=lead.assigned_to,
            )
            deals.append(deal)
            deals_by_stage_key[id(deal)] = stage_key

        db.add_all(deals)
        await db.flush()

        enrolled_deals = [d for d in deals if deals_by_stage_key[id(d)] == "enrolled"]

        # ── c) Finanzas ───────────────────────────────────────────────────────
        expense_categories = [
            ExpenseCategory(tenant_id=tenant.id, name=name, kind=kind)
            for name, kind in EXPENSE_CATEGORY_SPECS
        ]
        db.add_all(expense_categories)
        await db.flush()
        cat_by_name = {c.name: c for c in expense_categories}

        expenses: list[Expense] = []

        # Gasto publicitario — Meta Ads (14) y Google Ads (10), montos
        # placeholder de gasto diario/semanal de campaña, NO cifras reales.
        for cat_name, count, amount_range in (
            ("Meta Ads", 14, (800, 3500)),
            ("Google Ads", 10, (800, 3500)),
        ):
            cat = cat_by_name[cat_name]
            for _ in range(count):
                incurred = today - timedelta(days=rng.randint(0, 59))
                expenses.append(Expense(
                    tenant_id=tenant.id, branch_id=branch.id, category_id=cat.id,
                    amount=_q2(Decimal(rng.randint(*amount_range))),
                    kind="variable", currency="MXN", incurred_at=incurred,
                    status="confirmed" if rng.random() < 0.80 else "draft",
                    source="manual",
                    description=f"Gasto de campaña — {cat_name} (placeholder de demo)",
                ))

        # Software y Herramientas (5), Renta y Operación (4) — fijos.
        for cat_name, count, amount_range in (
            ("Software y Herramientas", 5, (500, 3000)),
            ("Renta y Operación", 4, (8_000, 25_000)),
        ):
            cat = cat_by_name[cat_name]
            for _ in range(count):
                incurred = today - timedelta(days=rng.randint(0, 59))
                expenses.append(Expense(
                    tenant_id=tenant.id, branch_id=branch.id, category_id=cat.id,
                    amount=_q2(Decimal(rng.randint(*amount_range))),
                    kind="fijo", currency="MXN", incurred_at=incurred,
                    status="confirmed" if rng.random() < 0.80 else "draft",
                    source="manual",
                    description=f"Gasto operativo — {cat_name} (placeholder de demo)",
                ))

        # Nómina Asesores (7, dentro del rango 5-8 pedido) — comisión
        # placeholder del 10% del amount del Deal, ligada a un Deal enrolled.
        # source="rule" porque narrativamente representa lo que generaría el
        # ExpenseRule de comisión creado más abajo (mismo criterio real que
        # app/services/expense_generation.py usa para expenses generados por
        # regla), aunque acá se inserta directo por simplicidad del seed.
        nomina_cat = cat_by_name["Nómina Asesores"]
        commission_deals = enrolled_deals[: min(7, len(enrolled_deals))]
        for deal in commission_deals:
            close = deal.expected_close_date or today
            expenses.append(Expense(
                tenant_id=tenant.id, branch_id=branch.id, category_id=nomina_cat.id,
                amount=_q2(deal.amount * Decimal("0.10")),
                kind="fijo", currency="MXN", incurred_at=close,
                status="confirmed", source="rule", deal_id=deal.id,
                owner_id=deal.owner_id,
                description=f"Comisión de asesor por inscripción cerrada — {deal.title} (placeholder 10%)",
            ))

        db.add_all(expenses)

        # RecurringExpense (2)
        recurring_expenses = [
            RecurringExpense(
                tenant_id=tenant.id, category_id=cat_by_name["Meta Ads"].id,
                amount=Decimal("15000.00"), day_of_month=1,
                description="Presupuesto mensual Meta Ads (placeholder de demo)",
            ),
            RecurringExpense(
                tenant_id=tenant.id, category_id=cat_by_name["Software y Herramientas"].id,
                amount=Decimal("2500.00"), day_of_month=5,
                description="Licencia CRM/Software (placeholder de demo)",
            ),
        ]
        db.add_all(recurring_expenses)

        # ExpenseRule (1) — de ejemplo, auto_confirm=False a propósito para
        # no generar side-effects (no queremos que nada se auto-confirme solo).
        expense_rules = [
            ExpenseRule(
                tenant_id=tenant.id, category_id=nomina_cat.id,
                name="Comisión por inscripción (demo)",
                rule_type="percent_of_deal", value=Decimal("10.00"),
                deal_type_filter="licenciatura_hibrida", auto_confirm=False,
            ),
        ]
        db.add_all(expense_rules)

        # ── d) Metas mensuales ───────────────────────────────────────────────
        # PLACEHOLDER de demo — no son metas reales de ingresos de Utel.
        month_specs = [
            (_prev_year_month(today.year, today.month, 2), Decimal("450000.00"), "Meta cerrada — hace 2 meses (demo)"),
            (_prev_year_month(today.year, today.month, 1), Decimal("480000.00"), "Meta cerrada — mes pasado (demo)"),
            ((today.year, today.month), Decimal("520000.00"), "Meta en curso — mes actual (demo)"),
        ]
        shares = [Decimal("40"), Decimal("30"), Decimal("30")]
        assert sum(shares) == Decimal("100")

        monthly_goals: list[MonthlyGoal] = []
        for (year, month), amount, notes in month_specs:
            monthly_goals.append(MonthlyGoal(
                tenant_id=tenant.id, period_year=year, period_month=month,
                amount=amount, currency="MXN",
                dimension="global", dimension_value_text=None, dimension_value_uuid=None,
                notes=notes, is_draft=False,
                created_by=owner.id if owner else None,
            ))
        db.add_all(monthly_goals)
        await db.flush()

        assignments: list[MonthlyGoalAssignment] = []
        for goal in monthly_goals:
            for asesor, share in zip(asesores, shares):
                assignments.append(MonthlyGoalAssignment(
                    goal_id=goal.id, tenant_id=tenant.id, user_id=asesor.id,
                    share_percent=share,
                    amount=_q2(goal.amount * share / Decimal("100")),
                ))
        db.add_all(assignments)

        await db.flush()

        # ── e) Manifiesto ────────────────────────────────────────────────────
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": str(tenant.id),
            "product_category_ids": [str(p.id) for p in product_categories],
            "deal_ids": [str(d.id) for d in deals],
            "expense_category_ids": [str(c.id) for c in expense_categories],
            "expense_ids": [str(e.id) for e in expenses],
            "recurring_expense_ids": [str(r.id) for r in recurring_expenses],
            "expense_rule_ids": [str(r.id) for r in expense_rules],
            "monthly_goal_ids": [str(g.id) for g in monthly_goals],
            "monthly_goal_assignment_ids": [str(a.id) for a in assignments],
        }

        await db.commit()

        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # ── f) Resumen ────────────────────────────────────────────────────────
        print("\n✓ Demo B sembrada exitosamente\n")
        print(f"  Product Categories: {len(product_categories)}")
        print(f"\n  Deals: {len(deals)}")
        by_stage: dict[str, tuple[int, Decimal]] = {}
        for d in deals:
            sk = deals_by_stage_key[id(d)]
            cnt, total = by_stage.get(sk, (0, Decimal("0")))
            by_stage[sk] = (cnt + 1, total + d.amount)
        for sk in ("appointment", "follow_up", "docs", "enrolled", "lost"):
            cnt, total = by_stage.get(sk, (0, Decimal("0")))
            print(f"    {sk:<12} {cnt:>3}  suma=${total:,.2f}")
        print(f"\n  Expense Categories: {len(expense_categories)}")
        print(f"  Expenses: {len(expenses)}")
        exp_by_cat: dict[str, tuple[int, Decimal]] = {}
        for e in expenses:
            cat_name = next(n for n, c in cat_by_name.items() if c.id == e.category_id)
            cnt, total = exp_by_cat.get(cat_name, (0, Decimal("0")))
            exp_by_cat[cat_name] = (cnt + 1, total + e.amount)
        for name, _ in EXPENSE_CATEGORY_SPECS:
            cnt, total = exp_by_cat.get(name, (0, Decimal("0")))
            print(f"    {name:<24} {cnt:>3}  suma=${total:,.2f}")
        print(f"\n  RecurringExpense: {len(recurring_expenses)}  |  ExpenseRule: {len(expense_rules)}")
        print(f"\n  MonthlyGoal: {len(monthly_goals)}")
        for goal in monthly_goals:
            print(f"    {goal.period_year}/{goal.period_month:02d}  amount=${goal.amount:,.2f}  is_draft={goal.is_draft}")
            for asesor, share in zip(asesores, shares):
                amt = _q2(goal.amount * share / Decimal("100"))
                print(f"      {asesor.email:<28} {share}%  ${amt:,.2f}")
        print(f"\n  Manifiesto escrito en: {MANIFEST_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
