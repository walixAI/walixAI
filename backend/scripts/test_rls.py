"""test_rls.py — Verifica que las políticas RLS funcionan correctamente.

Crea un rol temporal sin privilegios de superusuario para simular el usuario
de aplicación (walix_app). Ejecuta queries con diferentes valores de
app.current_tenant_id y verifica el aislamiento entre tenants.

Uso:
    python scripts/test_rls.py

Requisitos:
    · La migración h4i5j6k7l8m9 debe estar aplicada (alembic upgrade head).
    · DATABASE_URL debe apuntar a un usuario con privilegios de superusuario
      (para poder hacer SET ROLE y crear el rol de prueba).
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal


# ── Helpers ───────────────────────────────────────────────────────────────────

_TEST_ROLE = "rls_verifier"
_PASS = "✅ PASS"
_FAIL = "❌ FAIL"


def _async_dsn(url: str) -> str:
    """Convert SQLAlchemy URL to asyncpg DSN."""
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def result(label: str, ok: bool) -> None:
    print(f"  {_PASS if ok else _FAIL}  {label}")


# ── Setup / teardown ──────────────────────────────────────────────────────────

async def setup_test_role(conn: asyncpg.Connection) -> None:
    """Create a non-superuser role for RLS testing."""
    await conn.execute(f"DROP ROLE IF EXISTS {_TEST_ROLE}")
    await conn.execute(
        f"CREATE ROLE {_TEST_ROLE} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN"
        f" PASSWORD 'rls_test_only'"
    )
    await conn.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_TEST_ROLE}"
    )
    await conn.execute(
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_TEST_ROLE}"
    )


async def cleanup_test_role(conn: asyncpg.Connection) -> None:
    await conn.execute(f"DROP ROLE IF EXISTS {_TEST_ROLE}")


async def create_test_data() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """
    Inserta dos tenants con sus branches y un lead cada uno.
    Devuelve (tenant_a_id, branch_a_id, lead_a_id, tenant_b_id, branch_b_id, lead_b_id).
    """
    from app.models.lead import Lead, LeadStatus
    from app.models.tenant import Branch, Company, Tenant, TenantPlan

    async with AsyncSessionLocal() as db:
        # Tenant A
        ta = Tenant(
            name="RLS Test Tenant A",
            email=f"rls-a-{uuid.uuid4().hex[:6]}@test.walix",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(ta)
        await db.flush()

        ca = Company(tenant_id=ta.id, name="Empresa A")
        db.add(ca)
        await db.flush()

        ba = Branch(
            company_id=ca.id,
            tenant_id=ta.id,
            name="Sucursal A",
            is_active=True,
        )
        db.add(ba)
        await db.flush()

        la = Lead(
            branch_id=ba.id,
            tenant_id=ta.id,
            wa_phone=f"+5215500{uuid.uuid4().int % 10_000_000:07d}",
            name="Lead Tenant A",
            status=LeadStatus.NUEVO,
        )
        db.add(la)
        await db.flush()

        # Tenant B
        tb = Tenant(
            name="RLS Test Tenant B",
            email=f"rls-b-{uuid.uuid4().hex[:6]}@test.walix",
            plan=TenantPlan.STARTER,
            is_active=True,
        )
        db.add(tb)
        await db.flush()

        cb = Company(tenant_id=tb.id, name="Empresa B")
        db.add(cb)
        await db.flush()

        bb = Branch(
            company_id=cb.id,
            tenant_id=tb.id,
            name="Sucursal B",
            is_active=True,
        )
        db.add(bb)
        await db.flush()

        lb = Lead(
            branch_id=bb.id,
            tenant_id=tb.id,
            wa_phone=f"+5215511{uuid.uuid4().int % 10_000_000:07d}",
            name="Lead Tenant B",
            status=LeadStatus.NUEVO,
        )
        db.add(lb)

        await db.commit()
        return ta.id, ba.id, la.id, tb.id, bb.id, lb.id


async def cleanup_test_data(
    ta_id: uuid.UUID, tb_id: uuid.UUID
) -> None:
    """Elimina todos los datos de los tenants de prueba (cascade handles children)."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM tenants WHERE id IN (:a, :b)"),
            {"a": ta_id, "b": tb_id},
        )
        await db.commit()


# ── Verificaciones ────────────────────────────────────────────────────────────

