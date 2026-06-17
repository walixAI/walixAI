"""BotConfigGeneratorService — genera la config inicial del bot desde el onboarding.

Usa Claude Haiku para producir en un solo call:
  - bot_system_prompt    : system prompt listo para el bot
  - bot_tone             : tono del bot
  - bot_qualification_questions : preguntas de calificación
  - kb_initial_content   : resumen del negocio para el primer documento KB

El documento KB se indexa automáticamente vía el mismo mecanismo que
app/api/kb.py → POST /fragments (reutiliza _split_with_overlap y
_generate_embeddings de app/ai/ingestion.py — sin duplicar lógica).
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
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
Eres un asistente que configura bots de WhatsApp para negocios.

El negocio se describe así:
{description}

Información extraída:
{extracted_data}

Industria: {industry_key}

Genera en JSON (sin markdown ni texto adicional, solo el JSON):
{{
  "system_prompt": "...",
  "tone": "formal|amigable|profesional|cercano",
  "qualification_questions": [
    {{"order": 1, "question": "...", "field_key": "..."}},
    {{"order": 2, "question": "...", "field_key": "..."}},
    {{"order": 3, "question": "...", "field_key": "..."}}
  ],
  "kb_initial_content": "..."
}}

INSTRUCCIONES:
- system_prompt (máx 500 palabras): incluye nombre del negocio (si está disponible), qué \
ofrece, cómo saludar, cuándo hacer handoff a humano. Dirigido al bot: "Eres...", "Tu objetivo es...".
- tone: refleja la formalidad del giro.
- qualification_questions: entre 3 y 5, en español natural, field_key en snake_case \
(ej: nombre_paciente, motivo_consulta, presupuesto).
- kb_initial_content: resumen en prosa del negocio para el Knowledge Base del bot — servicios \
principales, horarios si se mencionan, precios si existen, datos de contacto, \
cualquier FAQ relevante. Escríbelo como si fuera un documento interno de ayuda. Máx 800 palabras.
"""


@dataclass
class BotConfigResult:
    system_prompt: str
    tone: str
    qualification_questions: list[dict]
    kb_initial_content: str


