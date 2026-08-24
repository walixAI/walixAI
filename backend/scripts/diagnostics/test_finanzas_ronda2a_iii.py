"""test_finanzas_ronda2a_iii.py — Verificación de la Ronda 2a-iii de
Finanzas/Gastos: metas (update_monthly_goal por id, set_goal_assignments)
wireadas al catálogo del Copiloto. Cierra la Ronda 2a completa.

Llama execute_tool() directo (mismo patrón que
scripts/diagnostics/test_finanzas_ronda2a_i.py /
test_finanzas_ronda2a_ii.py) contra un tenant desechable propio, creado y
limpiado en esta misma corrida.

update_monthly_goal y set_goal_assignments son DISTINTAS de set_monthly_goal
(ya wireada, hallazgo #6) — actualizan/reemplazan por goal_id, no hacen
upsert por dimensión. El fixture de MonthlyGoal se prepara en el setup vía
upsert_monthly_goal (goals_service.py) — SOLO para crear el dato de prueba,
no es parte de lo que se está verificando.

Verificaciones:
  a) update_monthly_goal cambia solo amount; currency/notes/is_draft
     quedan intactos.
  b) update_monthly_goal sobre una meta de un periodo pasado (insertada
     directo en BD, ya que upsert_monthly_goal tampoco permite crear metas
     de periodo pasado) -> {"error": ...}, sin cambios.
  c) set_goal_assignments con 2 usuarios sumando 100% sobre una meta NO
     borrador -> éxito, amounts auto-calculados = goal.amount * share/100.
  d) set_goal_assignments con usuarios sumando 60% sobre la MISMA meta no
     borrador -> {"error": ...} de suma=100%, las asignaciones de (c)
     siguen iguales (no se tocaron).
  e) Meta marcada como is_draft=True (vía update_monthly_goal), luego
     set_goal_assignments con usuarios sumando 60% -> esta vez SÍ acepta
     (regla de 100% se salta en borrador), reemplaza las de (c).
  f) set_goal_assignments con un user_id que NO pertenece al tenant ->
     {"error": ...} mencionando el id faltante, sin tocar nada.
  g) Usuario sin FinancePermission: update_monthly_goal denegado.

Uso:
    .venv/Scripts/python.exe scripts/diagnostics/test_finanzas_ronda2a_iii.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import delete, select

from app.ai.copilot_tools import execute_tool
from app.core.database import AsyncSessionLocal
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole
from app.services.goals_service import upsert_monthly_goal


def _previous_period(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


async def _setup() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]

        tenant = Tenant(
            name=f"[test_finanzas_r2a_iii] {tag}",
            email=f"finr2aiii-{tag}@walix.test",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        company = Company(tenant_id=tenant.id, name="Empresa Test")
        db.add(company)
        await db.flush()

        branch = Branch(company_id=company.id, tenant_id=tenant.id, name="Sucursal", is_active=True)
        db.add(branch)
        await db.flush()

        owner_user = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email=f"owner-{tag}@walix.test", name="Owner Test",
            hashed_password="not-used", role=UserRole.OWNER, is_active=True,
        )
        db.add(owner_user)

        user_a = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email=f"usera-{tag}@walix.test", name="Usuario A",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(user_a)

        user_b = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email=f"userb-{tag}@walix.test", name="Usuario B",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(user_b)

        asesor_no_permission = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email=f"asesor-noperm-{tag}@walix.test", name="Asesor Sin Acceso",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(asesor_no_permission)
        await db.flush()

        # Tenant/usuario ajenos, para probar (f) — user_id que no pertenece
        # al tenant de la meta.
        other_tenant = Tenant(
            name=f"[test_finanzas_r2a_iii_other] {tag}",
            email=f"finr2aiii-other-{tag}@walix.test",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(other_tenant)
        await db.flush()

        foreign_user = User(
            tenant_id=other_tenant.id, branch_id=None,
            email=f"foreign-{tag}@walix.test", name="Usuario Ajeno",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(foreign_user)
        await db.flush()

        await db.commit()

        # Fixture: meta mensual real del mes actual, dimension="global".
        # SOLO usa upsert_monthly_goal para preparar el dato de prueba, no
        # para implementar la acción bajo prueba.
        today = date.today()
        today_goal, _ = await upsert_monthly_goal(
            db,
            tenant_id=tenant.id,
            year=today.year,
            month=today.month,
            amount=Decimal("10000.00"),
            user_id=owner_user.id,
            currency="MXN",
            notes="Meta inicial",
            is_draft=False,
        )

        # Fixture: meta de un periodo pasado, insertada directo en BD —
        # upsert_monthly_goal tampoco permite crear metas de periodo
        # pasado, así que no hay otra forma de prepararla.
        py, pm = _previous_period(today.year, today.month)
        past_goal = MonthlyGoal(
            tenant_id=tenant.id,
            period_year=py,
            period_month=pm,
            amount=Decimal("5000.00"),
            currency="MXN",
            dimension="global",
            is_draft=False,
            created_by=owner_user.id,
        )
        db.add(past_goal)
        await db.commit()
        await db.refresh(past_goal)

        return {
            "tenant": tenant,
            "tenant_id": tenant.id,
            "other_tenant_id": other_tenant.id,
            "owner_user": owner_user,
            "user_a": user_a,
            "user_b": user_b,
            "asesor_no_permission": asesor_no_permission,
            "foreign_user": foreign_user,
            "goal_id": today_goal.id,
            "past_goal_id": past_goal.id,
        }


async def _cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant_id"]))
        await db.execute(delete(Tenant).where(Tenant.id == ctx["other_tenant_id"]))
        await db.commit()


async def _list_assignments(goal_id: uuid.UUID) -> list[dict]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(MonthlyGoalAssignment).where(MonthlyGoalAssignment.goal_id == goal_id)
            )
        ).scalars().all()
        return [
            {"user_id": r.user_id, "share_percent": r.share_percent, "amount": r.amount}
            for r in rows
        ]


async def main() -> int:
    print("=" * 70)
    print("  test_finanzas_ronda2a_iii.py — metas (update por id, assignments)")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []
    ctx = await _setup()

    try:
        tenant = ctx["tenant"]
        owner = ctx["owner_user"]
        user_a = ctx["user_a"]
        user_b = ctx["user_b"]
        asesor_no_permission = ctx["asesor_no_permission"]
        foreign_user = ctx["foreign_user"]
        goal_id = ctx["goal_id"]
        past_goal_id = ctx["past_goal_id"]

        async with AsyncSessionLocal() as db:
            # ── a) update_monthly_goal — solo amount ────────────────────────
            updated_a = await execute_tool(
                "update_monthly_goal",
                {"goal_id": str(goal_id), "amount": "15000.00"},
                owner, tenant, db,
            )
            ok_a = (
                "error" not in updated_a
                and float(updated_a.get("amount", 0)) == 15000.0
                and updated_a.get("currency") == "MXN"  # no tocado
                and updated_a.get("notes") == "Meta inicial"  # no tocado
                and updated_a.get("is_draft") is False  # no tocado
            )
            results.append((
                "a. update_monthly_goal actualiza amount y NO pisa currency/notes/is_draft no tocados",
                ok_a, f"updated={updated_a}",
            ))

            # ── b) update_monthly_goal sobre meta de periodo pasado ─────────
            denied_b = await execute_tool(
                "update_monthly_goal",
                {"goal_id": str(past_goal_id), "amount": "9999.00"},
                owner, tenant, db,
            )
            past_goal_after = (
                await db.execute(select(MonthlyGoal).where(MonthlyGoal.id == past_goal_id))
            ).scalar_one_or_none()
            ok_b = "error" in denied_b and past_goal_after is not None and float(past_goal_after.amount) == 5000.0
            results.append((
                "b. update_monthly_goal sobre periodo pasado falla, no cambia nada",
                ok_b, f"result={denied_b} amount_after={past_goal_after.amount if past_goal_after else 'N/A'}",
            ))

            # ── c) set_goal_assignments 2 usuarios sumando 100% (no borrador) ──
            set_c = await execute_tool(
                "set_goal_assignments",
                {
                    "goal_id": str(goal_id),
                    "assignments": [
                        {"user_id": str(user_a.id), "share_percent": "60"},
                        {"user_id": str(user_b.id), "share_percent": "40"},
                    ],
                },
                owner, tenant, db,
            )
            ok_c = "error" not in set_c and isinstance(set_c, list) and len(set_c) == 2
            if ok_c:
                by_user = {row["user_id"]: row for row in set_c}
                expected_a = (Decimal("15000.00") * Decimal("60") / Decimal("100")).quantize(Decimal("0.01"))
                expected_b = (Decimal("15000.00") * Decimal("40") / Decimal("100")).quantize(Decimal("0.01"))
                ok_c = (
                    str(user_a.id) in by_user and str(user_b.id) in by_user
                    and abs(Decimal(str(by_user[str(user_a.id)]["amount"])) - expected_a) < Decimal("0.01")
                    and abs(Decimal(str(by_user[str(user_b.id)]["amount"])) - expected_b) < Decimal("0.01")
                )
            results.append((
                "c. set_goal_assignments 60/40 sobre meta no-borrador -> éxito, amounts auto-calculados",
                ok_c, f"result={set_c}",
            ))

            # ── d) suma 60% (no 100%) sobre la MISMA meta no-borrador -> error ──
            before_d = await _list_assignments(goal_id)
            denied_d = await execute_tool(
                "set_goal_assignments",
                {
                    "goal_id": str(goal_id),
                    "assignments": [
                        {"user_id": str(user_a.id), "share_percent": "60"},
                    ],
                },
                owner, tenant, db,
            )
            after_d = await _list_assignments(goal_id)
            ok_d = "error" in denied_d and before_d == after_d and len(after_d) == 2
            results.append((
                "d. set_goal_assignments sumando 60% sobre meta no-borrador -> error, asignaciones de (c) intactas",
                ok_d, f"result={denied_d} before={before_d} after={after_d}",
            ))

            # ── e) marcar meta como borrador, luego 60% -> SÍ acepta ────────
            drafted = await execute_tool(
                "update_monthly_goal",
                {"goal_id": str(goal_id), "is_draft": True},
                owner, tenant, db,
            )
            set_e = await execute_tool(
                "set_goal_assignments",
                {
                    "goal_id": str(goal_id),
                    "assignments": [
                        {"user_id": str(user_a.id), "share_percent": "60"},
                    ],
                },
                owner, tenant, db,
            )
            ok_e = (
                "error" not in drafted and drafted.get("is_draft") is True
                and "error" not in set_e and isinstance(set_e, list) and len(set_e) == 1
                and set_e[0]["user_id"] == str(user_a.id)
            )
            results.append((
                "e. meta en borrador -> set_goal_assignments con 60% SÍ acepta, reemplaza (c)",
                ok_e, f"drafted={drafted} set_e={set_e}",
            ))

            # ── f) user_id que no pertenece al tenant -> error, sin tocar nada ──
            before_f = await _list_assignments(goal_id)
            denied_f = await execute_tool(
                "set_goal_assignments",
                {
                    "goal_id": str(goal_id),
                    "assignments": [
                        {"user_id": str(foreign_user.id), "share_percent": "100"},
                    ],
                },
                owner, tenant, db,
            )
            after_f = await _list_assignments(goal_id)
            ok_f = (
                "error" in denied_f
                and str(foreign_user.id) in str(denied_f.get("error", ""))
                and before_f == after_f
            )
            results.append((
                "f. set_goal_assignments con user_id ajeno al tenant -> error mencionando el id, sin tocar nada",
                ok_f, f"result={denied_f} before={before_f} after={after_f}",
            ))

            # ── g) sin FinancePermission -> update_monthly_goal denegado ────
            goal_before_g = (
                await db.execute(select(MonthlyGoal).where(MonthlyGoal.id == goal_id))
            ).scalar_one_or_none()
            amount_before_g = goal_before_g.amount if goal_before_g else None
            denied_g = await execute_tool(
                "update_monthly_goal",
                {"goal_id": str(goal_id), "amount": "1.00"},
                asesor_no_permission, tenant, db,
            )
            goal_after_g = (
                await db.execute(select(MonthlyGoal).where(MonthlyGoal.id == goal_id))
            ).scalar_one_or_none()
            ok_g = (
                "error" in denied_g
                and goal_after_g is not None
                and goal_after_g.amount == amount_before_g
            )
            results.append((
                "g. update_monthly_goal denegado sin FinancePermission, no cambia nada",
                ok_g, f"result={denied_g} amount_before={amount_before_g} amount_after={goal_after_g.amount if goal_after_g else 'N/A'}",
            ))

        return _report(results)

    finally:
        await _cleanup(ctx)
        print("\n(datos de prueba limpiados)")


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
