"""purge_utel_demo_data_b.py — Borra los datos sembrados por seed_utel_demo_b.py
(Deals + Finanzas + Metas mensuales). Mismo patrón exacto que
purge_utel_demo_data.py de Demo A, archivo/manifiesto separado a propósito
para poder purgar cada demo de forma independiente.

El manifiesto (.utel_demo_manifest_b.json) es la ÚNICA fuente de verdad — si
no existe, este script aborta.

Modo auditoría (default): cuenta filas que todavía existen, no borra nada.
Modo ejecución (--confirm): borra en orden correcto respetando FKs —
MonthlyGoalAssignment -> MonthlyGoal -> Expense -> ExpenseRule ->
RecurringExpense -> ExpenseCategory -> Deal -> ProductCategory.

Uso:
    .venv/Scripts/python.exe scripts/admin/purge_utel_demo_data_b.py             (auditoría)
    .venv/Scripts/python.exe scripts/admin/purge_utel_demo_data_b.py --confirm   (borra)
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models.deal import Deal
from app.models.finance import Expense, ExpenseCategory, ExpenseRule, RecurringExpense
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment, ProductCategory

MANIFEST_PATH = Path(__file__).resolve().parent / ".utel_demo_manifest_b.json"

ROWS = (
    ("Product Categories", "product_category_ids", ProductCategory),
    ("Deals", "deal_ids", Deal),
    ("Expense Categories", "expense_category_ids", ExpenseCategory),
    ("Expenses", "expense_ids", Expense),
    ("Recurring Expenses", "recurring_expense_ids", RecurringExpense),
    ("Expense Rules", "expense_rule_ids", ExpenseRule),
    ("Monthly Goals", "monthly_goal_ids", MonthlyGoal),
    ("Monthly Goal Assignments", "monthly_goal_assignment_ids", MonthlyGoalAssignment),
)


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"No existe el manifiesto ({MANIFEST_PATH}) — abortando.")
        print("No se intenta borrar por heurística.")
        sys.exit(1)
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


async def _count_existing(db, model, ids: list[str]) -> int:
    if not ids:
        return 0
    uuids = [uuid.UUID(i) for i in ids]
    rows = (await db.execute(select(model.id).where(model.id.in_(uuids)))).scalars().all()
    return len(rows)


async def _audit_mode(manifest: dict) -> int:
    print("=" * 70)
    print("  purge_utel_demo_data_b.py — AUDITORÍA (ningún cambio aplicado)")
    print("=" * 70)
    print()
    async with AsyncSessionLocal() as db:
        counts = {
            key: await _count_existing(db, model, manifest.get(key, []))
            for _, key, model in ROWS
        }
    print(f"Manifiesto: {MANIFEST_PATH} (creado {manifest.get('created_at', 'N/A')})")
    print()
    print("Filas que todavía existen en BD (de las que sembró el manifiesto):")
    for label, key, _model in ROWS:
        total = len(manifest.get(key, []))
        print(f"  {label:<26} {counts[key]}/{total} existen todavía")
    print()
    print("Para borrar de verdad: python scripts/admin/purge_utel_demo_data_b.py --confirm")
    return 0


async def _execute_mode(manifest: dict) -> int:
    print("=" * 70)
    print("  purge_utel_demo_data_b.py — MODO EJECUCIÓN (--confirm)")
    print("=" * 70)
    print()

    # Orden respetando FKs: children primero.
    delete_order = (
        ("Monthly Goal Assignments", "monthly_goal_assignment_ids", MonthlyGoalAssignment),
        ("Monthly Goals", "monthly_goal_ids", MonthlyGoal),
        ("Expenses", "expense_ids", Expense),
        ("Expense Rules", "expense_rule_ids", ExpenseRule),
        ("Recurring Expenses", "recurring_expense_ids", RecurringExpense),
        ("Expense Categories", "expense_category_ids", ExpenseCategory),
        ("Deals", "deal_ids", Deal),
        ("Product Categories", "product_category_ids", ProductCategory),
    )

    async with AsyncSessionLocal() as db:
        deleted: dict[str, int] = {}
        for label, key, model in delete_order:
            ids = [uuid.UUID(i) for i in manifest.get(key, [])]
            count = 0
            if ids:
                count = (await db.execute(delete(model).where(model.id.in_(ids)))).rowcount
            deleted[label] = count
        await db.commit()

    print("✓ Purga aplicada.")
    for label, _key, _model in delete_order:
        print(f"  {label:<26} borrados: {deleted[label]}")
    print()
    print(f"  Manifiesto conservado en {MANIFEST_PATH} (podés borrarlo manualmente si querés).")
    return 0


async def main() -> int:
    confirm = "--confirm" in sys.argv[1:]
    manifest = _load_manifest()
    if confirm:
        return await _execute_mode(manifest)
    return await _audit_mode(manifest)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
