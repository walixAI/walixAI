"""test_finanzas_ronda2a_i.py — Verificación de la Ronda 2a-i de
Finanzas/Gastos: núcleo de gastos (create_expense, update_expense,
confirm_expense, confirm_all_draft_expenses,
trigger_recurring_expense_generation) wireadas al catálogo del Copiloto.

Llama execute_tool() directo (mismo patrón que
tests/regression/test_copilot_dismiss_suggestion.py / test_copilot_finance_access.py)
contra un tenant desechable propio, creado y limpiado en esta misma corrida
— no toca datos compartidos. Sigue el patrón de
scripts/diagnostics/test_impersonation.py (setup/cleanup en finally,
PASS/FAIL por verificación).

Verificaciones:
  a) OWNER crea un gasto vía create_expense; aparece en list_expenses.
  b) OWNER actualiza ese gasto vía update_expense (partial update): el campo
     tocado cambia, los no tocados quedan intactos.
  c) Un gasto en draft (insertado directo en BD — create_expense siempre deja
     status='confirmed', igual que el REST) se confirma vía confirm_expense.
  d) Otro gasto en draft se confirma en bloque vía confirm_all_draft_expenses.
  e) Un usuario con FinancePermission scoped a OTRA sucursal intenta
     update_expense sobre el gasto de (a)/(b) — debe fallar y NO modificarlo.
  f) Un usuario sin ningún acceso a finanzas llama
     trigger_recurring_expense_generation — debe bloquearse por ROL
     (check_permission + ActionDefinition.required_role=_OWNER_TIER), no por
     require_finance_access (esta acción no la llama).
  g) OWNER llama trigger_recurring_expense_generation — responde
     {"generated": ...} sin error.
  h) OWNER actualiza el gasto de (a)/(b) vía update_expense con
     status="draft" y deal_id — confirma que ambos campos (los que faltaban
     en el bloque wireado original) se aplican de verdad, y que el resto
     (amount/description/kind) sigue intacto.

Uso:
    .venv/Scripts/python.exe scripts/diagnostics/test_finanzas_ronda2a_i.py
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
from app.models.deal import Deal
from app.models.finance import Expense, ExpenseCategory, FinancePermission
from app.models.lead import Lead
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole


async def _setup() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]

        tenant = Tenant(
            name=f"[test_finanzas_r2a_i] {tag}",
            email=f"finr2ai-{tag}@walix.test",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        company = Company(tenant_id=tenant.id, name="Empresa Test")
        db.add(company)
        await db.flush()

        branch_a = Branch(company_id=company.id, tenant_id=tenant.id, name="Sucursal A", is_active=True)
        branch_b = Branch(company_id=company.id, tenant_id=tenant.id, name="Sucursal B", is_active=True)
        db.add(branch_a)
        db.add(branch_b)
        await db.flush()

        category = ExpenseCategory(tenant_id=tenant.id, name="Renta", kind="fijo", is_active=True)
        db.add(category)
        await db.flush()

        owner_user = User(
            tenant_id=tenant.id, branch_id=branch_a.id,
            email=f"owner-{tag}@walix.test", name="Owner Test",
            hashed_password="not-used", role=UserRole.OWNER, is_active=True,
        )
        db.add(owner_user)
        await db.flush()

        asesor_wrong_branch = User(
            tenant_id=tenant.id, branch_id=branch_b.id,
            email=f"asesor-wrongbranch-{tag}@walix.test", name="Asesor Sucursal B",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(asesor_wrong_branch)
        await db.flush()
        db.add(FinancePermission(tenant_id=tenant.id, branch_id=branch_b.id, user_id=asesor_wrong_branch.id))

        asesor_no_permission = User(
            tenant_id=tenant.id, branch_id=branch_a.id,
            email=f"asesor-noperm-{tag}@walix.test", name="Asesor Sin Acceso",
            hashed_password="not-used", role=UserRole.ASESOR, is_active=True,
        )
        db.add(asesor_no_permission)
        await db.flush()

        # expenses.deal_id SÍ tiene FK real hacia deals.id (a diferencia de
        # category_id, que ninguna capa valida) — hace falta un Deal real
        # para probar update_expense con deal_id, un UUID inventado viola
        # el constraint a nivel de BD.
        lead = Lead(branch_id=branch_a.id, tenant_id=tenant.id, wa_phone="+520000000099", name="Lead para Deal de prueba")
        db.add(lead)
        await db.flush()

        pipeline = Pipeline(tenant_id=tenant.id, branch_id=branch_a.id, name="Pipeline Test", is_default=True, position=0)
        db.add(pipeline)
        await db.flush()

        stage = PipelineStage(
            tenant_id=tenant.id, branch_id=branch_a.id, pipeline_id=pipeline.id,
            name="Nuevo", slug="nuevo", order_index=0, is_won=False, is_lost=False,
        )
        db.add(stage)
        await db.flush()

        deal = Deal(
            tenant_id=tenant.id, lead_id=lead.id, pipeline_stage_id=stage.id,
            title="Deal de prueba", amount=Decimal("0"), probability=0, owner_id=owner_user.id,
        )
        db.add(deal)
        await db.flush()

        await db.commit()

        return {
            "tenant": tenant,
            "branch_a_id": branch_a.id,
            "branch_b_id": branch_b.id,
            "category_id": category.id,
            "deal_id": deal.id,
            "owner_user": owner_user,
            "asesor_wrong_branch": asesor_wrong_branch,
            "asesor_no_permission": asesor_no_permission,
            "tenant_id": tenant.id,
        }


async def _cleanup(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant_id"]))
        await db.commit()


async def _create_draft_expense(ctx: dict, *, amount: str, description: str) -> uuid.UUID:
    """create_expense (REST y tool) siempre deja status='confirmed' — para
    ejercitar confirm_expense/confirm_all_draft_expenses de verdad hace falta
    un gasto en 'draft', que solo se puede insertar directo en BD hoy."""
    async with AsyncSessionLocal() as db:
        exp = Expense(
            tenant_id=ctx["tenant_id"],
            branch_id=ctx["branch_a_id"],
            category_id=ctx["category_id"],
            owner_id=ctx["owner_user"].id,
            amount=Decimal(amount),
            kind="variable",
            currency="MXN",
            incurred_at=date.today(),
            status="draft",
            source="manual",
            description=description,
        )
        db.add(exp)
        await db.commit()
        await db.refresh(exp)
        return exp.id


async def _get_expense(expense_id: uuid.UUID) -> Expense | None:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Expense).where(Expense.id == expense_id))).scalar_one_or_none()


async def main() -> int:
    print("=" * 70)
    print("  test_finanzas_ronda2a_i.py — núcleo de gastos (escritura)")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []
    ctx = await _setup()

    try:
        tenant = ctx["tenant"]
        owner = ctx["owner_user"]
        asesor_wrong_branch = ctx["asesor_wrong_branch"]
        asesor_no_permission = ctx["asesor_no_permission"]

        async with AsyncSessionLocal() as db:
            # ── a) create_expense + aparece en list_expenses ──────────────────
            created = await execute_tool(
                "create_expense",
                {
                    "branch_id": str(ctx["branch_a_id"]),
                    "category_id": str(ctx["category_id"]),
                    "amount": "500",
                    "kind": "fijo",
                    "description": "Renta de agosto",
                },
                owner, tenant, db,
            )
            ok_a = (
                "error" not in created
                and created.get("status") == "confirmed"
                and float(created.get("amount", 0)) == 500.0
            )
            expense_id = created.get("id")
            if ok_a and expense_id:
                listed = await execute_tool("list_expenses", {}, owner, tenant, db)
                ok_a = ok_a and any(item.get("id") == expense_id for item in listed)
            results.append((
                "a. create_expense crea el gasto y aparece en list_expenses",
                ok_a, f"created={created} listed_ids={[i.get('id') for i in listed] if ok_a else 'N/A'}",
            ))
            if not ok_a:
                results.append(("ABORTADO — sin expense_id válido no se puede seguir", False, "ver punto a arriba"))
                return _report(results)

            # ── b) update_expense — partial update real ────────────────────────
            updated = await execute_tool(
                "update_expense",
                {"expense_id": expense_id, "amount": "750"},
                owner, tenant, db,
            )
            ok_b = (
                "error" not in updated
                and float(updated.get("amount", 0)) == 750.0
                and updated.get("description") == "Renta de agosto"  # no tocado, debe seguir igual
                and updated.get("kind") == "fijo"  # no tocado
                and updated.get("category_id") == str(ctx["category_id"])  # no tocado
            )
            results.append((
                "b. update_expense actualiza amount y NO pisa description/kind/category_id no tocados",
                ok_b, f"updated={updated}",
            ))

            # ── c) draft -> confirm_expense ──────────────────────────────────
            draft_id_c = await _create_draft_expense(ctx, amount="120", description="Draft para confirm_expense")
            confirmed_c = await execute_tool(
                "confirm_expense", {"expense_id": str(draft_id_c)}, owner, tenant, db,
            )
            db_exp_c = await _get_expense(draft_id_c)
            ok_c = (
                "error" not in confirmed_c
                and confirmed_c.get("status") == "confirmed"
                and db_exp_c is not None and db_exp_c.status == "confirmed"
            )
            results.append((
                "c. confirm_expense pasa un gasto draft a confirmed",
                ok_c, f"tool_result_status={confirmed_c.get('status')} db_status={db_exp_c.status if db_exp_c else None}",
            ))

            # ── d) draft -> confirm_all_draft_expenses ──────────────────────
            draft_id_d = await _create_draft_expense(ctx, amount="80", description="Draft para confirm_all")
            confirm_all_result = await execute_tool("confirm_all_draft_expenses", {}, owner, tenant, db)
            db_exp_d = await _get_expense(draft_id_d)
            ok_d = (
                "error" not in confirm_all_result
                and confirm_all_result.get("updated", 0) >= 1
                and db_exp_d is not None and db_exp_d.status == "confirmed"
            )
            results.append((
                "d. confirm_all_draft_expenses confirma en bloque (incluye el draft de prueba)",
                ok_d, f"result={confirm_all_result} db_status={db_exp_d.status if db_exp_d else None}",
            ))

            # ── e) usuario con FinancePermission de OTRA sucursal — denegado ──
            amount_before_e = (await _get_expense(uuid.UUID(expense_id))).amount
            denied_update = await execute_tool(
                "update_expense",
                {"expense_id": expense_id, "amount": "999"},
                asesor_wrong_branch, tenant, db,
            )
            db_exp_e = await _get_expense(uuid.UUID(expense_id))
            ok_e = (
                "error" in denied_update
                and db_exp_e is not None
                and db_exp_e.amount == amount_before_e
                and db_exp_e.amount != Decimal("999")
            )
            results.append((
                "e. update_expense denegado para usuario con FinancePermission de OTRA sucursal, sin modificar el gasto",
                ok_e, f"result={denied_update} amount_before={amount_before_e} amount_after={db_exp_e.amount if db_exp_e else None}",
            ))

            # ── f) sin acceso — trigger_recurring_expense_generation bloqueado por ROL ──
            denied_trigger = await execute_tool(
                "trigger_recurring_expense_generation", {}, asesor_no_permission, tenant, db,
            )
            ok_f = "error" in denied_trigger and "generated" not in denied_trigger
            results.append((
                "f. trigger_recurring_expense_generation bloqueado por rol (check_permission + _OWNER_TIER) para no-owner",
                ok_f, f"result={denied_trigger}",
            ))

            # ── g) OWNER — trigger_recurring_expense_generation funciona ────────
            allowed_trigger = await execute_tool(
                "trigger_recurring_expense_generation", {}, owner, tenant, db,
            )
            ok_g = "error" not in allowed_trigger and "generated" in allowed_trigger
            results.append((
                "g. trigger_recurring_expense_generation funciona para OWNER (sin error, devuelve 'generated')",
                ok_g, f"result={allowed_trigger}",
            ))

            # ── h) update_expense — status y deal_id (campos que faltaban) ──────
            deal_id_str = str(ctx["deal_id"])
            updated_h = await execute_tool(
                "update_expense",
                {"expense_id": expense_id, "status": "draft", "deal_id": deal_id_str},
                owner, tenant, db,
            )
            ok_h = (
                "error" not in updated_h
                and updated_h.get("status") == "draft"
                and updated_h.get("deal_id") == deal_id_str
                and float(updated_h.get("amount", 0)) == 750.0  # de (b), no tocado acá
                and updated_h.get("description") == "Renta de agosto"  # no tocado
                and updated_h.get("kind") == "fijo"  # no tocado
            )
            results.append((
                "h. update_expense aplica status='draft' y deal_id de verdad, sin pisar amount/description/kind",
                ok_h, f"updated={updated_h}",
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
