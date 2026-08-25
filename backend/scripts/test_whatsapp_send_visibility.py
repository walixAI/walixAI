"""test_whatsapp_send_visibility.py — Verificación del fix de observabilidad
para envíos de WhatsApp fallidos (hallazgo 2026-08-25: "el bot no envía la
respuesta de WhatsApp").

Diagnóstico (Paso 1 del prompt): el token, las credenciales y el número de
Utel funcionan correctamente — confirmado con 2 envíos reales en vivo
(status 200 + wamid, mensaje recibido). El problema real no es Meta ni el
código de envío en sí: es que un fallo (síncrono, vía el valor de retorno
de send_text_message(), o asíncrono, vía value.statuses del webhook) no
dejaba NINGÚN rastro visible dentro de Walix — solo en logs de Railway, si
acaso. Este test verifica el fix de observabilidad (Paso 3), no el envío
en sí (ya confirmado real y funcional en el diagnóstico).

Verificaciones:
  a) send_text_message() devuelve False (mockeado) → se crea una Activity
     (activity_type="system") en el lead con la fila esperada.
  b) send_text_message() devuelve True (mockeado) → NO se crea ninguna
     Activity de fallo (regression guard, evita ruido en el caso exitoso).
  c) PASS/FAIL por cada verificación.

No se mockea Claude ni el resto del pipeline — solo whatsapp_service, el
único punto que ya sabemos (por el diagnóstico) que funciona bien en
producción y cuyo comportamiento real no es lo que este test verifica.

Uso:
    .venv/Scripts/python.exe scripts/test_whatsapp_send_visibility.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.ai.bot_engine import _process_message_inner
from app.core.database import AsyncSessionLocal
from app.models.activity import Activity
from app.models.deal import Deal  # noqa: F401 — registers `deals` so Activity.deal_id's FK resolves at flush
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

FAIL_DESCRIPTION = "Envío de WhatsApp falló (ver logs de Railway para el detalle de Meta)"


async def _setup_tenant() -> dict:
    async with AsyncSessionLocal() as db:
        tag = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"[test_wa_send_visibility] {tag}", email=f"wasend-{tag}@walix.test",
            plan=TenantPlan.STARTER, is_active=True,
        )
        db.add(tenant)
        await db.flush()
        company = Company(tenant_id=tenant.id, name="Empresa Test")
        db.add(company)
        await db.flush()
        branch = Branch(
            company_id=company.id, tenant_id=tenant.id, name="Sucursal", is_active=True,
            wa_phone_number_id="000000000000", wa_token="fake-token-not-used-mocked",
        )
        db.add(branch)
        await db.flush()
        owner = User(
            tenant_id=tenant.id, branch_id=branch.id, email=f"owner-{tag}@walix.test",
            name="Owner Test", hashed_password="not-used", role=UserRole.OWNER, is_active=True,
        )
        db.add(owner)
        await db.flush()
        await db.commit()
        return {"tenant": tenant, "branch": branch, "owner": owner}


async def _cleanup_tenant(ctx: dict) -> None:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        # activities.tenant_id has no ondelete=CASCADE — clear explicitly first.
        await db.execute(delete(Activity).where(Activity.tenant_id == ctx["tenant"].id))
        await db.execute(delete(Tenant).where(Tenant.id == ctx["tenant"].id))
        await db.commit()


async def _run_message(ctx: dict, wa_phone: str, send_result: bool) -> None:
    with patch(
        "app.ai.bot_engine.whatsapp_service.send_text_message",
        new=AsyncMock(return_value=send_result),
    ):
        await _process_message_inner(
            wa_phone=wa_phone,
            message_body="Hola, quiero información",
            branch_id=ctx["branch"].id,
            tenant_id=ctx["tenant"].id,
            message_id=f"wamid.TEST_{uuid.uuid4().hex[:16]}",
        )


async def _fail_activities_for(tenant_id: uuid.UUID) -> list[Activity]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Activity).where(
                Activity.tenant_id == tenant_id,
                Activity.activity_type == "system",
                Activity.body == FAIL_DESCRIPTION,
            )
        )).scalars().all()
        return list(rows)


async def main() -> int:
    print("=" * 70)
    print("  test_whatsapp_send_visibility.py — Observabilidad de envíos fallidos")
    print("=" * 70)

    results: list[tuple[str, bool, str]] = []
    ctx = await _setup_tenant()
    try:
        # ── a) send_text_message devuelve False -> se crea la Activity ──────────
        await _run_message(ctx, "525500001111", send_result=False)
        fail_rows_a = await _fail_activities_for(ctx["tenant"].id)
        ok_a = len(fail_rows_a) == 1
        results.append((
            "a. send_text_message()=False crea una Activity(system) de fallo en el lead",
            ok_a,
            f"activities_creadas={len(fail_rows_a)} body={fail_rows_a[0].body if fail_rows_a else None}",
        ))

        # ── b) send_text_message devuelve True -> NO se crea ninguna de fallo ───
        await _run_message(ctx, "525500002222", send_result=True)
        fail_rows_b = await _fail_activities_for(ctx["tenant"].id)
        # Debe seguir habiendo solo la 1 de la verificación (a) — ninguna nueva.
        ok_b = len(fail_rows_b) == 1
        results.append((
            "b. send_text_message()=True NO crea Activity de fallo (regression guard)",
            ok_b,
            f"activities_de_fallo_totales_tras_envio_exitoso={len(fail_rows_b)} (debe seguir en 1, no 2)",
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
