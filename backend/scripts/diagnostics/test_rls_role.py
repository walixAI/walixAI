"""test_rls_role.py — Verificación end-to-end del rol walix_app + RLS.

A diferencia de backend/tests/regression/test_multi_tenancy.py (que
impersona walix_app vía `SET LOCAL ROLE` desde la conexión admin de la
suite, para no depender de credenciales reales — ver el docstring de ese
módulo), este script abre una conexión REAL como walix_app, con su
contraseña real, para validar que el setup de scripts/setup_db_user.py
efectivamente funciona de punta a punta en el entorno que estés probando.

Corré esto DESPUÉS de:
  1. Ejecutar el SQL que imprime scripts/setup_db_user.py en la consola SQL
     de Railway del entorno que estés probando (dev primero).
  2. Setear la variable de entorno WALIX_APP_DATABASE_URL con la connection
     string real de walix_app — NUNCA hardcodear la password acá ni en
     ningún archivo del repo.

Uso:
    WALIX_APP_DATABASE_URL="postgresql://walix_app:TU_PASSWORD@host:puerto/railway" \\
      .venv/Scripts/python.exe scripts/diagnostics/test_rls_role.py

Verificaciones, por cada tabla en RLS_TABLES (A/B/C) — D corre una sola vez:
  A. Sin app.current_tenant_id seteado, un SELECT sin WHERE no devuelve filas.
  B. Con app.current_tenant_id apuntando a un tenant inexistente, tampoco.
  C. Con app.current_tenant_id apuntando a un tenant real con datos, un
     SELECT sin WHERE devuelve SOLO filas de ese tenant — nunca de otros.
     Si la tabla no tiene ninguna fila en este entorno, se omite (SKIP) —
     no es una falla, solo no hay datos con qué verificar aislamiento.
  D. walix_app recibe un error de permisos al intentar ALTER TABLE (prueba
     de que no tiene privilegios de DDL/admin) — se corre una sola vez,
     no depende de ninguna tabla en particular.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

WALIX_APP_URL = os.environ.get("WALIX_APP_DATABASE_URL")

# Todas las tablas con RLS a esta fecha — leads (cutover original, 832e6af)
# + las 5 pendientes cerradas en la migración p1q2r3s4t5u6.
RLS_TABLES = [
    "leads",
    "ai_memory_events",
    "ai_entity_context",
    "expenses",
    "subscriptions",
    "failed_payments",
]


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


async def _pick_a_real_tenant_with_rows(table: str) -> str | None:
    """Usa la conexión admin normal de la app (settings.effective_database_url)
    solo para DESCUBRIR un tenant_id real con datos en `table` — no para
    verificar RLS."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text(f"SELECT tenant_id FROM {table} GROUP BY tenant_id HAVING COUNT(*) > 0 LIMIT 1")  # noqa: S608 — table viene de RLS_TABLES, no de input externo
            )
        ).scalar_one_or_none()
        return str(row) if row else None


async def _check_table(engine, table: str, fake_tenant_id: str) -> list[tuple[str, bool | None, str]]:
    results: list[tuple[str, bool | None, str]] = []
    tenant_id = await _pick_a_real_tenant_with_rows(table)

    # ── A + B: sin contexto / contexto inexistente → 0 filas ─────────────────
    for label, tid in [
        (f"{table} — A. Sin app.current_tenant_id seteado", None),
        (f"{table} — B. app.current_tenant_id = tenant inexistente", fake_tenant_id),
    ]:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                if tid is not None:
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": tid}
                    )
                count = (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()  # noqa: S608
            finally:
                await trans.rollback()
            ok = count == 0
            results.append((label, ok, f"COUNT(*) = {count} (esperado 0)"))

    # ── C: contexto real → solo filas de ese tenant ───────────────────────────
    label_c = f"{table} — C. app.current_tenant_id = tenant real"
    if tenant_id is None:
        results.append((label_c, None, f"SKIP — {table} no tiene ninguna fila en este entorno"))
    else:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": tenant_id}
                )
                own_count = (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()  # noqa: S608
                other_count = (
                    await conn.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id != :tid"), {"tid": tenant_id}  # noqa: S608
                    )
                ).scalar_one()
            finally:
                await trans.rollback()
            ok = own_count > 0 and other_count == 0
            results.append((
                label_c, ok,
                f"propias={own_count} (>0 esperado), de-otros-tenants={other_count} (0 esperado)",
            ))

    return results


async def main() -> int:
    print("=" * 70)
    print("  test_rls_role.py — verificación end-to-end de walix_app + RLS")
    print("=" * 70)

    if not WALIX_APP_URL:
        print(
            "\n✗ Falta la variable de entorno WALIX_APP_DATABASE_URL.\n\n"
            "  1. Corré `python scripts/setup_db_user.py` y aplicá el SQL en la\n"
            "     consola de Railway del entorno que quieras probar.\n"
            "  2. Volvé a correr esto con:\n\n"
            "     WALIX_APP_DATABASE_URL=\"postgresql://walix_app:TU_PASSWORD@host:puerto/railway\" \\\n"
            "       .venv/Scripts/python.exe scripts/diagnostics/test_rls_role.py\n"
        )
        return 1

    fake_tenant_id = str(uuid.uuid4())
    engine = create_async_engine(_async_url(WALIX_APP_URL), pool_pre_ping=True)
    results: list[tuple[str, bool | None, str]] = []

    try:
        # Todas las verificaciones corren dentro de una transacción que
        # SIEMPRE se revierte al final (incluso si algo "funciona" cuando no
        # debería, como el ALTER TABLE de D) — este script es de solo
        # lectura por diseño, nunca deja efectos persistentes.
        for table in RLS_TABLES:
            results.extend(await _check_table(engine, table, fake_tenant_id))

        # ── D: sin privilegios de DDL (una sola vez, sobre `leads`) ───────────
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                try:
                    await conn.execute(text("ALTER TABLE leads ADD COLUMN _rls_role_smoke_test INTEGER"))
                    ddl_blocked = False
                    detail = "ALTER TABLE se ejecutó — walix_app SÍ tiene privilegios de DDL (mal)"
                except Exception as e:  # noqa: BLE001 — cualquier excepción acá = bloqueado, que es lo esperado
                    ddl_blocked = True
                    detail = f"bloqueado correctamente ({type(e).__name__})"
            finally:
                await trans.rollback()
            results.append(("D. walix_app NO puede ALTER TABLE", ddl_blocked, detail))

    finally:
        await engine.dispose()

    print()
    all_ok = True
    for label, ok, detail in results:
        status_tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        if ok is False:
            all_ok = False
        print(f"  [{status_tag}] {label}\n         {detail}")

    print()
    if all_ok:
        print("✓ Todas las verificaciones pasaron (SKIP no cuenta como falla) — walix_app está correctamente configurado.")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba antes de repuntar DATABASE_URL en Railway.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
