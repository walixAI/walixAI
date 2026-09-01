"""fix_utel_branch_industry.py — PASO 1 del prompt Utel branch.industry.

Causa raíz: en app/ai/config_loader.py::get_branch_config(), cuando
branch.bot_system_prompt está seteado, el resto de la config base viene de
get_default_config(branch.industry or "salud"). branch.industry de Utel es
None -> cae en INDUSTRY_TEMPLATES["salud"] -> el qualifier extrae campos
pediátricos de prospectos universitarios adultos.

Este script:
  1. Localiza el tenant Utel (admin@utel.walix.mx) y su(s) branch(es).
  2. Reporta el branch.industry actual (re-verifica, no asume).
  3. Si es None, hace UPDATE branches SET industry = 'educacion' WHERE id = <branch>.
  4. Verifica que INDUSTRY_TEMPLATES['educacion'] existe y lista sus required_fields
     para comparar manualmente contra el protocolo real de Utel.

Uso:
    .venv/Scripts/python.exe scripts/admin/fix_utel_branch_industry.py           # dry-run (solo reporta)
    .venv/Scripts/python.exe scripts/admin/fix_utel_branch_industry.py --apply   # aplica el UPDATE
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.ai.industry_templates import INDUSTRY_TEMPLATES
from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch, Tenant

TENANT_EMAIL = "admin@utel.walix.mx"


async def main() -> int:
    apply_fix = "--apply" in sys.argv

    print("=" * 70)
    print("  fix_utel_branch_industry.py — PASO 1 (branch.industry Utel)")
    print(f"  modo: {'APLICAR UPDATE' if apply_fix else 'DRY-RUN (solo reporte)'}")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == TENANT_EMAIL)
        )).scalar_one_or_none()

        if tenant is None:
            print(f"\n✗ No existe ningún tenant con email {TENANT_EMAIL!r}.")
            return 1

        print(f"\nTenant: {tenant.name!r} (id={tenant.id}) industry_key={tenant.industry_key!r}")

        branches = (await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id)
        )).scalars().all()

        if not branches:
            print("\n✗ El tenant no tiene branches.")
            return 1

        print(f"\nBranches encontradas: {len(branches)}")
        for b in branches:
            print(
                f"  id={b.id} name={b.name!r} industry={b.industry!r} "
                f"onboarding_status={b.onboarding_status!r} "
                f"bot_system_prompt_set={b.bot_system_prompt is not None}"
            )

        if len(branches) != 1:
            print(
                "\n! Hay más de una branch — este script solo maneja el caso de una "
                "branch principal. Revisar manualmente cuál es la 'branch principal de "
                "Utel' antes de aplicar el UPDATE."
            )
            return 1

        branch = branches[0]
        already_ok = branch.industry == "educacion"

        if branch.industry not in (None, "educacion"):
            print(
                f"\n! branch.industry actual es {branch.industry!r} (ni None ni "
                "'educacion') — no es el caso descrito en el prompt. Abortando sin "
                "tocar nada; revisar manualmente."
            )
            return 1

        if already_ok:
            print("\n✓ branch.industry YA es 'educacion' — nada que hacer (re-verificado, no se asumió).")
        elif not apply_fix:
            print(
                f"\nbranch.industry actual = {branch.industry!r} (None, confirma la causa raíz). "
                "Dry-run: no se aplicó el UPDATE. Correr de nuevo con --apply para aplicarlo."
            )
        else:
            branch.industry = "educacion"
            await db.commit()
            await db.refresh(branch)
            print(f"\n✓ UPDATE aplicado. branch.industry ahora = {branch.industry!r} (branch id={branch.id}).")

    # ── Verificación del entry 'educacion' en INDUSTRY_TEMPLATES ──────────
    print("\n" + "-" * 70)
    tmpl = INDUSTRY_TEMPLATES.get("educacion")
    if tmpl is None:
        print("✗ INDUSTRY_TEMPLATES NO tiene entry 'educacion' — esto es grave, bloquea el fix.")
        return 1

    required_fields = tmpl["qualification"]["required_fields"]
    print("INDUSTRY_TEMPLATES['educacion'].qualification.required_fields:")
    for f in required_fields:
        print(f"  - {f['name']}: {f['description']}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
