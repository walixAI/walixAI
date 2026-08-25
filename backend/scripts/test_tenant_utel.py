"""test_tenant_utel.py — Verificación del tenant "Universidad Utel" creado
administrativamente por scripts/admin/create_tenant_utel.py.

A diferencia de los scripts de scripts/diagnostics/, este NO usa un tenant
desechable ni lo borra al final — Utel es un tenant real de cliente. Solo
lee y verifica lo que ya existe en BD.

Verificaciones:
  a) El tenant existe con industry_key="educacion", entity_name="Prospecto".
  b) Hay exactamente 8 PipelineStage activas (is_archived=False), en el
     orden correcto, con los stage_keys esperados.
  c) La stage "enrolled" tiene is_won=True y "lost" tiene is_lost=True.
  d) No quedaron stages huérfanas del template "educacion" sin archivar
     (el set completo de stage_keys activas es EXACTAMENTE el esperado,
     ni de más ni de menos).
  e) Login del owner: verify_password (app/core/security.py) contra el
     hash guardado. Requiere el password en claro — se lo pasa por CLI o
     env var UTEL_OWNER_PASSWORD (el password real solo se imprimió una
     vez al crear el tenant, no queda guardado en ningún otro lado, así
     que este check no puede reconstruirlo por su cuenta). Si no se
     proporciona, se reporta SKIP, no FAIL.
  f) Con set_tenant_context(db, tenant.id) activo, un SELECT de
     PipelineStage sin filtro de tenant_id (RLS puro) solo devuelve las 8
     filas de Utel. Si existe un tenant de referencia distinto (ej. la
     clínica, admin@clinica.com), se confirma también que las filas de
     Utel son invisibles desde SU contexto de tenant (aislamiento
     bidireccional).

Uso:
    .venv/Scripts/python.exe scripts/test_tenant_utel.py [OWNER_PASSWORD]
    (o) UTEL_OWNER_PASSWORD=... .venv/Scripts/python.exe scripts/test_tenant_utel.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal, set_tenant_context
from app.core.security import verify_password
from app.models.pipeline import PipelineStage
from app.models.tenant import Tenant
from app.models.user import User, UserRole

TENANT_EMAIL = "admin@utel.walix.mx"
REFERENCE_TENANT_EMAIL = "admin@clinica.com"  # sembrado por scripts/seed.py, best-effort

EXPECTED_STAGES = [
    ("new", 1), ("profiling", 2), ("profiled", 3), ("appointment", 4),
    ("follow_up", 5), ("docs", 6), ("enrolled", 7), ("lost", 8),
]
EXPECTED_KEYS = {k for k, _ in EXPECTED_STAGES}


async def main() -> int:
    print("=" * 70)
    print("  test_tenant_utel.py — verificación del tenant Universidad Utel")
    print("=" * 70)

    results: list[tuple[str, str, str]] = []  # (label, PASS/FAIL/SKIP, detail)

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == TENANT_EMAIL)
        )).scalar_one_or_none()

        if tenant is None:
            print(f"\n✗ No existe ningún tenant con email {TENANT_EMAIL!r}.")
            print("  Correr primero scripts/admin/create_tenant_utel.py.")
            return 1

        # ── a) tenant existe con industry_key/entity_name correctos ─────────
        ok_a = tenant.industry_key == "educacion" and tenant.entity_name == "Prospecto"
        results.append((
            "a. tenant existe con industry_key='educacion', entity_name='Prospecto'",
            "PASS" if ok_a else "FAIL",
            f"industry_key={tenant.industry_key!r} entity_name={tenant.entity_name!r}",
        ))

        # ── b) exactamente 8 stages activas, orden y keys correctos ─────────
        active_stages = (await db.execute(
            select(PipelineStage).where(
                PipelineStage.tenant_id == tenant.id,
                PipelineStage.is_archived.is_(False),
            ).order_by(PipelineStage.order_index)
        )).scalars().all()
        actual_order = [(s.stage_key, s.order_index) for s in active_stages]
        ok_b = len(active_stages) == 8 and actual_order == EXPECTED_STAGES
        results.append((
            "b. exactamente 8 PipelineStage activas, en el orden/keys esperado",
            "PASS" if ok_b else "FAIL",
            f"actual={actual_order}",
        ))

        # ── c) enrolled.is_won / lost.is_lost ────────────────────────────────
        by_key = {s.stage_key: s for s in active_stages}
        enrolled = by_key.get("enrolled")
        lost = by_key.get("lost")
        ok_c = (
            enrolled is not None and enrolled.is_won is True
            and lost is not None and lost.is_lost is True
        )
        results.append((
            "c. stage 'enrolled' tiene is_won=True, 'lost' tiene is_lost=True",
            "PASS" if ok_c else "FAIL",
            f"enrolled.is_won={getattr(enrolled, 'is_won', 'N/A')} "
            f"lost.is_lost={getattr(lost, 'is_lost', 'N/A')}",
        ))

        # ── d) sin huérfanas del template "educacion" ────────────────────────
        actual_keys = {s.stage_key for s in active_stages}
        ok_d = actual_keys == EXPECTED_KEYS
        results.append((
            "d. el set de stage_keys activas es EXACTAMENTE el esperado (sin huérfanas)",
            "PASS" if ok_d else "FAIL",
            f"actual_keys={sorted(actual_keys)} expected_keys={sorted(EXPECTED_KEYS)}",
        ))

        # ── e) login del owner ────────────────────────────────────────────────
        owner = (await db.execute(
            select(User).where(User.email == TENANT_EMAIL, User.role == UserRole.OWNER)
        )).scalar_one_or_none()
        owner_password = (
            sys.argv[1] if len(sys.argv) > 1 else os.environ.get("UTEL_OWNER_PASSWORD")
        )
        if owner is None:
            results.append(("e. login del owner (verify_password)", "FAIL", "usuario owner no encontrado"))
        elif not owner_password:
            results.append((
                "e. login del owner (verify_password)",
                "SKIP",
                "no se proporcionó el password en claro (CLI arg o UTEL_OWNER_PASSWORD)",
            ))
        else:
            ok_e = verify_password(owner_password, owner.hashed_password)
            results.append((
                "e. login del owner (verify_password contra el hash guardado)",
                "PASS" if ok_e else "FAIL",
                f"owner_id={owner.id}",
            ))

        # ── f) aislamiento RLS ────────────────────────────────────────────────
        reference_tenant = (await db.execute(
            select(Tenant).where(Tenant.email == REFERENCE_TENANT_EMAIL)
        )).scalar_one_or_none()

    # Sesión nueva para el chequeo de RLS — set_tenant_context debe ser lo
    # primero que corre en la sesión, antes de cualquier query protegida.
    async with AsyncSessionLocal() as db_rls:
        bypassrls = (await db_rls.execute(text(
            "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ))).scalar_one_or_none()

        if bypassrls:
            # El rol de conexión (current_user) tiene BYPASSRLS — Postgres
            # ignora FORCE ROW LEVEL SECURITY para ese rol sin importar las
            # políticas. Esto es una característica preexistente de ESTE
            # entorno (DATABASE_URL usa el rol "postgres"), no algo que este
            # prompt haya tocado ni algo específico del tenant Utel — no se
            # puede verificar aislamiento por comportamiento con este rol.
            # Se verifica en su lugar que la POLICY en sí está bien definida
            # (misma cláusula qual que usan todas las demás tablas RLS de la
            # app), como evidencia indirecta de que el aislamiento SÍ
            # funcionaría con un rol de aplicación sin BYPASSRLS.
            policy_row = (await db_rls.execute(text(
                "SELECT qual FROM pg_policies "
                "WHERE tablename = 'pipeline_stages' AND policyname = 'tenant_isolation_select'"
            ))).scalar_one_or_none()
            expected_qual = "(tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)"
            ok_f = policy_row == expected_qual
            detail_f = (
                f"current_user tiene BYPASSRLS=True en este entorno (DATABASE_URL usa el rol "
                f"'postgres') — Postgres ignora RLS para ese rol, así que un SELECT real no "
                f"prueba aislamiento acá (no es un problema de este tenant ni de este prompt, "
                f"es infraestructura preexistente). Se verificó en su lugar que la policy "
                f"tenant_isolation_select de pipeline_stages tiene la cláusula correcta: "
                f"{'coincide' if ok_f else 'NO coincide'} con lo esperado ({expected_qual!r}, "
                f"encontrado {policy_row!r}). El aislamiento real hoy lo dan los filtros "
                f"explícitos tenant_id==... que usa cada query de la app, no RLS con este rol."
            )
        else:
            await set_tenant_context(db_rls, tenant.id)
            rows_from_utel_ctx = (await db_rls.execute(
                select(PipelineStage).where(PipelineStage.is_archived.is_(False))
            )).scalars().all()
            ok_f_utel_side = (
                len(rows_from_utel_ctx) == 8
                and all(r.tenant_id == tenant.id for r in rows_from_utel_ctx)
            )

            if reference_tenant is not None:
                async with AsyncSessionLocal() as db_rls2:
                    await set_tenant_context(db_rls2, reference_tenant.id)
                    rows_from_reference_ctx = (await db_rls2.execute(
                        select(PipelineStage)
                    )).scalars().all()
                    leaked = [r for r in rows_from_reference_ctx if r.tenant_id == tenant.id]
                ok_f_reference_side = len(leaked) == 0
                ok_f = ok_f_utel_side and ok_f_reference_side
                detail_f = (
                    f"desde contexto Utel: {len(rows_from_utel_ctx)} filas (todas de Utel: "
                    f"{all(r.tenant_id == tenant.id for r in rows_from_utel_ctx)}). "
                    f"desde contexto '{REFERENCE_TENANT_EMAIL}': "
                    f"{len(rows_from_reference_ctx)} filas totales, {len(leaked)} de Utel filtradas (deben ser 0)."
                )
            else:
                ok_f = ok_f_utel_side
                detail_f = (
                    f"desde contexto Utel: {len(rows_from_utel_ctx)} filas (todas de Utel: "
                    f"{all(r.tenant_id == tenant.id for r in rows_from_utel_ctx)}). "
                    f"(tenant de referencia '{REFERENCE_TENANT_EMAIL}' no encontrado en este entorno — "
                    f"solo se pudo verificar el lado Utel del aislamiento)"
                )
    results.append((
        "f. RLS: SELECT sin filtro de tenant_id bajo contexto Utel solo devuelve sus 8 filas",
        "PASS" if ok_f else "FAIL",
        detail_f,
    ))

    return _report(results)


def _report(results: list[tuple[str, str, str]]) -> int:
    print()
    all_ok = True
    for label, tag, detail in results:
        if tag == "FAIL":
            all_ok = False
        print(f"  [{tag}] {label}\n         {detail}")
    print()
    if all_ok:
        print("✓ Todas las verificaciones pasaron (o se marcaron SKIP explícitamente).")
        return 0
    print("✗ Al menos una verificación falló — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
