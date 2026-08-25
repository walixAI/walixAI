"""test_utel_demo_b.py — Verificación de la demo Utel B (Deals + Finanzas +
Metas mensuales), sembrada por scripts/admin/seed_utel_demo_b.py.

NO borra nada.

Verificaciones:
  a) 65 Deals, distribuidos exactamente según la cuenta de leads por stage de
     Demo A (appointment=20, follow_up=15, docs=12, enrolled=10, lost=8),
     con is_won/is_lost correctos solo en enrolled/lost respectivamente.
  b) Ningún Deal con amount <= 0.
  c) Todo Expense.category_id apunta a una de las 5 categorías creadas acá
     (ninguno huérfano/None).
  d) Los Expense con deal_id (5-8 de ellos) apuntan efectivamente a un Deal
     is_won=True.
  e) Para cada MonthlyGoal, la suma de share_percent de sus
     MonthlyGoalAssignment es exactamente 100 y la suma de amount de los
     assignments es igual al amount del goal (tolerancia: hasta 3 centavos
     de diferencia por redondeo — 3 assignments, cada uno redondeado
     independientemente con ROUND_HALF_UP a 2 decimales).
  f) purge_utel_demo_data_b.py en modo auditoría no borra nada.
  g) PASS/FAIL por cada verificación.

Uso:
    .venv/Scripts/python.exe scripts/test_utel_demo_b.py
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models.deal import Deal
from app.models.finance import Expense, ExpenseCategory
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment
from app.models.pipeline import PipelineStage
from app.models.tenant import Tenant

sys.path.insert(0, str(Path(__file__).resolve().parent / "admin"))
from purge_utel_demo_data_b import _audit_mode as _purge_audit_mode  # noqa: E402
from purge_utel_demo_data_b import _load_manifest  # noqa: E402

UTEL_EMAIL = "admin@utel.walix.mx"
EXPECTED_DEAL_DISTRIBUTION = {"appointment": 20, "follow_up": 15, "docs": 12, "enrolled": 10, "lost": 8}
ROUNDING_TOLERANCE = Decimal("0.03")


async def main() -> int:
    print("=" * 70)
    print("  test_utel_demo_b.py — Demo Utel B (Deals + Finanzas + Metas mensuales)")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.email == UTEL_EMAIL))).scalar_one_or_none()
        if tenant is None:
            print(f"\nNo existe el tenant Utel ({UTEL_EMAIL!r}).")
            return 1

        # ── a) 65 Deals, distribución exacta, is_won/is_lost correctos ──────
        deal_rows = (await db.execute(
            select(PipelineStage.stage_key, Deal.is_won, Deal.is_lost)
            .join(PipelineStage, PipelineStage.id == Deal.pipeline_stage_id)
            .where(Deal.tenant_id == tenant.id)
        )).all()
        distribution: dict[str, int] = {}
        won_lost_ok = True
        for stage_key, is_won, is_lost in deal_rows:
            distribution[stage_key] = distribution.get(stage_key, 0) + 1
            expected_won = stage_key == "enrolled"
            expected_lost = stage_key == "lost"
            if is_won != expected_won or is_lost != expected_lost:
                won_lost_ok = False
        ok_a = len(deal_rows) == 65 and distribution == EXPECTED_DEAL_DISTRIBUTION and won_lost_ok
        results.append((
            "a. 65 Deals, distribución exacta por stage, is_won/is_lost correctos",
            ok_a,
            f"total={len(deal_rows)} distribution={distribution} won_lost_ok={won_lost_ok}",
        ))

        # ── b) ningún Deal con amount <= 0 ───────────────────────────────────
        bad_amounts = (await db.execute(
            select(func.count()).select_from(Deal).where(Deal.tenant_id == tenant.id, Deal.amount <= 0)
        )).scalar_one()
        ok_b = bad_amounts == 0
        results.append((
            "b. Ningún Deal con amount <= 0",
            ok_b,
            f"deals_con_amount_invalido={bad_amounts}",
        ))

        # ── c) todo Expense.category_id apunta a una categoría real ─────────
        cat_ids = set((await db.execute(
            select(ExpenseCategory.id).where(ExpenseCategory.tenant_id == tenant.id)
        )).scalars().all())
        expense_cat_ids = (await db.execute(
            select(Expense.category_id).where(Expense.tenant_id == tenant.id)
        )).scalars().all()
        orphans = [c for c in expense_cat_ids if c is None or c not in cat_ids]
        ok_c = len(orphans) == 0 and len(expense_cat_ids) > 0
        results.append((
            "c. Todo Expense.category_id apunta a una de las 5 categorías creadas (sin huérfanos)",
            ok_c,
            f"total_expenses={len(expense_cat_ids)} huerfanos={len(orphans)}",
        ))

        # ── d) Expense con deal_id apuntan a un Deal is_won=True ────────────
        linked = (await db.execute(
            select(Expense.deal_id, Deal.is_won)
            .join(Deal, Deal.id == Expense.deal_id)
            .where(Expense.tenant_id == tenant.id, Expense.deal_id.isnot(None))
        )).all()
        ok_d = 5 <= len(linked) <= 8 and all(is_won for _deal_id, is_won in linked)
        results.append((
            "d. 5-8 Expense con deal_id, todos apuntando a un Deal is_won=True",
            ok_d,
            f"count={len(linked)} all_won={all(is_won for _d, is_won in linked) if linked else 'N/A'}",
        ))

        # ── e) MonthlyGoalAssignment suma 100% y amount coincide (tolerancia redondeo) ──
        goals = (await db.execute(select(MonthlyGoal).where(MonthlyGoal.tenant_id == tenant.id))).scalars().all()
        goal_checks = []
        ok_e = len(goals) == 3
        for goal in goals:
            assignments = (await db.execute(
                select(MonthlyGoalAssignment).where(MonthlyGoalAssignment.goal_id == goal.id)
            )).scalars().all()
            pct_sum = sum((a.share_percent for a in assignments), Decimal("0"))
            amt_sum = sum((a.amount for a in assignments), Decimal("0"))
            pct_ok = pct_sum == Decimal("100")
            amt_ok = abs(amt_sum - goal.amount) <= ROUNDING_TOLERANCE
            goal_checks.append((f"{goal.period_year}/{goal.period_month:02d}", pct_ok, amt_ok, pct_sum, amt_sum, goal.amount))
            if not (pct_ok and amt_ok):
                ok_e = False
        results.append((
            "e. Cada MonthlyGoal: share_percent suma 100%, amount de assignments == goal.amount (±0.03 por redondeo)",
            ok_e,
            f"goals={goal_checks}",
        ))

        try:
            manifest = _load_manifest()
        except SystemExit:
            results.append(("f. purge_utel_demo_data_b.py en modo auditoría no borra nada", False, "manifiesto no encontrado"))
            return _report(results)

    async def _snapshot() -> dict:
        async with AsyncSessionLocal() as db2:
            return {
                "deals": (await db2.execute(select(func.count()).select_from(Deal).where(Deal.tenant_id == tenant.id))).scalar_one(),
                "expenses": (await db2.execute(select(func.count()).select_from(Expense).where(Expense.tenant_id == tenant.id))).scalar_one(),
                "goals": (await db2.execute(select(func.count()).select_from(MonthlyGoal).where(MonthlyGoal.tenant_id == tenant.id))).scalar_one(),
            }

    before = await _snapshot()
    purge_exit_code = await _purge_audit_mode(manifest)
    after = await _snapshot()
    ok_f = before == after and purge_exit_code == 0
    results.append((
        "f. purge_utel_demo_data_b.py en modo auditoría (sin --confirm) no borra nada",
        ok_f,
        f"exit_code={purge_exit_code} before={before} after={after}",
    ))

    return _report(results)


def _report(results: list[tuple[str, bool, str]]) -> int:
    print()
    all_ok = True
    for label, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{tag}] {label}\n         {detail}")
    print()
    if all_ok:
        print("✓ Todas las verificaciones pasaron.")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
