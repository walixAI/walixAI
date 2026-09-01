"""test_educacion_hibrida_fields.py — PASO 5 del prompt "template educacion_hibrida".

Verifica:
  a. get_branch_config(Utel) devuelve los 7 required_fields de
     "educacion_hibrida", con los names exactos.
  b. get_branch_config de una branch de la clínica sigue devolviendo
     required_fields de salud (regression guard).
  c. get_branch_config de una branch hipotética con industry='educacion'
     (no 'educacion_hibrida') sigue devolviendo los required_fields
     genéricos de educación sin modificar (regression guard: "educacion"
     quedó intacta).
  d. build_qualification_json_schema(required_fields) con los 7 campos
     nuevos genera un schema JSON válido.

SOLO LECTURA (no crea ni modifica branches reales — (c) usa get_default_config
directamente, sin ir a BD, porque no necesitamos una branch real para probar
que la plantilla "educacion" no cambió).

Uso:
    .venv/Scripts/python.exe scripts/test_educacion_hibrida_fields.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.ai.config_loader import build_qualification_json_schema, get_branch_config, get_default_config
from app.ai.industry_templates import INDUSTRY_TEMPLATES
from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch, Tenant

UTEL_TENANT_EMAIL = "admin@utel.walix.mx"
CLINICA_TENANT_EMAIL = "admin@clinica.com"
CLINICA_SEED_BRANCH_NAMES = {"Sucursal Monterrey", "Sucursal Santa Fe", "Sucursal Condesa"}

_EXPECTED_HIBRIDA_FIELD_NAMES = [
    "contact_name", "age", "city", "program_interest",
    "hybrid_confirmed", "preferred_sede", "contact_time_window",
]
_SALUD_FIELD_NAMES = {f["name"] for f in INDUSTRY_TEMPLATES["salud"]["qualification"]["required_fields"]}
_EDUCACION_FIELD_NAMES_BEFORE = {
    "education_level", "program_interest", "student_age",
    "start_date", "contact_name", "contact_city", "scholarship_interest",
}


async def main() -> int:
    print("=" * 70)
    print("  test_educacion_hibrida_fields.py")
    print("=" * 70)

    results: list[tuple[str, str, str]] = []

    async with AsyncSessionLocal() as db:
        # ── a) get_branch_config(Utel) → 7 campos de educacion_hibrida ─────
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

        utel_config = await get_branch_config(utel_branch.id, db)
        utel_required_fields = utel_config.get("qualification", {}).get("required_fields", [])
        utel_field_names = [f["name"] for f in utel_required_fields]

        ok_a = (
            utel_branch.industry == "educacion_hibrida"
            and utel_field_names == _EXPECTED_HIBRIDA_FIELD_NAMES
        )
        results.append((
            "a. get_branch_config(Utel) devuelve los 7 required_fields de educacion_hibrida",
            "PASS" if ok_a else "FAIL",
            f"branch.industry={utel_branch.industry!r} campos={utel_field_names}",
        ))

        # ── b) regression guard: clínica sigue en salud ─────────────────────
        clinica_tenant = (await db.execute(
            select(Tenant).where(Tenant.email == CLINICA_TENANT_EMAIL)
        )).scalar_one_or_none()

        if clinica_tenant is None:
            results.append((
                "b. get_branch_config(clínica) sigue devolviendo required_fields de salud",
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
                    "b. get_branch_config(clínica) sigue devolviendo required_fields de salud",
                    "SKIP",
                    "no se encontraron las branches seed de la clínica en este entorno",
                ))
            else:
                all_ok_b = True
                detail_lines = []
                for b in clinica_branches:
                    cfg = await get_branch_config(b.id, db)
                    field_names = {f["name"] for f in cfg.get("qualification", {}).get("required_fields", [])}
                    branch_ok = field_names == _SALUD_FIELD_NAMES
                    all_ok_b = all_ok_b and branch_ok
                    detail_lines.append(f"{b.name}: {'OK' if branch_ok else 'MISMATCH'}")
                results.append((
                    "b. get_branch_config(clínica) sigue devolviendo required_fields de salud (regression guard)",
                    "PASS" if all_ok_b else "FAIL",
                    "; ".join(detail_lines),
                ))

    # ── c) "educacion" (genérica) quedó intacta ─────────────────────────────
    # No necesita una branch real: get_default_config("educacion") lee
    # directo de INDUSTRY_TEMPLATES, igual que get_branch_config lo haría
    # para cualquier branch con industry="educacion".
    educacion_config = get_default_config("educacion")
    educacion_field_names = {f["name"] for f in educacion_config["qualification"]["required_fields"]}
    ok_c = educacion_field_names == _EDUCACION_FIELD_NAMES_BEFORE
    results.append((
        "c. INDUSTRY_TEMPLATES['educacion'] (genérica) sigue con sus required_fields originales, sin modificar",
        "PASS" if ok_c else "FAIL",
        f"campos actuales={sorted(educacion_field_names)}",
    ))

    # ── d) build_qualification_json_schema con los 7 campos nuevos ─────────
    try:
        hibrida_required_fields = INDUSTRY_TEMPLATES["educacion_hibrida"]["qualification"]["required_fields"]
        schema_str = build_qualification_json_schema(hibrida_required_fields)
        schema = json.loads(schema_str)
        expected_keys = set(_EXPECTED_HIBRIDA_FIELD_NAMES) | {
            "qualification_status", "qualification_score", "missing_fields", "escalation_reason",
        }
        ok_d = set(schema.keys()) == expected_keys
        results.append((
            "d. build_qualification_json_schema(educacion_hibrida) genera JSON válido con las 11 claves esperadas",
            "PASS" if ok_d else "FAIL",
            f"claves generadas={sorted(schema.keys())}",
        ))
    except (json.JSONDecodeError, KeyError) as exc:
        results.append((
            "d. build_qualification_json_schema(educacion_hibrida) genera JSON válido",
            "FAIL",
            f"excepción: {exc!r}",
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
