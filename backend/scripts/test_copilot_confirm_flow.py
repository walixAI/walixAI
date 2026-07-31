"""test_copilot_confirm_flow.py — Verifica el flujo de confirmación del Copiloto (C3).

Turno 1: "Cámbiame la meta de este mes a $80,000"
  → Claude debe pedir confirmación; set_monthly_goal NO debe llamarse todavía.

Turno 2: "Sí, confirmo"
  → Claude debe llamar set_monthly_goal(confirmed=True)
  → MonthlyGoal en DB queda con amount=$80,000.

Uso:
    cd backend
    .venv/bin/python scripts/test_copilot_confirm_flow.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select

from app.ai.copilot_engine import run_copilot_turn
from app.core.database import AsyncSessionLocal
from app.models.ai_memory import AIConversationMessage
from app.models.goals import MonthlyGoal
from app.models.tenant import Tenant
from app.models.user import User, UserRole

SESSION_ID = "test-c3"
TARGET_EMAIL = "owner@clinica.com"
TARGET_AMOUNT = 80_000.0


def _hr(label: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")


async def get_owner_user(db) -> tuple[User, Tenant]:
    """Busca el usuario OWNER del tenant de prueba. Fallback: primer OWNER activo."""
    user = (
        await db.execute(select(User).where(User.email == TARGET_EMAIL))
    ).scalar_one_or_none()

    if user is None:
        user = (
            await db.execute(
                select(User).where(
                    User.role == UserRole.OWNER,
                    User.is_active.is_(True),
                ).limit(1)
            )
        ).scalar_one_or_none()

    if user is None:
        print(f"\n❌ No se encontró ningún usuario OWNER (buscado: {TARGET_EMAIL})")
        sys.exit(1)

    tenant = await db.get(Tenant, user.tenant_id)
    if tenant is None:
        print(f"\n❌ Tenant no encontrado para user {user.email}")
        sys.exit(1)

    return user, tenant


async def clean_session(db) -> None:
    """Elimina filas previas del session_id de prueba para empezar limpio."""
    deleted = await db.execute(
        delete(AIConversationMessage).where(
            AIConversationMessage.session_id == SESSION_ID
        )
    )
    await db.commit()
    count = deleted.rowcount
    if count:
        print(f"  (limpiados {count} mensajes previos de session '{SESSION_ID}')")


async def main() -> None:
    print(f"\n{'=' * 60}")
    print("  Walix C3 — Copiloto confirm-flow (set_monthly_goal)")
    print(f"{'=' * 60}")

    today = date.today()

    async with AsyncSessionLocal() as db:
        user, tenant = await get_owner_user(db)
        print(f"\n  Usuario  : {user.email} ({user.role.value})")
        print(f"  Tenant   : {tenant.name}")
        print(f"  Session  : {SESSION_ID}")
        print(f"  Mes      : {today.year}/{today.month:02d}")
        print(f"  Objetivo : ${TARGET_AMOUNT:,.0f} MXN\n")
        await clean_session(db)

    # ── TURNO 1 ────────────────────────────────────────────────────────────────
    _hr('TURNO 1 — "Cámbiame la meta de este mes a $80,000"')

    async with AsyncSessionLocal() as db:
        user, tenant = await get_owner_user(db)
        result1 = await run_copilot_turn(
            message="Cámbiame la meta de este mes a $80,000",
            session_id=SESSION_ID,
            user=user,
            tenant=tenant,
            db=db,
        )

    print(f"\n  tool_calls_made: {result1['tool_calls_made']}")
    print(f"\n  reply:\n")
    print(result1["reply"])

    called_t1 = "set_monthly_goal" in result1["tool_calls_made"]
    print(f"\n  {'✅ set_monthly_goal NO llamado en turno 1 (correcto)' if not called_t1 else '⚠️  set_monthly_goal FUE llamado en turno 1 — revisar prompt de confirmación'}")

    # ── TURNO 2 ────────────────────────────────────────────────────────────────
    _hr('TURNO 2 — "Sí, confirmo"')

    async with AsyncSessionLocal() as db:
        user, tenant = await get_owner_user(db)
        result2 = await run_copilot_turn(
            message="Sí, confirmo",
            session_id=SESSION_ID,
            user=user,
            tenant=tenant,
            db=db,
        )

    print(f"\n  tool_calls_made: {result2['tool_calls_made']}")
    print(f"\n  reply:\n")
    print(result2["reply"])

    called_t2 = "set_monthly_goal" in result2["tool_calls_made"]
    print(f"\n  {'✅ set_monthly_goal llamado en turno 2 (correcto)' if called_t2 else '❌ set_monthly_goal NO llamado en turno 2'}")

    # ── VERIFICAR DB ───────────────────────────────────────────────────────────
    _hr("VERIFICACIÓN EN DB — MonthlyGoal")

    goal = None
    async with AsyncSessionLocal() as db:
        user, tenant = await get_owner_user(db)
        goal = (
            await db.execute(
                select(MonthlyGoal).where(
                    MonthlyGoal.tenant_id == tenant.id,
                    MonthlyGoal.period_year == today.year,
                    MonthlyGoal.period_month == today.month,
                    MonthlyGoal.dimension == "global",
                )
            )
        ).scalar_one_or_none()

    if goal is None:
        print("\n  ❌ MonthlyGoal NO encontrada en DB")
        amount_ok = False
    else:
        amount_ok = abs(float(goal.amount) - TARGET_AMOUNT) < 0.01
        print(f"\n  goal_id  : {goal.id}")
        print(f"  period   : {goal.period_year}/{goal.period_month:02d}")
        print(f"  amount   : ${float(goal.amount):,.0f} MXN  {'✅' if amount_ok else f'❌ (esperado ${TARGET_AMOUNT:,.0f})'}")
        print(f"  is_draft : {goal.is_draft}")

    # ── RESUMEN FINAL ──────────────────────────────────────────────────────────
    _hr("RESUMEN")
    checks = {
        "Turno 1: sin llamar set_monthly_goal": not called_t1,
        "Turno 2: llama set_monthly_goal":       called_t2,
        "DB: MonthlyGoal con $80,000 MXN":       amount_ok,
    }
    for label, ok in checks.items():
        print(f"  {'✅' if ok else '❌'}  {label}")

    all_ok = all(checks.values())
    print(f"\n  {'✅ PASS' if all_ok else '⚠️  PARTIAL / FAIL'} — flujo de confirmación C3\n")


if __name__ == "__main__":
    asyncio.run(main())
