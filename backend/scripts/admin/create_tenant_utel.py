"""create_tenant_utel.py — Alta administrativa del tenant "Universidad Utel".

Crea el tenant completo directamente en BD (sin pasar por el wizard de
onboarding conversacional /v1/onboarding/*, que requiere un usuario ya
autenticado), reutilizando TenantSetupService.apply_industry_template()
(ya existe y está probado) como base con industry_key="educacion", y luego
personalizando entity_name/entity_plural y reemplazando las pipeline stages
del template genérico por el funnel de admisiones propio de Utel.

Idempotente: si ya existe un tenant con TENANT_EMAIL, aborta sin crear
duplicados.

Este script SOLO crea el esqueleto del tenant — NO toca webhooks.py, NO
configura MetaLeadConfig, NO escribe el system prompt del bot manualmente
(TenantSetupService ya intenta generarlo, ver bot_config_generated en el
resumen final) ni la Knowledge Base.

Uso:
    .venv/Scripts/python.exe scripts/admin/create_tenant_utel.py
"""
from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Company, Tenant, TenantPlan
from app.models.user import User, UserRole
from app.services.tenant_setup import TenantSetupService

TENANT_EMAIL = "admin@utel.walix.mx"  # placeholder de contacto interno — NO es el email real del cliente todavía
TENANT_NAME = "Universidad Utel"
BRANCH_NAME = "Utel — Campaña Licenciaturas Híbridas"
OWNER_NAME = "Admin Utel"

ONBOARDING_DESCRIPTION = (
    "Universidad con modalidad híbrida: clases en línea entre semana y sesión "
    "presencial semanal enfocada en el desarrollo de power skills. Capta prospectos "
    "vía Meta Ads y Google Ads; el bot de WhatsApp perfila al prospecto y agenda "
    "una cita con un asesor humano para resolver dudas y cerrar la inscripción."
)

# Funnel de admisiones propio de Utel — reemplaza las stages genéricas del
# template "educacion" (Interesado/Entrevista/Evaluado/Inscrito/Cursando/
# Por renovar/Egresado/Baja), que están pensadas para una escuela con ciclo
# de cursada largo, no para un funnel de admisión con perfilamiento por bot
# + cita con asesor humano.
UTEL_ADMISSIONS_STAGES: list[dict] = [
    {"key": "new",         "label": "Nuevo",           "order": 1, "color": "#6B7280"},
    {"key": "profiling",   "label": "Perfilando",      "order": 2, "color": "#3B82F6"},
    {"key": "profiled",    "label": "Perfilado",       "order": 3, "color": "#8B5CF6"},
    {"key": "appointment", "label": "Cita con asesor", "order": 4, "color": "#6366F1"},
    {"key": "follow_up",   "label": "En seguimiento",  "order": 5, "color": "#F59E0B"},
    {"key": "docs",        "label": "Documentación",   "order": 6, "color": "#14B8A6"},
    {"key": "enrolled",    "label": "Inscrito",        "order": 7, "color": "#10B981"},
    {"key": "lost",        "label": "Perdido",         "order": 8, "color": "#EF4444"},
]


