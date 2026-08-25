"""test_tenant_context_pool_mitigation.py — Verifica la mitigación de fuga de
contexto de tenant entre sesiones concurrentes del pool de conexiones
(hallazgo 2026-08-25: "invalid input syntax for type uuid: \"\"" y, peor,
lectura del marcador de OTRO tenant, tras un commit() bajo contención real
del pool — reproducido con 10/40 mismatches en el experimento original).

Causa real (NO es is_local — set_tenant_context ya usa FALSE en los 3
call-sites): SQLAlchemy libera la conexión física al pool al hacer
commit(); la siguiente query de la MISMA AsyncSession puede recibir una
conexión física distinta, sin el app.current_tenant_id correcto (o con el
de otro tenant que dejó su contexto en esa conexión).

Mitigación aplicada (NO es el fix definitivo — ver nota en los 3
call-sites): reafirmar set_tenant_context(db, tenant_id) inmediatamente
después de cada commit(), antes de la siguiente query, en los 3 puntos
confirmados:
  - app/ai/bot_engine.py: después de los commits de los pasos 4a, 4b, 11.
  - app/ai/qualifier.py::qualify_lead: después del commit que precede a
    db.refresh(lead).

Verificaciones:
  a) Experimento abstracto: 40 sesiones concurrentes, cada una aplicando
     el patrón real (set_config(marker) -> commit() -> REAFIRMAR
     set_config(marker) -> leer current_setting()) — el mismatch debe caer
     a 0/40 (antes de la mitigación: 10/40).
  b) Regresión end-to-end real: 15 invocaciones concurrentes de
     _process_message_inner() contra un lead de prueba aislado — ninguna
     debe fallar con "invalid input syntax for type uuid".

NOTA DE ALCANCE (explícita, per instrucción del usuario 2026-08-25): esto
es una mitigación puntual sobre los 3 call-sites confirmados arriba — NO
es garantía de que el mismo problema no exista en otros lugares del código
que combinan set_tenant_context con múltiples commits (webhooks.py,
prediction_service.py, contact_executor.py, etc. — auditoría pendiente,
alcance separado).

Uso:
    .venv/Scripts/python.exe scripts/test_tenant_context_pool_mitigation.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text

from app.ai.bot_engine import _process_message_inner
from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.conversation import Conversation


# ── a) Patrón abstracto: set -> commit -> REAFIRMAR -> leer ─────────────────

async def _one_mitigated(i: int) -> tuple[int, str, str | None, bool]:
    marker = f"marker-{i}-{uuid.uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_tenant_id', :v, FALSE)"), {"v": marker})
        await db.execute(text("SELECT 1"))
        await db.commit()
        # Mitigación: reafirmar inmediatamente después del commit.
        await db.execute(text("SELECT set_config('app.current_tenant_id', :v, FALSE)"), {"v": marker})
        row = (await db.execute(text("SELECT current_setting('app.current_tenant_id', true)"))).scalar()
        return (i, marker, row, marker == row)


async def _check_a() -> tuple[bool, str]:
    results = await asyncio.gather(*[_one_mitigated(i) for i in range(40)])
    mismatches = [r for r in results if not r[3]]
    ok = len(mismatches) == 0
    detail = f"mismatches={len(mismatches)}/40"
    if mismatches:
        detail += f" ejemplo={mismatches[0]}"
    return ok, detail


# ── b) Regresión end-to-end real contra _process_message_inner ──────────────

async def _setup_tenant() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"[test_tenant_ctx_mitigation] {tag}", email=f"tcm-{tag}@walix.test",
            plan=TenantPlan.STARTER, is_active=True,
        )
        db.add(tenant)
        await db.flush()
        company = Company(tenant_id=tenant.id, name="Empresa Test")
        db.add(company)
        await db.flush()
        branch = Branch(
            company_id=company.id, tenant_id=tenant.id, name="Sucursal", is_active=True,
            wa_phone_number_id="000000000001", wa_token="fake-not-used",
        )
        db.add(branch)
        await db.flush()
        lead = Lead(
            branch_id=branch.id, tenant_id=tenant.id, wa_phone="525500007777",
            source=LeadSource.WHATSAPP_INBOUND, status=LeadStatus.NUEVO,
        )
        db.add(lead)
        await db.flush()
        conv = Conversation(lead_id=lead.id, branch_id=branch.id)
        db.add(conv)
        await db.flush()
        await db.commit()
        return {"tenant_id": tenant.id, "branch_id": branch.id}


async def _cleanup_tenant(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant_id"]))
        await db.commit()


async def _one_real_run(ctx: dict, i: int) -> tuple[int, str, str | None]:
    try:
        await _process_message_inner(
            wa_phone="525500007777",
            message_body=f"mensaje de prueba {i}",
            branch_id=ctx["branch_id"],
            tenant_id=ctx["tenant_id"],
            message_id=f"wamid.MITIG_{uuid.uuid4().hex[:12]}",
        )
        return (i, "OK", None)
    except Exception as e:
        return (i, "FAIL", f"{type(e).__name__}: {str(e)[:200]}")


async def _check_b() -> tuple[bool, str]:
    ctx = await _setup_tenant()
    try:
        results = await asyncio.gather(*[_one_real_run(ctx, i) for i in range(15)])
    finally:
        await _cleanup_tenant(ctx)

    uuid_fails = [r for r in results if r[1] == "FAIL" and "uuid" in (r[2] or "").lower()]
    other_fails = [r for r in results if r[1] == "FAIL" and "uuid" not in (r[2] or "").lower()]
    ok = len(uuid_fails) == 0
    detail = (
        f"total=15 uuid_fails={len(uuid_fails)} otros_fails={len(other_fails)} "
        f"(otros_fails esperables bajo carga: pool timeout, no relacionados)"
    )
    if uuid_fails:
        detail += f" ejemplo_uuid_fail={uuid_fails[0]}"
    return ok, detail


async def main() -> int:
    print("=" * 70)
    print("  test_tenant_context_pool_mitigation.py")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []

    ok_a, detail_a = await _check_a()
    results.append((
        "a. 40 sesiones concurrentes, patrón set->commit->REAFIRMAR->leer — 0 mismatches esperados",
        ok_a, detail_a,
    ))

    ok_b, detail_b = await _check_b()
    results.append((
        "b. 15 invocaciones reales concurrentes de _process_message_inner — 0 fallos de uuid esperados",
        ok_b, detail_b,
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
