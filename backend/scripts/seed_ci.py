"""seed_ci.py — Seed mínimo para el entorno CI.

Crea (idempotente):
  - Tenant A: Clínica Endocrinología Pediátrica (admin@clinica.com)
    · 1 branch "Condesa CDMX" con asesor.con@clinica.com y owner@clinica.com
    · 7 etapas de salud en esa branch

  - Tenant B: Demo Walix (test4@mail.com)
    · tenant_id fijo = 7e4ec8d0-1d93-43a2-b610-120a3bf91e68
    · 1 branch, usuario test4@mail.com (owner)
    · 6 etapas genéricas

En local con DB ya poblada, el script detecta datos existentes y no hace nada.

Uso:
    cd backend
    .venv/bin/python scripts/seed_ci.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.industry_templates.catalog import get_template
from app.models.pipeline import PipelineStage
from app.models.pipeline_group import Pipeline
from app.models.tenant import AssignmentMode, Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole

DEFAULT_PASSWORD = "walix2026"

# ── Etapas salud ──────────────────────────────────────────────────────────────

HEALTH_STAGES = [
    {"key": "ci_consulta",   "label": "Consulta Inicial",   "order": 0, "color": "#3B82F6", "is_won": False, "is_lost": False, "prob": 20},
    {"key": "ci_cita",       "label": "Primera Cita",       "order": 1, "color": "#8B5CF6", "is_won": False, "is_lost": False, "prob": 40},
    {"key": "ci_estudios",   "label": "Estudios / Labs",    "order": 2, "color": "#F59E0B", "is_won": False, "is_lost": False, "prob": 60},
    {"key": "ci_seguimiento","label": "Seguimiento",        "order": 3, "color": "#10B981", "is_won": False, "is_lost": False, "prob": 75},
    {"key": "ci_tratamiento","label": "Tratamiento Activo", "order": 4, "color": "#06B6D4", "is_won": False, "is_lost": False, "prob": 90},
    {"key": "ci_alta",       "label": "Alta Médica",        "order": 5, "color": "#22C55E", "is_won": True,  "is_lost": False, "prob": 100},
    {"key": "ci_perdido",    "label": "No continuó",        "order": 6, "color": "#EF4444", "is_won": False, "is_lost": True,  "prob": 0},
]

DEMO_STAGES = [
    {"key": "dm_nuevo",     "label": "Nuevo",     "order": 0, "color": "#3B82F6", "is_won": False, "is_lost": False, "prob": 20},
    {"key": "dm_contacto",  "label": "Contacto",  "order": 1, "color": "#8B5CF6", "is_won": False, "is_lost": False, "prob": 40},
    {"key": "dm_cita",      "label": "Cita",      "order": 2, "color": "#F59E0B", "is_won": False, "is_lost": False, "prob": 60},
    {"key": "dm_propuesta", "label": "Propuesta", "order": 3, "color": "#10B981", "is_won": False, "is_lost": False, "prob": 75},
    {"key": "dm_ganado",    "label": "Ganado",    "order": 4, "color": "#22C55E", "is_won": True,  "is_lost": False, "prob": 100},
    {"key": "dm_perdido",   "label": "Perdido",   "order": 5, "color": "#EF4444", "is_won": False, "is_lost": True,  "prob": 0},
]


# ── Helper ────────────────────────────────────────────────────────────────────

def _apply_industry_fields(tenant: Tenant, industry_key: str) -> None:
    """Puebla los campos semánticos de nomenclatura dinámica (Sprint 8B).

    seed_ci.py crea las pipeline_stages directamente en vez de vía
    TenantSetupService.apply_industry_template() (que también archiva
    stages previas — innecesario acá, tenant nuevo), así que replica solo
    la parte de campos del tenant. Sin esto, industry_key/entity_name/
    entity_plural/contact_statuses_config se quedan en su server_default
    ("generico"/"Contacto"/"Contactos"/[]) y test_nomenclatura.py falla
    porque contact_statuses_config queda vacío.
    """
    template = get_template(industry_key)
    tenant.industry_key = industry_key
    tenant.industry_label = template["label"]
    tenant.entity_name = template["entity_name"]
    tenant.entity_plural = template["entity_plural"]
    tenant.contact_statuses_config = template["contact_statuses"]


async def _branch_needs_stages(db, branch_id: uuid.UUID) -> bool:
    """True si el branch no tiene al menos una etapa won Y una lost."""
    stages = (await db.execute(
        select(PipelineStage).where(PipelineStage.branch_id == branch_id)
    )).scalars().all()
    has_won  = any(s.is_won  for s in stages)
    has_lost = any(s.is_lost for s in stages)
    return not (has_won and has_lost)


async def _create_stages(
    db,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    stage_specs: list[dict],
) -> int:
    """Crea stages evitando violar la constraint (tenant_id, stage_key).

    pipeline_id es NOT NULL en pipeline_stages — resuelve o crea el Pipeline
    default del branch antes de crear las stages (mismo patrón que
    app/models/pipeline.py, donde se resuelve/crea "Pipeline Principal").
    """
    pipeline_result = await db.execute(
        select(Pipeline).where(
            Pipeline.branch_id == branch_id,
            Pipeline.is_default.is_(True),
        ).limit(1)
    )
    pipeline = pipeline_result.scalar_one_or_none()
    if pipeline is None:
        pipeline = Pipeline(
            tenant_id=tenant_id,
            branch_id=branch_id,
            name="Pipeline Principal",
            is_default=True,
            position=0,
        )
        db.add(pipeline)
        await db.flush()

    existing_tenant_keys = {
        row[0]
        for row in (await db.execute(
            select(PipelineStage.stage_key).where(
                PipelineStage.tenant_id == tenant_id,
                PipelineStage.stage_key.isnot(None),
            )
        )).all()
    }
    created = 0
    for spec in stage_specs:
        if spec["key"] in existing_tenant_keys:
            continue
        db.add(PipelineStage(
            tenant_id=tenant_id,
            branch_id=branch_id,
            pipeline_id=pipeline.id,
            name=spec["label"],
            slug=spec["key"],
            stage_key=spec["key"],
            order_index=spec["order"],
            color=spec["color"],
            is_won=spec["is_won"],
            is_lost=spec["is_lost"],
            probability_default=spec["prob"],
            is_active=True,
        ))
        existing_tenant_keys.add(spec["key"])
        created += 1
    return created


# ── Tenant A: Clínica ─────────────────────────────────────────────────────────

CLINICA_EMAIL = "admin@clinica.com"


async def seed_clinica() -> None:
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.email == CLINICA_EMAIL)
        )).scalar_one_or_none()

        if tenant is None:
            tenant = Tenant(
                name="Clínica Endocrinología Pediátrica",
                email=CLINICA_EMAIL,
                plan=TenantPlan.ENTERPRISE,
                industry="salud",
            )
            _apply_industry_fields(tenant, "salud")
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

            condesa = Branch(
                company_id=company.id,
                tenant_id=tenant.id,
                name="Condesa CDMX",
                # PENDIENTE_MTY (no _CON) a propósito: es el phone_number_id
                # que scripts/test_webhook.py y test_qualification.py tienen
                # hardcodeado (mismo valor que usa scripts/seed.py para la
                # branch Monterrey en dev local) — sin este match, el
                # webhook de CI nunca resuelve una branch y el lead nunca
                # se crea, dejando a este tenant sin leads para los tests
                # de deals/pipeline que corren después.
                wa_phone_number_id="PENDIENTE_MTY",
                wa_token=None,
                assignment_mode=AssignmentMode.EQUITATIVA,
            )
            db.add(condesa)
            await db.flush()

            hashed = hash_password(DEFAULT_PASSWORD)
            for spec in [
                {"email": "owner@clinica.com",     "name": "Owner Clínica",  "role": "owner", "branch_id": None},
                {"email": "asesor.con@clinica.com", "name": "Asesor Condesa","role": "asesor","branch_id": condesa.id},
            ]:
                db.add(User(
                    tenant_id=tenant.id,
                    branch_id=spec["branch_id"],
                    email=spec["email"],
                    name=spec["name"],
                    hashed_password=hashed,
                    role=UserRole(spec["role"]),
                ))

            n = await _create_stages(db, tenant.id, condesa.id, HEALTH_STAGES)
            await db.commit()
            print(f"  ✓ Tenant clinica creado ({tenant.id})")
            print(f"  ✓ Branch Condesa + {n} stages + 2 usuarios")
        else:
            print(f"  → Tenant clinica ya existe ({tenant.id})")

            # Asegurar que alguna branch activa tenga stages completos
            branches = (await db.execute(
                select(Branch).where(Branch.tenant_id == tenant.id, Branch.is_active.is_(True))
            )).scalars().all()

            total_new = 0
            for branch in branches:
                if not await _branch_needs_stages(db, branch.id):
                    continue
                n = await _create_stages(db, tenant.id, branch.id, HEALTH_STAGES)
                total_new += n

            if total_new:
                await db.commit()
                print(f"  ✓ {total_new} stages añadidas a branches sin cobertura completa")
            else:
                print(f"  → Stages ya presentes en todas las branches activas")


# ── Tenant B: Demo ────────────────────────────────────────────────────────────

DEMO_TENANT_ID = uuid.UUID("7e4ec8d0-1d93-43a2-b610-120a3bf91e68")


async def seed_demo_tenant() -> None:
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == DEMO_TENANT_ID)
        )).scalar_one_or_none()

        if tenant is None:
            tenant = Tenant(
                id=DEMO_TENANT_ID,
                name="Demo Walix",
                email="admin@demo.walix",
                plan=TenantPlan.STARTER,
            )
            _apply_industry_fields(tenant, "generico")
            db.add(tenant)
            await db.flush()

            company = Company(tenant_id=tenant.id, name="Demo Walix")
            db.add(company)
            await db.flush()

            branch = Branch(
                company_id=company.id,
                tenant_id=tenant.id,
                name="Principal",
                wa_phone_number_id="DEMO_WA_001",
                wa_token=None,
                assignment_mode=AssignmentMode.EQUITATIVA,
            )
            db.add(branch)
            await db.flush()

            hashed = hash_password(DEFAULT_PASSWORD)
            db.add(User(
                tenant_id=tenant.id,
                branch_id=branch.id,
                email="test4@mail.com",
                name="Demo Owner",
                hashed_password=hashed,
                role=UserRole.OWNER,
            ))

            n = await _create_stages(db, tenant.id, branch.id, DEMO_STAGES)
            await db.commit()
            print(f"  ✓ Demo tenant creado ({DEMO_TENANT_ID})")
            print(f"  ✓ test4@mail.com (owner) + {n} stages")
        else:
            print(f"  → Demo tenant ya existe ({DEMO_TENANT_ID})")
            # Asegurar stages
            branches = (await db.execute(
                select(Branch).where(Branch.tenant_id == DEMO_TENANT_ID)
            )).scalars().all()
            total_new = 0
            for branch in branches:
                if not await _branch_needs_stages(db, branch.id):
                    continue
                n = await _create_stages(db, tenant.id, branch.id, DEMO_STAGES)
                total_new += n
            if total_new:
                await db.commit()
                print(f"  ✓ {total_new} stages añadidas al demo tenant")
            else:
                print(f"  → Stages ya presentes en demo tenant")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n══════════════════════════════════════════════════════")
    print("  Walix CI Seed")
    print("══════════════════════════════════════════════════════\n")
    print("── Tenant A: Clínica ──────────────────────────────────")
    await seed_clinica()
    print("\n── Tenant B: Demo (test4@mail.com) ────────────────────")
    await seed_demo_tenant()
    print("\n✅  seed_ci.py completado.\n")


if __name__ == "__main__":
    asyncio.run(main())
