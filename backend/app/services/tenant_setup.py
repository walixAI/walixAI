"""
TenantSetupService — aplica un Industry Template al tenant.

Archiva las etapas de pipeline anteriores, crea las nuevas desde el template
y actualiza los metadatos del tenant (entity_name, statuses, etc.).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.industry_templates.catalog import get_template
from app.models.pipeline import PipelineStage
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


class TenantSetupService:

    async def apply_industry_template(
        self,
        tenant: Tenant,
        industry_key: str,
        onboarding_description: str,
        extracted_data: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Aplica el template de industria al tenant.

        Pasos:
          a) Obtener template
          b) Actualizar campos del tenant
          c) Archivar stages anteriores
          d) Crear stages nuevas desde template
          e) Hook post-onboarding (no-op por ahora)
          f) Commit
          g) Retornar resumen
        """
        # a) Template
        template = get_template(industry_key)

        # b) Actualizar tenant
        tenant.industry_key = industry_key
        tenant.industry_label = template["label"]
        tenant.entity_name = template["entity_name"]
        tenant.entity_plural = template["entity_plural"]
        tenant.contact_statuses_config = template["contact_statuses"]
        tenant.onboarding_description = onboarding_description
        tenant.onboarding_extracted_data = extracted_data or {}
        tenant.onboarding_completed_at = datetime.now(timezone.utc)

        # c) Archivar stages anteriores del tenant.
        #    Se renombra el slug con un sufijo único para liberar la restricción
        #    uq_pipeline_stages_branch_slug (branch_id, slug) antes de insertar
        #    las stages nuevas del template (que comparten los mismos slugs base).
        old_stages = (
            await db.execute(
                select(PipelineStage).where(
                    PipelineStage.tenant_id == tenant.id,
                    PipelineStage.is_archived.is_(False),
                )
            )
        ).scalars().all()
        for stage in old_stages:
            stage.is_archived = True
            stage.slug = f"{stage.slug}__arc_{stage.id.hex[:6]}"
        await db.flush()

        # d) Crear stages nuevas desde template
        stages_created = await PipelineStage.create_from_template(
            tenant_id=tenant.id,
            stages=template["pipeline_stages"],
            db=db,
        )

        # e) Hook post-onboarding (no-op — se implementará en Sprint 8C)
        await _post_onboarding_hook(tenant.id, extracted_data, db)

        # f) Commit
        await db.commit()

        # g) Resumen
        return {
            "success": True,
            "industry_key": industry_key,
            "industry_label": template["label"],
            "entity_name": template["entity_name"],
            "entity_plural": template["entity_plural"],
            "stages_created": stages_created,
        }


async def _post_onboarding_hook(tenant_id: Any, extracted_data: dict, db: AsyncSession) -> None:
    """Genera la config del bot WhatsApp automáticamente desde la descripción del onboarding."""
    from app.models.tenant import Tenant
    from app.services.bot_config_generator import bot_config_generator

    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        return
    try:
        await bot_config_generator.generate_and_apply(
            tenant=tenant,
            extracted_data=extracted_data,
            db=db,
        )
    except Exception:
        logger.warning("post_onboarding_hook: bot config generation failed for tenant %s", tenant_id)
