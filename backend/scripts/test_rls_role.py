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
      .venv/Scripts/python.exe scripts/test_rls_role.py

Verificaciones:
  A. Sin app.current_tenant_id seteado, un SELECT sin WHERE en `leads`
     (tabla con RLS) no devuelve filas.
  B. Con app.current_tenant_id apuntando a un tenant inexistente, tampoco.
  C. Con app.current_tenant_id apuntando a un tenant real con datos, un
     SELECT sin WHERE devuelve SOLO filas de ese tenant — nunca de otros.
  D. walix_app recibe un error de permisos al intentar ALTER TABLE (prueba
     de que no tiene privilegios de DDL/admin).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

WALIX_APP_URL = os.environ.get("WALIX_APP_DATABASE_URL")


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


async def _pick_a_real_tenant_with_leads() -> str | None:
    """Usa la conexión admin normal de la app (settings.effective_database_url)
    solo para DESCUBRIR un tenant_id real con datos — no para verificar RLS."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text("SELECT tenant_id FROM leads GROUP BY tenant_id HAVING COUNT(*) > 0 LIMIT 1")
            )
        ).scalar_one_or_none()
        return str(row) if row else None


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
            "       .venv/Scripts/python.exe scripts/test_rls_role.py\n"
        )
        return 1

    tenant_id = await _pick_a_real_tenant_with_leads()
    if tenant_id is None:
        print("\n✗ No se encontró ningún tenant con leads en esta DB — no hay datos con qué verificar aislamiento.")
        return 1

    fake_tenant_id = str(uuid.uuid4())
    engine = create_async_engine(_async_url(WALIX_APP_URL), pool_pre_ping=True)
    results: list[tuple[str, bool, str]] = []

    try:
        # Todas las verificaciones corren dentro de una transacción que
        # SIEMPRE se revierte al final (incluso si algo "funciona" cuando no
        # debería, como el ALTER TABLE de D) — este script es de solo
        # lectura por diseño, nunca deja efectos persistentes.

        # ── A + B: sin contexto / contexto inexistente → 0 filas ─────────────
        for label, tid in [
            ("A. Sin app.current_tenant_id seteado", None),
            ("B. app.current_tenant_id = tenant inexistente", fake_tenant_id),
        ]:
            async with engine.connect() as conn:
                trans = await conn.begin()
                try:
                    if tid is not None:
                        await conn.execute(
                            text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": tid}
                        )
                    count = (await conn.execute(text("SELECT COUNT(*) FROM leads"))).scalar_one()
                finally:
                    await trans.rollback()
                ok = count == 0
                results.append((label, ok, f"COUNT(*) = {count} (esperado 0)"))

        # ── C: contexto real → solo filas de ese tenant ───────────────────────
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": tenant_id}
                )
                own_count = (await conn.execute(text("SELECT COUNT(*) FROM leads"))).scalar_one()
                other_count = (
                    await conn.execute(
                        text("SELECT COUNT(*) FROM leads WHERE tenant_id != :tid"), {"tid": tenant_id}
                    )
                ).scalar_one()
            finally:
                await trans.rollback()
            ok = own_count > 0 and other_count == 0
            results.append((
                "C. app.current_tenant_id = tenant real",
                ok,
                f"propias={own_count} (>0 esperado), de-otros-tenants={other_count} (0 esperado)",
            ))

        # ── D: sin privilegios de DDL ──────────────────────────────────────────
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
        status = "PASS" if ok else "FAIL"
        all_ok = all_ok and ok
        print(f"  [{status}] {label}\n         {detail}")

    print()
    if all_ok:
        print("✓ Todas las verificaciones pasaron — walix_app está correctamente configurado.")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba antes de repuntar DATABASE_URL en Railway.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
