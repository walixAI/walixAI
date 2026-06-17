"""BotConfigGeneratorService — genera la config inicial del bot desde el onboarding.

Usa Claude Haiku para producir:
  - bot_system_prompt: system prompt completo listo para usar en el bot
  - bot_tone: tono detectado ("formal" | "amigable" | "profesional" | "cercano")
  - bot_qualification_questions: [{order, question, field_key}]

La config generada se guarda en Branch y el config_loader la usa con prioridad
sobre ai_config (modo legado).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.tenant import Branch, Tenant

logger = logging.getLogger(__name__)

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

_TONE_OPTIONS = ("formal", "amigable", "profesional", "cercano")

_GENERATION_PROMPT = """\
Eres un experto en CRM conversacional para WhatsApp. Con base en la descripción del negocio, \
genera la configuración inicial del bot de calificación.

DESCRIPCIÓN DEL NEGOCIO:
{description}

INDUSTRIA DETECTADA: {industry_key}
DATOS EXTRAÍDOS DEL ONBOARDING:
{extracted_data}

Genera un JSON con exactamente esta estructura (sin texto adicional, solo el JSON):
{{
  "tone": "<uno de: formal, amigable, profesional, cercano>",
  "system_prompt": "<system prompt completo para el bot, en español, máx 800 chars. \
Incluye: nombre del negocio, qué hace, tono de voz, objetivo (calificar al contacto), \
y qué NO debe hacer (no revelar precios exactos, no hacer diagnósticos, etc.). \
Personaliza según la industria.>",
  "qualification_questions": [
    {{"order": 1, "question": "<pregunta natural en español>", "field_key": "<snake_case>"}},
    {{"order": 2, "question": "<pregunta>", "field_key": "<snake_case>"}},
    {{"order": 3, "question": "<pregunta>", "field_key": "<snake_case>"}}
  ]
}}

REGLAS:
- El system_prompt debe ser en segunda persona hacia el bot ("Eres...", "Tu objetivo es...")
- Mínimo 3, máximo 5 preguntas de calificación relevantes para la industria
- Los field_key deben ser snake_case descriptivos (ej: nombre_paciente, edad, motivo_consulta)
- El tono debe reflejar la formalidad del giro
- Solo JSON válido, sin comentarios
"""


class BotConfigGeneratorService:
    """Genera y persiste la configuración inicial del bot desde el onboarding."""

    async def generate_and_apply(
        self,
        tenant: Tenant,
        extracted_data: dict[str, Any],
        db: AsyncSession,
    ) -> int:
        """Genera bot config para todas las branches activas del tenant.

        Retorna el número de branches configuradas.
        """
        if not tenant.onboarding_description:
            logger.info("bot_config_generator: tenant %s sin descripción — omitiendo", tenant.id)
            return 0

        # Generar la config una sola vez para el tenant
        config = await self._call_claude(
            description=tenant.onboarding_description,
            industry_key=tenant.industry_key,
            extracted_data=extracted_data,
        )
        if config is None:
            return 0

        # Aplicar a todas las branches activas
        branches_result = await db.execute(
            select(Branch).where(
                Branch.tenant_id == tenant.id,
                Branch.is_active.is_(True),
            )
        )
        branches = branches_result.scalars().all()

        now = datetime.now(timezone.utc)
        applied = 0
        for branch in branches:
            # No sobreescribir si el usuario ya editó manualmente
            if branch.bot_config_updated_at is not None:
                continue
            branch.bot_system_prompt = config["system_prompt"]
            branch.bot_tone = config["tone"]
            branch.bot_qualification_questions = config["qualification_questions"]
            branch.bot_config_generated_at = now
            applied += 1

        if applied:
            await db.flush()
            logger.info(
                "bot_config_generator: aplicado a %d branch(es) del tenant %s",
                applied, tenant.id,
            )
        return applied

    async def regenerate_for_branch(
        self,
        branch: Branch,
        tenant: Tenant,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """Regenera la config para una branch específica (llamado desde el endpoint)."""
        description = tenant.onboarding_description or branch.business_description
        if not description:
            return None

        config = await self._call_claude(
            description=description,
            industry_key=tenant.industry_key,
            extracted_data=tenant.onboarding_extracted_data or {},
        )
        if config is None:
            return None

        now = datetime.now(timezone.utc)
        branch.bot_system_prompt = config["system_prompt"]
        branch.bot_tone = config["tone"]
        branch.bot_qualification_questions = config["qualification_questions"]
        branch.bot_config_generated_at = now
        branch.bot_config_updated_at = None  # reset manual edits flag
        await db.flush()
        return config

    async def _call_claude(
        self,
        description: str,
        industry_key: str,
        extracted_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        extracted_str = json.dumps(extracted_data, ensure_ascii=False, indent=2) if extracted_data else "(sin datos extraídos)"
        prompt = _GENERATION_PROMPT.format(
            description=description[:3000],
            industry_key=industry_key,
            extracted_data=extracted_str[:800],
        )
        try:
            resp = await _anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            config = json.loads(raw)
            # Validate minimal structure
            if not all(k in config for k in ("tone", "system_prompt", "qualification_questions")):
                logger.warning("bot_config_generator: respuesta Claude incompleta")
                return None
            if config["tone"] not in _TONE_OPTIONS:
                config["tone"] = "amigable"
            return config
        except Exception:
            logger.exception("bot_config_generator: error llamando Claude")
            return None


bot_config_generator = BotConfigGeneratorService()
