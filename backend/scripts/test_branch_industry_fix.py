"""test_branch_industry_fix.py — PASO 5 del prompt Utel branch.industry.

Verifica:
  a. branch.industry de Utel == 'educacion'.
  b. get_branch_config(branch_utel_id) devuelve required_fields de educación
     (no de salud).
  c. get_branch_config de una branch de la clínica sigue devolviendo
     required_fields de salud — regression guard: el fix de Utel no debe
     afectar a la clínica.

SOLO LECTURA.

Uso:
    .venv/Scripts/python.exe scripts/test_branch_industry_fix.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.ai.config_loader import get_branch_config
from app.ai.industry_templates import INDUSTRY_TEMPLATES
from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch, Tenant

UTEL_TENANT_EMAIL = "admin@utel.walix.mx"
CLINICA_TENANT_EMAIL = "admin@clinica.com"
# Los 3 branches seed de la clínica (ver prompt PASO 4.3) — el tenant clínica
# también tiene "Sucursal Puebla" (industry='inmobiliaria'), sembrada aparte
# para probar otra industria; no es parte del regression guard de salud.
CLINICA_SEED_BRANCH_NAMES = {"Sucursal Monterrey", "Sucursal Santa Fe", "Sucursal Condesa"}

_SALUD_FIELD_NAMES = {f["name"] for f in INDUSTRY_TEMPLATES["salud"]["qualification"]["required_fields"]}
_EDUCACION_FIELD_NAMES = {f["name"] for f in INDUSTRY_TEMPLATES["educacion"]["qualification"]["required_fields"]}


async def main() -> int:
    print("=" * 70)
    print("  test_branch_industry_fix.py")
    print("=" * 70)

    results: list[tuple[str, str, str]] = []  # (label, PASS/FAIL/SKIP, detail)

    async with AsyncSessionLocal() as db:
        utel_tenant = (await db.execute(
            select(Tenant).where(Tenant.email == UTEL_TENANT_EMAIL)
        )).scalar_one_or_none()

        if utel_tenant is None:
            print(f"\n✗ No existe tenant {UTEL_TENANT_EMAIL!r} — abortando.")
            return 1

        utel_branch = (await db.execute(
            select(Branch).where(Branch.tenant_id == utel_tenant.id)
        )).scalars().first()

        if utel_branch is None:
            print("\n✗ El tenant Utel no tiene branches — abortando.")
            return 1

        # ── a) branch.industry de Utel == 'educacion' ──────────────────────
        ok_a = utel_branch.industry == "educacion"
        results.append((
            "a. branch.industry de Utel == 'educacion'",
            "PASS" if ok_a else "FAIL",
            f"branch.industry={utel_branch.industry!r} (branch id={utel_branch.id})",
        ))

        # ── b) get_branch_config(utel) → required_fields de educación ──────
        utel_config = await get_branch_config(utel_branch.id, db)
        utel_field_names = {
            f["name"] for f in utel_config.get("qualification", {}).get("required_fields", [])
        }
        ok_b = (
            utel_field_names == _EDUCACION_FIELD_NAMES
            and not (utel_field_names & _SALUD_FIELD_NAMES - _EDUCACION_FIELD_NAMES)
        )
        results.append((
            "b. get_branch_config(Utel) devuelve required_fields de educación (no de salud)",
            "PASS" if ok_b else "FAIL",
            f"campos devueltos={sorted(utel_field_names)}",
        ))

        # ── c) regression guard: branch de la clínica sigue en salud ────────
        clinica_tenant = (await db.execute(
            select(Tenant).where(Tenant.email == CLINICA_TENANT_EMAIL)
        )).scalar_one_or_none()

        if clinica_tenant is None:
            results.append((
                "c. get_branch_config(clínica) sigue devolviendo required_fields de salud",
                "SKIP",
                f"no se encontró tenant {CLINICA_TENANT_EMAIL!r} en este entorno",
            ))
        else:
            clinica_branches = (await db.execute(
                select(Branch).where(
                    Branch.tenant_id == clinica_tenant.id,
                    Branch.name.in_(CLINICA_SEED_BRANCH_NAMES),
                )
            )).scalars().all()
            if not clinica_branches:
                results.append((
                    "c. get_branch_config(clínica) sigue devolviendo required_fields de salud",
                    "SKIP",
                    "el tenant clínica no tiene branches en este entorno",
                ))
            else:
                all_ok_c = True
                detail_lines = []
                for b in clinica_branches:
                    cfg = await get_branch_config(b.id, db)
                    field_names = {f["name"] for f in cfg.get("qualification", {}).get("required_fields", [])}
                    branch_ok = field_names == _SALUD_FIELD_NAMES
                    all_ok_c = all_ok_c and branch_ok
                    detail_lines.append(f"{b.name} (industry={b.industry!r}): {'OK' if branch_ok else 'MISMATCH'}")
                results.append((
                    "c. get_branch_config(clínica) sigue devolviendo required_fields de salud (regression guard)",
                    "PASS" if all_ok_c else "FAIL",
                    "; ".join(detail_lines),
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
    print(
        "  [SKIP] frontend component tests — el proyecto no tiene framework de "
        "tests de componentes configurado (sin vitest/jest, sin .test.tsx). "
        "Verificado manualmente vía scripts/admin/verify_qualification_config.py "
        "en su lugar (ContactSidePanel/AssignmentDropdown consumen la misma "
        "get_branch_config probada en b/c de este script)."
    )
    if all_ok:
        print("\n✓ Todas las verificaciones pasaron (o se marcaron SKIP explícitamente).")
        return 0
    print("\n✗ Al menos una verificación falló — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
