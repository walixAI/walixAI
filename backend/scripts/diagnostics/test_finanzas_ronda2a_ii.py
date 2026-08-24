"""test_finanzas_ronda2a_ii.py — Verificación de la Ronda 2a-ii de
Finanzas/Gastos: catálogos de finanzas (create/update de expense_category,
recurring_expense, expense_rule, product_category) wireados al catálogo
del Copiloto.

Llama execute_tool() directo (mismo patrón que
tests/regression/test_copilot_dismiss_suggestion.py / scripts/diagnostics/
test_finanzas_ronda2a_i.py) contra un tenant desechable propio, creado y
limpiado en esta misma corrida.

Verificaciones:
  a) create_expense_category crea la categoría; aparece en
     list_expense_categories.
  b) update_expense_category (solo icon) — name/kind no tocados.
  c) create_recurring_expense con day_of_month=30 (fuera de 1-28) — falla
     con error de validación, no crea nada.
  d) create_recurring_expense válida, luego update (solo amount) —
     category_id/day_of_month/description intactos.
  e) create_expense_rule, luego update (solo value) — deal_type_filter y
     demás intactos.
  f) create_product_category "Test Dup".
  g) create_product_category "Test Dup" otra vez (mismo tenant) — devuelve
     {"error": ...} con el mensaje de duplicado (no una excepción cruda),
     Y una llamada posterior (list_product_categories) en la MISMA sesión
     de BD sigue funcionando — prueba real de que el rollback tras
     IntegrityError dejó la sesión usable.
  h) update_product_category de (f) (solo position) — name/is_active
     intactos.
  i) Usuario sin FinancePermission — create_expense_category denegado, no
     crea nada.

Uso:
    .venv/Scripts/python.exe scripts/diagnostics/test_finanzas_ronda2a_ii.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import delete, select

from app.ai.copilot_tools import execute_tool
from app.core.database import AsyncSessionLocal
from app.models.finance import ExpenseCategory, RecurringExpense
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


async def _setup() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]

        tenant = Tenant(
            name=f"[test_finanzas_r2a_ii] {tag}",
            email=f"finr2aii-{tag}@walix.test",
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
        await db.flush()

        asesor_no_permission = User(
            tenant_id=tenant.id, branch_id=branch.id,
            email=f"asesor-noperm-{tag}@walix.test", name="Asesor Sin Acceso",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(asesor_no_permission)
        await db.flush()

        await db.commit()

        return {
            "tenant": tenant,
            "owner_user": owner_user,
            "asesor_no_permission": asesor_no_permission,
            "tenant_id": tenant.id,
        }


async def _cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant_id"]))
        await db.commit()


async def _count(model, tenant_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(model).where(model.tenant_id == tenant_id))).scalars().all()
        return len(rows)


async def main() -> int:
    print("=" * 70)
    print("  test_finanzas_ronda2a_ii.py — catálogos de finanzas (escritura)")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []
    ctx = await _setup()

    try:
        tenant = ctx["tenant"]
        owner = ctx["owner_user"]
        asesor_no_permission = ctx["asesor_no_permission"]

        async with AsyncSessionLocal() as db:
            # ── a) create_expense_category + aparece en list_expense_categories ──
            created_cat = await execute_tool(
                "create_expense_category",
                {"name": "Renta", "kind": "fijo", "icon": "home"},
                owner, tenant, db,
            )
            ok_a = "error" not in created_cat and created_cat.get("name") == "Renta"
            cat_id = created_cat.get("id")
            if ok_a and cat_id:
                listed_cats = await execute_tool("list_expense_categories", {}, owner, tenant, db)
                ok_a = ok_a and any(c.get("id") == cat_id for c in listed_cats)
            results.append((
                "a. create_expense_category crea la categoría y aparece en list_expense_categories",
                ok_a, f"created={created_cat}",
            ))
            if not ok_a:
                results.append(("ABORTADO — sin cat_id válido no se puede seguir", False, "ver punto a arriba"))
                return _report(results)

            # ── b) update_expense_category — solo icon ─────────────────────────
            updated_cat = await execute_tool(
                "update_expense_category",
                {"category_id": cat_id, "icon": "building"},
                owner, tenant, db,
            )
            ok_b = (
                "error" not in updated_cat
                and updated_cat.get("icon") == "building"
                and updated_cat.get("name") == "Renta"  # no tocado
                and updated_cat.get("kind") == "fijo"  # no tocado
            )
            results.append((
                "b. update_expense_category actualiza icon y NO pisa name/kind no tocados",
                ok_b, f"updated={updated_cat}",
            ))

            # ── c) create_recurring_expense con day_of_month fuera de rango ────
            rec_count_before_c = await _count(RecurringExpense, ctx["tenant_id"])
            invalid_rec = await execute_tool(
                "create_recurring_expense",
                {"category_id": cat_id, "amount": "100", "day_of_month": 30},
                owner, tenant, db,
            )
            rec_count_after_c = await _count(RecurringExpense, ctx["tenant_id"])
            ok_c = "error" in invalid_rec and rec_count_after_c == rec_count_before_c
            results.append((
                "c. create_recurring_expense con day_of_month=30 (fuera de 1-28) falla, no crea nada",
                ok_c, f"result={invalid_rec} count_before={rec_count_before_c} count_after={rec_count_after_c}",
            ))

            # ── d) create_recurring_expense válida + update (solo amount) ──────
            created_rec = await execute_tool(
                "create_recurring_expense",
                {"category_id": cat_id, "amount": "500", "day_of_month": 15, "description": "Renta mensual"},
                owner, tenant, db,
            )
            rec_id = created_rec.get("id")
            updated_rec = await execute_tool(
                "update_recurring_expense",
                {"recurring_id": rec_id, "amount": "550"},
                owner, tenant, db,
            ) if rec_id else {}
            ok_d = (
                "error" not in created_rec and rec_id is not None
                and "error" not in updated_rec
                and float(updated_rec.get("amount", 0)) == 550.0
                and updated_rec.get("category_id") == cat_id  # no tocado
                and updated_rec.get("day_of_month") == 15  # no tocado
                and updated_rec.get("description") == "Renta mensual"  # no tocado
            )
            results.append((
                "d. create_recurring_expense + update_recurring_expense (solo amount), resto intacto",
                ok_d, f"created={created_rec} updated={updated_rec}",
            ))

            # ── e) create_expense_rule + update (solo value) ────────────────────
            created_rule = await execute_tool(
                "create_expense_rule",
                {
                    "category_id": cat_id, "name": "Comisión venta", "rule_type": "percent_of_deal",
                    "value": "5", "deal_type_filter": "servicio",
                },
                owner, tenant, db,
            )
            rule_id = created_rule.get("id")
            updated_rule = await execute_tool(
                "update_expense_rule",
                {"rule_id": rule_id, "value": "7.5"},
                owner, tenant, db,
            ) if rule_id else {}
            ok_e = (
                "error" not in created_rule and rule_id is not None
                and "error" not in updated_rule
                and float(updated_rule.get("value", 0)) == 7.5
                and updated_rule.get("deal_type_filter") == "servicio"  # no tocado
                and updated_rule.get("rule_type") == "percent_of_deal"  # no tocado
                and updated_rule.get("name") == "Comisión venta"  # no tocado
            )
            results.append((
                "e. create_expense_rule + update_expense_rule (solo value), deal_type_filter y demás intactos",
                ok_e, f"created={created_rule} updated={updated_rule}",
            ))

            # ── f) create_product_category "Test Dup" ───────────────────────────
            created_prod = await execute_tool(
                "create_product_category", {"name": "Test Dup"}, owner, tenant, db,
            )
            prod_id = created_prod.get("id")
            ok_f = "error" not in created_prod and prod_id is not None
            results.append((
                "f. create_product_category crea 'Test Dup'",
                ok_f, f"created={created_prod}",
            ))

            # ── g) duplicado -> error manejado, sesión sigue usable ─────────────
            dup_result = await execute_tool(
                "create_product_category", {"name": "Test Dup"}, owner, tenant, db,
            )
            ok_g = "error" in dup_result and "Test Dup" in str(dup_result.get("error", ""))
            # La prueba real: la MISMA sesión sigue usable después del
            # IntegrityError — si el rollback no se hizo, esta llamada
            # siguiente fallaría con InFailedSqlTransaction o similar.
            post_dup_list = await execute_tool("list_product_categories", {}, owner, tenant, db)
            ok_g = ok_g and isinstance(post_dup_list, list) and any(p.get("id") == prod_id for p in post_dup_list)
            results.append((
                "g. create_product_category duplicado -> error manejado (no excepción cruda), sesión sigue usable después (rollback real)",
                ok_g, f"dup_result={dup_result} post_dup_list_len={len(post_dup_list) if isinstance(post_dup_list, list) else 'N/A'}",
            ))

            # ── h) update_product_category — solo position ─────────────────────
            updated_prod = await execute_tool(
                "update_product_category",
                {"category_id": prod_id, "position": 5},
                owner, tenant, db,
            )
            ok_h = (
                "error" not in updated_prod
                and updated_prod.get("position") == 5
                and updated_prod.get("name") == "Test Dup"  # no tocado
                and updated_prod.get("is_active") is True  # no tocado
            )
            results.append((
                "h. update_product_category actualiza position y NO pisa name/is_active no tocados",
                ok_h, f"updated={updated_prod}",
            ))

            # ── i) sin FinancePermission — create_expense_category denegado ────
            cat_count_before_i = await _count(ExpenseCategory, ctx["tenant_id"])
            denied = await execute_tool(
                "create_expense_category",
                {"name": "No debería crearse", "kind": "variable"},
                asesor_no_permission, tenant, db,
            )
            cat_count_after_i = await _count(ExpenseCategory, ctx["tenant_id"])
            ok_i = "error" in denied and cat_count_after_i == cat_count_before_i
            results.append((
                "i. create_expense_category denegado sin FinancePermission, no crea nada",
                ok_i, f"result={denied} count_before={cat_count_before_i} count_after={cat_count_after_i}",
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