async def main() -> int:
    print("=" * 70)
    print("  create_tenant_utel.py — alta administrativa de Universidad Utel")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(Tenant).where(Tenant.email == TENANT_EMAIL)
        )).scalar_one_or_none()
        if existing is not None:
            print(
                f"\nYa existe un tenant con email {TENANT_EMAIL!r} "
                f"(id={existing.id}) — abortando, no se crea ningún duplicado."
            )
            return 0

        # ── a) Tenant ────────────────────────────────────────────────────────
        tenant = Tenant(
            name=TENANT_NAME,
            email=TENANT_EMAIL,
            plan=TenantPlan.BUSINESS,
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        # ── b) Company ───────────────────────────────────────────────────────
        company = Company(
            tenant_id=tenant.id,
            name=TENANT_NAME,
        )
        db.add(company)
        await db.flush()

        # ── c) Branch ────────────────────────────────────────────────────────
        # wa_phone_number_id/wa_token quedan en None a propósito — sin número
        # de WhatsApp Business conectado todavía, el bot no puede enviar
        # mensajes hasta que se configure (fuera de alcance de este prompt).
        branch = Branch(
            company_id=company.id,
            tenant_id=tenant.id,
            name=BRANCH_NAME,
            wa_phone_number_id=None,
            wa_token=None,
            is_active=True,
        )
        db.add(branch)
        await db.flush()

        # ── d) User owner ────────────────────────────────────────────────────
        owner_password = secrets.token_urlsafe(24)
        owner = User(
            tenant_id=tenant.id,
            branch_id=branch.id,
            email=TENANT_EMAIL,
            name=OWNER_NAME,
            hashed_password=hash_password(owner_password),
            role=UserRole.OWNER,
            is_active=True,
        )
        db.add(owner)
        await db.flush()

        # ── e) Aplicar el template de industria "educacion" ─────────────────
        # apply_industry_template hace su propio commit() internamente (paso e
        # del método) — tenant/company/branch/owner, ya flusheados arriba pero
        # todavía no commiteados, quedan persistidos en ese mismo commit.
        setup_service = TenantSetupService()
        template_result = await setup_service.apply_industry_template(
            tenant=tenant,
            industry_key="educacion",
            onboarding_description=ONBOARDING_DESCRIPTION,
            extracted_data={},
            db=db,
        )

        # ── f.1) Renombrar la entidad ────────────────────────────────────────
        tenant.entity_name = "Prospecto"
        tenant.entity_plural = "Prospectos"

        # ── f.2) Reemplazar las pipeline stages del template genérico ───────
        # Mismo patrón que TenantSetupService.apply_industry_template usa
        # (archivar-no-borrar): archivar las stages activas que el template
        # "educacion" acaba de crear, luego crear las 8 propias de Utel.
        old_stages = (await db.execute(
            select(PipelineStage).where(
                PipelineStage.tenant_id == tenant.id,
                PipelineStage.is_archived.is_(False),
            )
        )).scalars().all()
        for stage in old_stages:
            stage.is_archived = True
            stage.slug = f"{stage.slug}__arc_{stage.id.hex[:6]}"
        await db.flush()

        await PipelineStage.create_from_template(
            tenant_id=tenant.id,
            stages=UTEL_ADMISSIONS_STAGES,
            db=db,
        )

        new_stages = (await db.execute(
            select(PipelineStage).where(
                PipelineStage.tenant_id == tenant.id,
                PipelineStage.is_archived.is_(False),
            ).order_by(PipelineStage.order_index)
        )).scalars().all()

        # create_from_template (app/models/pipeline.py) SÍ setea is_won/is_lost
        # a partir de una convención de stage_key, pero esa convención es
        # ("closed_won", "discharged", "delivered", "graduated") para is_won
        # y solo "lost" para is_lost. "lost" cae en la convención (is_lost se
        # setea solo, confirmado abajo) — "enrolled" NO está en la lista de
        # is_won, así que hace falta el UPDATE manual descrito en el prompt
        # únicamente para esa columna en esa stage.
        enrolled_stage = next((s for s in new_stages if s.stage_key == "enrolled"), None)
        lost_stage = next((s for s in new_stages if s.stage_key == "lost"), None)
        manual_is_won_update = False
        if enrolled_stage is not None and not enrolled_stage.is_won:
            enrolled_stage.is_won = True
            manual_is_won_update = True
        lost_auto_set_correctly = lost_stage is not None and lost_stage.is_lost is True

        # ── f.3) commit ──────────────────────────────────────────────────────
        await db.commit()
        await db.refresh(tenant)

        # ── g) Resumen ───────────────────────────────────────────────────────
        print("\n✓ Tenant creado exitosamente\n")
        print(f"  tenant_id       = {tenant.id}")
        print(f"  company_id      = {company.id}")
        print(f"  branch_id       = {branch.id}")
        print(f"  owner_user_id   = {owner.id}")
        print()
        print("  ⚠ CREDENCIALES DEL OWNER — se imprimen UNA SOLA VEZ, guárdalas")
        print("    ahora en un lugar seguro (gestor de contraseñas, vault, etc.).")
        print("    NO quedan logueadas en ningún otro lado por este script.")
        print(f"    email    = {TENANT_EMAIL}")
        print(f"    password = {owner_password}")
        print()
        print(f"  entity_name     = {tenant.entity_name}")
        print(f"  entity_plural   = {tenant.entity_plural}")
        print()
        print(f"  create_from_template: is_lost para key='lost' se setea solo "
              f"por convención (confirmado: {lost_auto_set_correctly}); "
              f"is_won para key='enrolled' NO está en esa convención, se aplicó "
              f"UPDATE manual (aplicado: {manual_is_won_update}).")
        print()
        print(f"  Pipeline stages ({len(new_stages)}):")
        for s in new_stages:
            flags = []
            if s.is_won:
                flags.append("is_won")
            if s.is_lost:
                flags.append("is_lost")
            flags_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"    {s.order_index}. {s.stage_key:<12} {s.name}{flags_str}")
        print()
        bot_config_generated = template_result.get("bot_config_generated")
        print(f"  bot_config_generated = {bot_config_generated}")
        if not bot_config_generated:
            print(
                "    Motivo: TenantSetupService._generate_bot_config_safe falla en "
                "silencio (no propaga el detalle de la excepción al resultado, solo "
                "la registra vía logging.exception) — revisar logs del proceso si "
                "hace falta el detalle exacto. No bloqueante: el resto del tenant "
                "quedó creado correctamente."
            )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
