"""Seed pipeline stages for the clinic's three branches.

Run from the backend/ directory:

    .venv/bin/python scripts/seed_pipeline.py

Idempotent — skips any branch that already has pipeline stages configured.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Tenant

TENANT_EMAIL = "admin@clinica.com"

STAGE_SPECS: list[dict] = [
    {"name": "Nuevo",             "slug": "nuevo",             "color": "#9B9893", "order_index": 0, "is_won": False, "is_lost": False},
    {"name": "Calificando",       "slug": "calificando",       "color": "#EF9F27", "order_index": 1, "is_won": False, "is_lost": False},
    {"name": "Calificado",        "slug": "calificado",        "color": "#1A5BB5", "order_index": 2, "is_won": False, "is_lost": False},
    {"name": "Consulta agendada", "slug": "consulta_agendada", "color": "#534AB7", "order_index": 3, "is_won": False, "is_lost": False},
    {"name": "Paciente activo",   "slug": "paciente_activo",   "color": "#0F6E56", "order_index": 4, "is_won": True,  "is_lost": False},
    {"name": "No califica",       "slug": "no_califica",       "color": "#993C1D", "order_index": 5, "is_won": False, "is_lost": True},
]


async def seed_pipeline() -> None:
    async with AsyncSessionLocal() as db:
        # Locate tenant
        tenant_row = await db.execute(
            select(Tenant).where(Tenant.email == TENANT_EMAIL)
        )
        tenant = tenant_row.scalar_one_or_none()
        if tenant is None:
            print(f"✗ Tenant {TENANT_EMAIL} not found — run scripts/seed.py first")
            return

        # Fetch all branches for this tenant
        branches_row = await db.execute(
            select(Branch).where(Branch.tenant_id == tenant.id).order_by(Branch.name)
        )
        branches = branches_row.scalars().all()
        if not branches:
            print("✗ No branches found for tenant — run scripts/seed.py first")
            return

        for branch in branches:
            # Check if stages already exist for this branch
            existing_row = await db.execute(
                select(PipelineStage).where(PipelineStage.branch_id == branch.id).limit(1)
            )
            if existing_row.scalar_one_or_none() is not None:
                print(f"  — {branch.name}: already has pipeline stages, skipping")
                continue

            for spec in STAGE_SPECS:
                db.add(
                    PipelineStage(
                        branch_id=branch.id,
                        tenant_id=tenant.id,
                        name=spec["name"],
                        slug=spec["slug"],
                        color=spec["color"],
                        order_index=spec["order_index"],
                        is_won=spec["is_won"],
                        is_lost=spec["is_lost"],
                    )
                )

            await db.flush()
            print(f"  ✓ {branch.name}: {len(STAGE_SPECS)} stages inserted")

        await db.commit()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(seed_pipeline())
