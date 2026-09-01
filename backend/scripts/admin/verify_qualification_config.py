"""verify_qualification_config.py — verifica get_branch_config() para Utel y
para las 3 branches seed de la clínica, simulando lo que devolverá el nuevo
endpoint GET /branches/{id}/qualification-config.

SOLO LECTURA.

Uso:
    .venv/Scripts/python.exe scripts/admin/verify_qualification_config.py
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

_DEFAULT_AGENT_ROLE_LABEL = {"singular": "especialista", "plural": "especialistas"}


async def _report_branch(db, branch: Branch, label: str) -> None:
    config = await get_branch_config(branch.id, db)
    required_fields = config.get("qualification", {}).get("required_fields", [])
    role_label = config.get("agent_role_label", _DEFAULT_AGENT_ROLE_LABEL)
    curated = [f for f in required_fields if f.get("label")]

    print(f"\n{label} (branch id={branch.id}, industry={branch.industry!r})")
    print(f"  agent_role_label = {role_label}")
    print(f"  qualification fields expuestos en ContactSidePanel ({len(curated)}):")
    for f in curated:
        print(f"    - {f['name']}: {f['label']}")


async def main() -> int:
    async with AsyncSessionLocal() as db:
        utel_tenant = (await db.execute(
            select(Tenant).where(Tenant.email == "admin@utel.walix.mx")
        )).scalar_one_or_none()
        if utel_tenant:
            utel_branch = (await db.execute(
                select(Branch).where(Branch.tenant_id == utel_tenant.id)
            )).scalars().first()
            if utel_branch:
                await _report_branch(db, utel_branch, "UTEL")

        clinica_tenant = (await db.execute(
            select(Tenant).where(Tenant.email == "admin@clinica.com")
        )).scalar_one_or_none()
        if clinica_tenant:
            clinica_branches = (await db.execute(
                select(Branch).where(Branch.tenant_id == clinica_tenant.id).order_by(Branch.name)
            )).scalars().all()
            for b in clinica_branches:
                await _report_branch(db, b, f"CLÍNICA — {b.name}")
        else:
            print("\n! No se encontró tenant admin@clinica.com — revisar seed.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
