"""Seed the dev database with one tenant, one company, three branches and four users.

Run from the backend/ directory:

    .venv/bin/python scripts/seed.py

The script is idempotent — if the tenant already exists it exits without changes.
"""
import asyncio
import sys
from pathlib import Path

# Make `app.*` importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tenant import (
    AssignmentMode,
    Branch,
    Company,
    Tenant,
    TenantPlan,
)
from app.models.user import User, UserRole

TENANT_EMAIL = "admin@clinica.com"
DEFAULT_PASSWORD = "walix2026"

BRANCH_SPECS: list[dict[str, str]] = [
    # wa_phone_number_id is unique per branch so the webhook resolver can pick
    # the right one. Replace with the real Meta ID once you configure each
    # number in developers.facebook.com.
    {"name": "Monterrey", "wa_phone_number_id": "PENDIENTE_MTY"},
    {"name": "Santa Fe CDMX", "wa_phone_number_id": "PENDIENTE_SF"},
    {"name": "Condesa CDMX", "wa_phone_number_id": "PENDIENTE_CON"},
]

USER_SPECS: list[dict[str, str | None]] = [
    {
        "name": "Owner Clínica",
        "email": "owner@clinica.com",
        "role": "owner",
        "branch": None,
    },
    {
        "name": "Asistente Médica",
        "email": "asistente@clinica.com",
        "role": "asesor",
        "branch": "Monterrey",
    },
    {
        "name": "Dr. González",
        "email": "doctor@clinica.com",
        "role": "doctor",
        "branch": "Monterrey",
    },
    {
        "name": "Soporte IT",
        "email": "it@clinica.com",
        "role": "it",
        "branch": "Monterrey",
    },
    {
        "name": "Asesor Santa Fe",
        "email": "asesor.sf@clinica.com",
        "role": "asesor",
        "branch": "Santa Fe CDMX",
    },
    {
        "name": "Asesor Condesa",
        "email": "asesor.con@clinica.com",
        "role": "asesor",
        "branch": "Condesa CDMX",
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(Tenant).where(Tenant.email == TENANT_EMAIL)
        )
        if existing.scalar_one_or_none() is not None:
            print(
                f"Tenant {TENANT_EMAIL} already exists — nothing to do.\n"
                "Drop it manually if you want to re-seed."
            )
            return

        tenant = Tenant(
            name="Clínica Endocrinología Pediátrica",
            email=TENANT_EMAIL,
            plan=TenantPlan.ENTERPRISE,
            industry="salud",
        )
        db.add(tenant)
        await db.flush()

        company = Company(
            tenant_id=tenant.id,
            name="Clínica Endocrinología Pediátrica",
            industry="salud",
            config={},
        )
        db.add(company)
        await db.flush()

        branches_by_name: dict[str, Branch] = {}
        for spec in BRANCH_SPECS:
            branch = Branch(
                company_id=company.id,
                tenant_id=tenant.id,
                name=spec["name"],
                wa_phone_number_id=spec["wa_phone_number_id"],
                wa_token=None,
                assignment_mode=AssignmentMode.EQUITATIVA,
            )
            db.add(branch)
            branches_by_name[spec["name"]] = branch
        await db.flush()

        hashed = hash_password(DEFAULT_PASSWORD)
        for spec in USER_SPECS:
            branch_name = spec["branch"]
            branch_id = (
                branches_by_name[branch_name].id if branch_name else None
            )
            db.add(
                User(
                    tenant_id=tenant.id,
                    branch_id=branch_id,
                    email=spec["email"],
                    name=spec["name"],
                    hashed_password=hashed,
                    role=UserRole(spec["role"]),
                )
            )

        await db.commit()

        print(f"✓ Tenant:  {tenant.name}")
        print(f"  id={tenant.id}  plan={tenant.plan.value}")
        print(f"✓ Company: {company.name}")
        for spec in BRANCH_SPECS:
            b = branches_by_name[spec["name"]]
            print(
                f"✓ Branch:  {b.name:<18} "
                f"wa_phone_number_id={b.wa_phone_number_id}"
            )
        print(f"✓ Users (password = {DEFAULT_PASSWORD!r}):")
        for spec in USER_SPECS:
            print(
                f"    - {spec['email']:<30} "
                f"role={spec['role']:<7} branch={spec['branch'] or '(none)'}"
            )


if __name__ == "__main__":
    asyncio.run(seed())
