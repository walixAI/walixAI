"""Backfill histórico de métricas para Walix — Sprint 6.

Ejecuta aggregate_daily_metrics() para los últimos 30 días en todos los
branches activos. Pobla daily_metrics con datos históricos para que las
gráficas del dashboard tengan contexto desde el día 1.

Uso:
    .venv/bin/python scripts/backfill_metrics.py
    .venv/bin/python scripts/backfill_metrics.py --days 60
"""
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch
from app.services.metrics_engine import aggregate_daily_metrics


async def get_active_branches() -> list[tuple]:
    """Return list of (branch_id, branch_name) for all active branches."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Branch.id, Branch.name).where(Branch.is_active.is_(True))
        )
        return result.all()


async def backfill(days: int = 30) -> None:
    branches = await get_active_branches()

    if not branches:
        print("✗ No se encontraron branches activos. Corre seed.py primero.")
        sys.exit(1)

    today = date.today()
    start_date = today - timedelta(days=days - 1)  # inclusive, days total

    print("=" * 60)
    print(f"Backfill de métricas: últimos {days} días")
    print(f"Rango: {start_date} → {today - timedelta(days=1)}")
    print(f"Branches: {len(branches)}")
    print("=" * 60)

    total_days = days - 1  # yesterday is the last full day
    ok_count = 0
    fail_count = 0

    for branch_id, branch_name in branches:
        print(f"\n── {branch_name} ({str(branch_id)[:8]}…) ──────────────────")

        current = start_date
        while current < today:  # stop at yesterday (today not yet complete)
            label = f"Procesando {current}..."
            print(f"  {label}", end="", flush=True)
            try:
                async with AsyncSessionLocal() as db:
                    await aggregate_daily_metrics(branch_id, current, db)
                    await db.commit()
                print(" ✓")
                ok_count += 1
            except Exception as exc:
                print(f" ✗  {exc!r:.80}")
                fail_count += 1
            current += timedelta(days=1)

    print()
    print("=" * 60)
    total = ok_count + fail_count
    print(f"Resultado: {ok_count}/{total} días procesados correctamente")
    if fail_count:
        print(f"  {fail_count} fallo(s) — revisa los ✗ arriba.")
    else:
        print("  Backfill completado. ✓")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill daily metrics for all active branches")
    p.add_argument("--days", type=int, default=30, help="Number of days to backfill (default: 30)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(backfill(days=args.days))
