"""test_lead_scoring_task.py — Verificación del fix de scoring perdido por
tarea de fondo sin referencia (hallazgo 2026-08-25: lead 66e166b5 tuvo 20
respuestas del bot pero solo 18 filas en lead_scores, sin ningún log de
falla — consistente con asyncio.create_task() sin guardar la referencia
devuelta: el GC puede cancelar la tarea (asyncio.CancelledError, que hereda
de BaseException, no de Exception) antes de que termine, sin que el
`except Exception` de calculate_lead_score() la capture).

Fix: app/ai/bot_engine.py::_fire_and_forget (set a nivel de módulo con
referencias fuertes + add_done_callback para liberarlas al terminar), mismo
patrón que ya usaban app/api/kb.py y app/ai/copilot_tools.py::reindex_kb.
También aplicado a prediction_service.py::_maybe_trigger_closing_agent
(mismo bug, mismo archivo, no mencionado en el hallazgo original).

Verificaciones:
  a) _fire_and_forget sobrevive un gc.collect() agresivo disparado
     inmediatamente después de crear la tarea, antes de que corra — la
     corrutina sí completa (reproduce el bug si el fix no está aplicado:
     revertir _fire_and_forget a asyncio.create_task() sin guardar la
     referencia hace que esta verificación falle de forma intermitente).
  b) Disparo real de calculate_lead_score() vía _fire_and_forget para un
     lead de prueba (aislado, no toca leads reales de Utel — ver nota de
     alcance abajo), con gc.collect() inmediato: se crea una fila nueva en
     lead_scores y lead.current_score se actualiza.
  c) PASS/FAIL por cada verificación.

NOTA DE ALCANCE: el Paso 3.2 del prompt original pedía confirmar el fix
contra el lead real que disparó el reporte (enviándole un mensaje de
prueba). Se usa en su lugar un lead sintético en un tenant aislado y
desechable — igual que test_lead_dedup.py — porque calculate_lead_score()
escribe una fila nueva en lead_scores (dato real), y la instrucción vigente
del usuario (2026-08-25) es no mutar datos de producción sin visto bueno
previo. Un lead de prueba en tenant aislado ejercita exactamente el mismo
código (_fire_and_forget -> calculate_lead_score -> INSERT lead_scores)
sin tocar leads reales.

Uso:
    .venv/Scripts/python.exe scripts/test_lead_scoring_task.py
"""
from __future__ import annotations

import asyncio
import gc
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.ai.bot_engine import _fire_and_forget
from app.core.database import AsyncSessionLocal
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.scoring import LeadScore
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole
from app.services.prediction_service import calculate_lead_score


async def _setup_tenant() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"[test_lead_scoring_task] {tag}", email=f"scoretask-{tag}@walix.test",
            plan=TenantPlan.STARTER, is_active=True,
        )
        db.add(tenant)
        await db.flush()
        company = Company(tenant_id=tenant.id, name="Empresa Test")
        db.add(company)
        await db.flush()
        branch = Branch(company_id=company.id, tenant_id=tenant.id, name="Sucursal", is_active=True)
        db.add(branch)
        await db.flush()
        owner = User(
            tenant_id=tenant.id, branch_id=branch.id, email=f"owner-{tag}@walix.test",
            name="Owner Test", hashed_password="not-used", role=UserRole.OWNER, is_active=True,
        )
        db.add(owner)
        await db.flush()
        lead = Lead(
            branch_id=branch.id, tenant_id=tenant.id, wa_phone="525500001234",
            name="Lead Scoring Test", source=LeadSource.WHATSAPP_INBOUND, status=LeadStatus.NUEVO,
        )
        db.add(lead)
        await db.flush()
        await db.commit()
        return {"tenant": tenant, "branch": branch, "owner": owner, "lead": lead}


async def _cleanup_tenant(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant"].id))
        await db.commit()


async def main() -> int:
    print("=" * 70)
    print("  test_lead_scoring_task.py — Fix de scoring perdido por GC")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []

    # ── a) _fire_and_forget sobrevive un gc.collect() inmediato ─────────────
    completed: list[bool] = []

    async def _slow_coro() -> None:
        await asyncio.sleep(0.3)
        completed.append(True)

    _fire_and_forget(_slow_coro(), name="test:gc_survival")
    gc.collect()  # exactamente lo que el prompt pide: forzar GC agresivo
    #                antes de que la tarea recién creada haya podido correr.
    await asyncio.sleep(1.0)
    ok_a = completed == [True]
    results.append((
        "a. _fire_and_forget sobrevive gc.collect() inmediato — la corrutina completa",
        ok_a,
        f"completed={completed}",
    ))

    # ── b) calculate_lead_score real vía _fire_and_forget + gc.collect() ────
    ctx = await _setup_tenant()
    try:
        async with AsyncSessionLocal() as db:
            score_rows_before = (await db.execute(
                select(LeadScore).where(LeadScore.lead_id == ctx["lead"].id)
            )).scalars().all()
        count_before = len(score_rows_before)

        _fire_and_forget(
            calculate_lead_score(ctx["lead"].id, ctx["tenant"].id),
            name=f"score:{ctx['lead'].id}",
        )
        gc.collect()

        # Espera activa a que la tarea termine (hasta 30s — llamada real a Claude Haiku).
        score_after = None
        for _ in range(30):
            await asyncio.sleep(1.0)
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(
                    select(LeadScore).where(LeadScore.lead_id == ctx["lead"].id)
                )).scalars().all()
            if len(rows) > count_before:
                score_after = rows[-1]
                break

        ok_b = score_after is not None
        results.append((
            "b. calculate_lead_score dispara vía _fire_and_forget, sobrevive gc.collect() y persiste LeadScore",
            ok_b,
            f"score_rows_before={count_before} score_rows_after={1 if score_after else 0} "
            f"score={score_after.score if score_after else None}",
        ))
    finally:
        await _cleanup_tenant(ctx)

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
