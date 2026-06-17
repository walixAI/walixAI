"""
TenantSetupService — aplica un Industry Template al tenant.

Archiva las etapas de pipeline anteriores, crea las nuevas desde el template
y actualiza los metadatos del tenant (entity_name, statuses, etc.).

Sprint 12: al confirmar el onboarding llama a BotConfigGeneratorService para
la branch principal del tenant. La generación del bot corre en una transacción
separada — si falla no bloquea la aplicación del template.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.industry_templates.catalog import get_template
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Tenant

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
          a-b) Guardar descripción y extracted_data en el tenant
          c)   Actualizar campos semánticos del tenant (entity_name, statuses…)
          d)   Archivar stages anteriores y crear las nuevas desde el template
          e)   COMMIT — el template queda guardado independientemente del bot
          f)   Generar config del bot para la branch principal (no bloqueante)
          g)   Retornar resumen con bot_config_generated + bot_config
        """
        template = get_template(industry_key)

        # a) Descripción completa del negocio
        tenant.onboarding_description = onboarding_description
        # b) Datos extraídos por IndustryInference
        tenant.onboarding_extracted_data = extracted_data or {}
        # c) Campos semánticos del template
        tenant.industry_key = industry_key
        tenant.industry_label = template["label"]
        tenant.entity_name = template["entity_name"]
        tenant.entity_plural = template["entity_plural"]
        tenant.contact_statuses_config = template["contact_statuses"]
        tenant.onboarding_completed_at = datetime.now(timezone.utc)

        # d) Archivar stages anteriores (slug único para liberar la constraint única)
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

        stages_created = await PipelineStage.create_from_template(
            tenant_id=tenant.id,
            stages=template["pipeline_stages"],
            db=db,
        )

        # e) Commit del template — independiente de lo que ocurra con el bot
        await db.commit()

        # f) Generar config del bot (no bloqueante — falla silenciosamente)
        bot_config_generated, bot_config = await _generate_bot_config_safe(
            tenant=tenant,
            extracted_data=extracted_data,
            db=db,
        )

        # g) Resumen
        return {
            "success": True,
            "industry_key": industry_key,
            "industry_label": template["label"],
            "entity_name": template["entity_name"],
            "entity_plural": template["entity_plural"],
            "stages_created": stages_created,
            "bot_config_generated": bot_config_generated,
            "bot_config": bot_config,
        }


async def _generate_bot_config_safe(
    tenant: Tenant,
    extracted_data: dict[str, Any],
    db: AsyncSession,
) -> tuple[bool, dict | None]:
    """Genera config del bot para la branch principal del tenant.

    Corre en una transacción separada para no bloquear el onboarding.
    Retorna (True, config_dict) si tuvo éxito, (False, None) si falló.
    """
    from app.services.bot_config_generator import bot_config_generator

    if not tenant.onboarding_description:
        return False, None

    try:
        # Buscar la branch principal: primero por nombre convencional, luego por created_at
        branch = await _find_principal_branch(tenant.id, db)
        if branch is None:
            logger.warning("_generate_bot_config_safe: no se encontró branch para tenant %s", tenant.id)
            return False, None

        config = await bot_config_generator.regenerate_for_branch(
            branch=branch,
            tenant=tenant,
            db=db,
        )
        if config is None:
            return False, None

        await db.commit()
        logger.info(
            "_generate_bot_config_safe: bot config generado para branch %s (tenant %s)",
            branch.id, tenant.id,
        )
        return True, {
            "system_prompt": config["system_prompt"],
            "tone": config["tone"],
            "qualification_questions": config["qualification_questions"],
        }

    except Exception:
        logger.exception(
            "_generate_bot_config_safe: falló para tenant %s — onboarding no afectado",
            tenant.id,
        )
        try:
            await db.rollback()
        except Exception:
            pass
        return False, None


async def _find_principal_branch(tenant_id: Any, db: AsyncSession) -> Branch | None:
    """Retorna la branch principal del tenant.

    Orden de prioridad:
      1. Branch cuyo nombre contiene "Principal" (convención Sprint 9)
      2. Branch cuyo nombre contiene "Sede" (registro legacy)
      3. Primera branch activa por created_at
    """
    result = await db.execute(
        select(Branch).where(
            Branch.tenant_id == tenant_id,
            Branch.is_active.is_(True),
        ).order_by(Branch.created_at.asc())
    )
    branches = result.scalars().all()
    if not branches:
        return None

    for candidate in branches:
        if "principal" in candidate.name.lower() or "sede" in candidate.name.lower():
            return candidate

    return branches[0]