async def run_verifications(
    conn: asyncpg.Connection,
    ta_id: uuid.UUID,
    ba_id: uuid.UUID,
    la_id: uuid.UUID,
    tb_id: uuid.UUID,
    bb_id: uuid.UUID,
    lb_id: uuid.UUID,
) -> int:
    """Ejecuta las verificaciones como rls_verifier. Retorna número de fallos."""
    failures = 0

    # Cambiar al rol sin privilegios — sujeto a RLS
    await conn.execute(f"SET ROLE {_TEST_ROLE}")

    # ── Verificación 1: SELECT con tenant_A solo retorna leads de tenant_A ────

    await conn.execute(
        f"SELECT set_config('app.current_tenant_id', '{ta_id}', FALSE)"
    )
    rows_a = await conn.fetch("SELECT id FROM leads WHERE name LIKE 'Lead Tenant %'")
    ids_a = {str(r["id"]) for r in rows_a}
    ok1 = str(la_id) in ids_a and str(lb_id) not in ids_a
    result("SELECT con tenant_A retorna solo leads de tenant_A", ok1)
    if not ok1:
        failures += 1
        print(f"       ids obtenidos: {ids_a}")
        print(f"       esperado lead_a={la_id}, NO lead_b={lb_id}")

    # ── Verificación 2: SELECT con tenant_B solo retorna leads de tenant_B ────

    await conn.execute(
        f"SELECT set_config('app.current_tenant_id', '{tb_id}', FALSE)"
    )
    rows_b = await conn.fetch("SELECT id FROM leads WHERE name LIKE 'Lead Tenant %'")
    ids_b = {str(r["id"]) for r in rows_b}
    ok2 = str(lb_id) in ids_b and str(la_id) not in ids_b
    result("SELECT con tenant_B retorna solo leads de tenant_B", ok2)
    if not ok2:
        failures += 1
        print(f"       ids obtenidos: {ids_b}")
        print(f"       esperado lead_b={lb_id}, NO lead_a={la_id}")

    # ── Verificación 3: INSERT con tenant_id incorrecto es rechazado ──────────

    await conn.execute(
        f"SELECT set_config('app.current_tenant_id', '{ta_id}', FALSE)"
    )
    cross_tenant_blocked = False
    try:
        # Intentar insertar un lead con tenant_id = tenant_B (cross-tenant)
        await conn.execute(
            "INSERT INTO leads (id, branch_id, tenant_id, wa_phone, name, status)"
            " VALUES ($1, $2, $3, $4, 'Intruso', 'nuevo')",
            uuid.uuid4(),
            bb_id,   # branch de tenant_B
            tb_id,   # tenant_id = tenant_B — debe fallar con tenant_A activo
            f"+5215599{uuid.uuid4().int % 10_000_000:07d}",
        )
    except Exception as exc:
        cross_tenant_blocked = True
        if "rls" in str(exc).lower() or "policy" in str(exc).lower() or "check" in str(exc).lower():
            pass  # error esperado de RLS
        else:
            print(f"       (excepción distinta a RLS: {exc})")
    result("INSERT con tenant_id ajeno es rechazado por la policy", cross_tenant_blocked)
    if not cross_tenant_blocked:
        failures += 1
        print("       El INSERT no lanzó error — la policy WITH CHECK no está activa.")

    # ── Verificación 4: SELECT sin tenant_id configurado retorna 0 filas ──────

    await conn.execute("SELECT set_config('app.current_tenant_id', '00000000-0000-0000-0000-000000000000', FALSE)")
    rows_none = await conn.fetch("SELECT id FROM leads WHERE name LIKE 'Lead Tenant %'")
    ok4 = len(rows_none) == 0
    result("SELECT con NULL_UUID retorna 0 filas (aislamiento total)", ok4)
    if not ok4:
        failures += 1
        print(f"       Se obtuvieron {len(rows_none)} filas; se esperaban 0.")

    # Restaurar rol admin
    await conn.execute("RESET ROLE")

    # ── Verificación 5 (admin): ambos leads existen en la BD ─────────────────

    rows_admin = await conn.fetch(
        "SELECT id FROM leads WHERE name LIKE 'Lead Tenant %'"
    )
    ids_admin = {str(r["id"]) for r in rows_admin}
    ok5 = str(la_id) in ids_admin and str(lb_id) in ids_admin
    result("Admin (superuser) ve todos los leads sin filtro RLS", ok5)
    if not ok5:
        failures += 1

    return failures


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n══════════════════════════════════════════════════════")
    print("  WALIX — Verificación de Row-Level Security (RLS)")
    print("══════════════════════════════════════════════════════\n")

    dsn = _async_dsn(settings.effective_database_url)

    ta_id = tb_id = None
    conn = None
    exit_code = 0

    try:
        print("→ Conectando a la base de datos...")
        conn = await asyncpg.connect(dsn)

        print("→ Creando rol de prueba sin privilegios de superusuario...")
        await setup_test_role(conn)

        print("→ Insertando datos de prueba (dos tenants con un lead cada uno)...")
        ta_id, ba_id, la_id, tb_id, bb_id, lb_id = await create_test_data()
        print(f"  Tenant A: {ta_id}  |  Lead A: {la_id}")
        print(f"  Tenant B: {tb_id}  |  Lead B: {lb_id}\n")

        print("→ Ejecutando verificaciones RLS:\n")
        failures = await run_verifications(conn, ta_id, ba_id, la_id, tb_id, bb_id, lb_id)

        print()
        if failures == 0:
            print("✅  Todas las verificaciones pasaron — RLS funciona correctamente.\n")
        else:
            print(f"❌  {failures} verificación(es) fallaron — revisa las políticas RLS.\n")
            exit_code = 1

    except Exception as exc:
        print(f"\n❌  Error durante la verificación: {exc}")
        import traceback
        traceback.print_exc()
        exit_code = 1

    finally:
        print("→ Limpiando datos y rol de prueba...")
        if conn:
            try:
                await conn.execute("RESET ROLE")  # asegurar que somos admin
            except Exception:
                pass
            await cleanup_test_role(conn)
            await conn.close()

        if ta_id and tb_id:
            try:
                await cleanup_test_data(ta_id, tb_id)
                print("  Datos de prueba eliminados.")
            except Exception as exc:
                print(f"  Advertencia: limpieza parcial — {exc}")

        print()

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