class BotConfigGeneratorService:
    """Genera y persiste la configuración inicial del bot desde el onboarding."""

    # ── Public methods ──────────────────────────────────────────────────────────

    async def generate_and_apply(
        self,
        tenant: Tenant,
        extracted_data: dict[str, Any],
        db: AsyncSession,
    ) -> int:
        """Genera bot config para todas las branches activas del tenant.

        No sobreescribe branches que el usuario ya editó manualmente.
        Retorna el número de branches configuradas.
        """
        if not tenant.onboarding_description:
            logger.info("bot_config_generator: tenant %s sin descripción — omitiendo", tenant.id)
            return 0

        result = await self._call_claude(
            description=tenant.onboarding_description,
            industry_key=tenant.industry_key,
            extracted_data=extracted_data,
        )
        if result is None:
            return 0

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
            if branch.bot_config_updated_at is not None:
                # User manually edited — don't overwrite
                continue
            branch.bot_system_prompt = result.system_prompt
            branch.bot_tone = result.tone
            branch.bot_qualification_questions = result.qualification_questions
            branch.bot_config_generated_at = now

            # Index the KB document for this branch
            await self._create_initial_kb_document(
                tenant_id=tenant.id,
                branch_id=branch.id,
                content=result.kb_initial_content,
                title="Descripción del negocio (generado automáticamente)",
                db=db,
            )
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
        """Regenera la config para una branch específica (llamado desde el endpoint PATCH)."""
        description = tenant.onboarding_description or branch.business_description
        if not description:
            return None

        result = await self._call_claude(
            description=description,
            industry_key=tenant.industry_key,
            extracted_data=tenant.onboarding_extracted_data or {},
        )
        if result is None:
            return None

        now = datetime.now(timezone.utc)
        branch.bot_system_prompt = result.system_prompt
        branch.bot_tone = result.tone
        branch.bot_qualification_questions = result.qualification_questions
        branch.bot_config_generated_at = now
        branch.bot_config_updated_at = None  # reset manual edits flag

        await self._create_initial_kb_document(
            tenant_id=branch.tenant_id,
            branch_id=branch.id,
            content=result.kb_initial_content,
            title="Descripción del negocio (generado automáticamente)",
            db=db,
        )

        await db.flush()
        return {
            "system_prompt": result.system_prompt,
            "tone": result.tone,
            "qualification_questions": result.qualification_questions,
            "kb_initial_content": result.kb_initial_content,
        }

    # ── Private helpers ─────────────────────────────────────────────────────────

    async def _call_claude(
        self,
        description: str,
        industry_key: str,
        extracted_data: dict[str, Any],
    ) -> BotConfigResult | None:
        extracted_str = (
            json.dumps(extracted_data, ensure_ascii=False, indent=2)
            if extracted_data
            else "(sin datos extraídos)"
        )
        prompt = _GENERATION_PROMPT.format(
            description=description[:3000],
            industry_key=industry_key,
            extracted_data=extracted_str[:800],
        )
        try:
            resp = await _anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)

            required = ("system_prompt", "tone", "qualification_questions", "kb_initial_content")
            if not all(k in data for k in required):
                logger.warning("bot_config_generator: respuesta Claude incompleta: %s", list(data.keys()))
                # Tolerate missing kb_initial_content by falling back to description
                if "kb_initial_content" not in data:
                    data["kb_initial_content"] = description[:2000]

            if data.get("tone") not in _TONE_OPTIONS:
                data["tone"] = "amigable"

            return BotConfigResult(
                system_prompt=data["system_prompt"],
                tone=data["tone"],
                qualification_questions=data.get("qualification_questions", []),
                kb_initial_content=data.get("kb_initial_content", ""),
            )
        except Exception:
            logger.exception("bot_config_generator: error llamando Claude")
            return None

    async def _create_initial_kb_document(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        content: str,
        title: str,
        db: AsyncSession,
    ) -> None:
        """Indexa el contenido en el KB del branch usando el mismo mecanismo que /api/kb/fragments.

        Reutiliza _split_with_overlap, _generate_embeddings y _sha256 de app/ai/ingestion —
        no duplica lógica. Si OPENAI_API_KEY no está configurado, lo omite con un warning.
        """
        if not content or not content.strip():
            return

        if not getattr(settings, "OPENAI_API_KEY", None):
            logger.warning("bot_config_generator: OPENAI_API_KEY no configurado — KB no indexado")
            return

        from app.ai.ingestion import _generate_embeddings, _sha256, _split_with_overlap
        from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
        from openai import AsyncOpenAI

        content_hash = _sha256(content)

        # Skip if this exact content is already indexed (idempotent)
        existing = (await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.content_hash == content_hash,
            )
        )).scalar_one_or_none()
        if existing:
            logger.info("bot_config_generator: KB doc ya existe (hash=%s) — omitiendo", content_hash[:8])
            return

        chunks = _split_with_overlap(content)
        if not chunks:
            return

        try:
            oai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            embeddings = await _generate_embeddings(oai, [c["text"] for c in chunks])
        except Exception:
            logger.exception("bot_config_generator: error generando embeddings para KB inicial")
            return

        now = datetime.now(timezone.utc)
        doc_id = uuid.uuid4()
        doc = KnowledgeDocument(
            id=doc_id,
            branch_id=branch_id,
            tenant_id=tenant_id,
            filename=f"onboarding_{doc_id.hex[:8]}.txt",
            title=title,
            content=content,
            content_hash=content_hash,
            chunk_count=len(chunks),
            indexed_at=now,
            is_auto_generated=True,
        )
        db.add(doc)
        await db.flush()

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            db.add(KnowledgeChunk(
                id=uuid.uuid4(),
                document_id=doc_id,
                tenant_id=tenant_id,
                chunk_index=i,
                content=chunk["text"],
                embedding=emb,
                token_count=chunk.get("token_count"),
                chunk_metadata={"section": chunk.get("section", ""), "title": title, "source": "onboarding"},
            ))

        logger.info(
            "bot_config_generator: KB doc creado tenant=%s branch=%s chunks=%d",
            tenant_id, branch_id, len(chunks),
        )


bot_config_generator = BotConfigGeneratorService()
