"""set_utel_industry_hibrida.py — PASO 4 del prompt "template educacion_hibrida".

Actualiza branch.industry de Utel de 'educacion' (fix anterior) a
'educacion_hibrida' (entrada nueva con los 7 required_fields reales del
protocolo de Utel).

Uso:
    .venv/Scripts/python.exe scripts/admin/set_utel_industry_hibrida.py           # dry-run
    .venv/Scripts/python.exe scripts/admin/set_utel_industry_hibrida.py --apply   # aplica el UPDATE
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

from app.ai.config_loader import get_branch_config
from app.core.database import AsyncSessionLocal
from app.models.tenant import Branch, Tenant

TENANT_EMAIL = "admin@utel.walix.mx"
EXPECTED_CURRENT = "educacion"
TARGET = "educacion_hibrida"


async def main() -> int:
    apply_fix = "--apply" in sys.argv

    print("=" * 70)
    print("  set_utel_industry_hibrida.py — PASO 4")
    print(f"  modo: {'APLICAR UPDATE' if apply_fix else 'DRY-RUN (solo reporte)'}")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == TENANT_EMAIL)
        )).scalar_one_or_none()
        if tenant is None:
            print(f"\n✗ No existe tenant {TENANT_EMAIL!r}.")
            return 1

        branches = (await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id)
        )).scalars().all()
        if len(branches) != 1:
            print(f"\n! Se esperaba exactamente 1 branch, hay {len(branches)}. Abortando.")
            return 1

        branch = branches[0]
        print(f"\nBranch: id={branch.id} name={branch.name!r} industry actual={branch.industry!r}")

        if branch.industry == TARGET:
            print(f"\n✓ branch.industry ya es {TARGET!r} — nada que hacer.")
        elif branch.industry != EXPECTED_CURRENT:
            print(
                f"\n! branch.industry actual es {branch.industry!r}, se esperaba "
                f"{EXPECTED_CURRENT!r} (del fix anterior). Abortando sin tocar nada — "
                "revisar manualmente."
            )
            return 1
        elif not apply_fix:
            print(f"\nDry-run: no se aplicó el UPDATE. Correr con --apply para setear industry={TARGET!r}.")
        else:
            branch.industry = TARGET
            await db.commit()
            await db.refresh(branch)
            print(f"\n✓ UPDATE aplicado. branch.industry ahora = {branch.industry!r}.")

        print("\n" + "-" * 70)
        config = await get_branch_config(branch.id, db)
        field_names = [f["name"] for f in config.get("qualification", {}).get("required_fields", [])]
        print(f"get_branch_config(Utel) required_fields ({len(field_names)}): {field_names}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
