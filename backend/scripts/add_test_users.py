"""Add IT, asistente, and doctor test users to an existing tenant.

Safe to run multiple times — skips users whose email already exists.

Run from backend/:
    .venv/bin/python scripts/add_test_users.py [--branch "Monterrey"]
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole

TENANT_EMAIL = "admin@clinica.com"
DEFAULT_PASSWORD = "walix2026"

NEW_USERS = [
    {
        "name": "Asistente Médica",
        "email": "asistente@clinica.com",
        "role": UserRole.ASESOR,
        "wa_phone": None,  # set a real number if you want WA notifications
    },
    {
        "name": "Dr. González",
        "email": "doctor@clinica.com",
        "role": UserRole.DOCTOR,
        "wa_phone": None,
    },
    {
        "name": "Soporte IT",
        "email": "it@clinica.com",
        "role": UserRole.IT,
        "wa_phone": None,
    },
]


async def run(branch_name: str) -> None:
    async with AsyncSessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.email == TENANT_EMAIL))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"Tenant {TENANT_EMAIL} not found — run seed.py first.")
            return

        branch = (
            await db.execute(
                select(Branch).where(
                    Branch.tenant_id == tenant.id,
                    Branch.name == branch_name,
                )
            )
        ).scalar_one_or_none()
        if branch is None:
            print(f"Branch '{branch_name}' not found. Available branches:")
            rows = (
                await db.execute(select(Branch).where(Branch.tenant_id == tenant.id))
            ).scalars().all()
            for b in rows:
                print(f"  - {b.name}")
            return

        hashed = hash_password(DEFAULT_PASSWORD)
        created = []
        skipped = []

        for spec in NEW_USERS:
            existing = (
                await db.execute(select(User).where(User.email == spec["email"]))
            ).scalar_one_or_none()
            if existing:
                skipped.append(spec["email"])
                continue
            db.add(
                User(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    email=spec["email"],
                    name=spec["name"],
                    hashed_password=hashed,
                    role=spec["role"],
                    wa_phone=spec["wa_phone"],
                )
            )
            created.append(spec)

        await db.commit()

    print(f"\nTenant : {TENANT_EMAIL}")
    print(f"Branch : {branch_name}")
    print(f"Password: {DEFAULT_PASSWORD!r}\n")

    if created:
        print("Usuarios creados:")
        for s in created:
            print(f"  ✓ {s['email']:<35} role={s['role'].value}")
    if skipped:
        print("\nYa existían (sin cambios):")
        for e in skipped:
            print(f"  - {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--branch", default="Monterrey", help="Branch name to assign users to"
    )
    args = parser.parse_args()
    asyncio.run(run(args.branch))
