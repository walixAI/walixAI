"""
Servicio de inferencia de industria para el onboarding conversacional de Walix.

Analiza texto libre (descripción del negocio del usuario) y determina qué
Industry Template aplica, usando detección por keywords como fast path y
Claude Haiku como confirmación semántica.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic
from langfuse import Langfuse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.industry_templates.catalog import INDUSTRY_TEMPLATES, get_all_keywords
from app.industry_templates.onboarding_guide import (
    OPTIONAL_FIELDS,
    get_follow_up_question,
    get_missing_required,
)
from app.models.onboarding_conversation import OnboardingConversation

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
_langfuse = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST,
)

_SYSTEM_PROMPT = """
Eres el asistente de configuración de Walix, un CRM para PyMEs mexicanas.
Analiza la descripción de un negocio y extrae información estructurada.
Responde ÚNICAMENTE con JSON válido, sin texto extra, sin markdown:
{
  "industry_key": "<salud|bienes_raices|educacion|estetica_wellness|automotriz|restaurante|servicios_profesionales|generico>",
  "confidence": <0.0 a 1.0>,
  "extracted": {
    "business_name": "<string o null>",
    "business_description": "<string o null>",
    "main_goal": "<string o null>",
    "city": "<string o null>",
    "team_size": "<string o null>",
    "main_pain": "<string o null>",
    "avg_ticket": "<string o null>",
    "sales_cycle": "<string o null>"
  },
  "reasoning": "<1 oración explicando por qué elegiste esa industria>"
}
Si no encaja claramente en ninguna: industry_key = "generico".
""".strip()


# ── Result dataclass ───────────────────────────────────────────────────────────


@dataclass
class InferenceResult:
    industry_key: str
    confidence: float
    extracted_data: dict[str, Any]
    missing_required: list[str]
    missing_optional: list[str]
    follow_up_questions: list[str]
    reasoning: str


# ── JSON extractor ─────────────────────────────────────────────────────────────


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found: {text[:200]}")
    return json.loads(match.group())


# ── Service ────────────────────────────────────────────────────────────────────


class IndustryInferenceService:
    """Infiere la industria de un negocio a partir de texto libre."""

    # ── Paso 1: fast-path por keywords ────────────────────────────────────────

    def _keyword_inference(self, text: str) -> tuple[str, float]:
        """Detección rápida por conteo de keywords por industria.

        Retorna (industry_key, confidence). Confianza 0.75 si hay un ganador
        claro (≥3 matches y ventaja ≥2 sobre el segundo), 0.0 si no hay señal.
        """
        lowered = text.lower()
        all_kw = get_all_keywords()
        scores: dict[str, int] = {key: 0 for key in all_kw if key != "generico"}

        for industry, keywords in all_kw.items():
            if industry == "generico":
                continue
            for kw in keywords:
                if kw in lowered:
                    scores[industry] += 1

        if not any(scores.values()):
            return "generico", 0.0

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_key, top_count = sorted_scores[0]
        second_count = sorted_scores[1][1] if len(sorted_scores) > 1 else 0

        if top_count >= 3 and (top_count - second_count) >= 2:
            return top_key, 0.75

        # Señal débil: retorna el top sin confianza alta
        if top_count >= 1:
            return top_key, 0.4

        return "generico", 0.0

    # ── Paso 2: confirmación con Claude Haiku ─────────────────────────────────

    async def _claude_inference(
        self, text: str, preliminary_key: str, preliminary_conf: float
    ) -> tuple[str, float, dict[str, Any], str]:
        """Llama a Claude Haiku para análisis semántico.

        Retorna (industry_key, confidence, extracted_data, reasoning).
        En caso de error usa el resultado del fast-path como fallback.
        """
        try:
            response = await _anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=500,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Descripción del negocio:\n{text}"}],
            )
            parsed = _extract_json(response.content[0].text)

            industry_key = str(parsed.get("industry_key", "generico"))
            if industry_key not in INDUSTRY_TEMPLATES:
                industry_key = "generico"

            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            extracted = dict(parsed.get("extracted") or {})
            reasoning = str(parsed.get("reasoning", ""))

            return industry_key, confidence, extracted, reasoning

        except Exception:
            logger.exception("industry_inference: Claude call failed — using keyword fallback")
            return preliminary_key, preliminary_conf, {}, "Inferido por keywords (Claude no disponible)"

    # ── Paso 4: follow-up questions ───────────────────────────────────────────

    @staticmethod
    def _build_follow_up_questions(
        missing_required: list[str],
        missing_optional: list[str],
    ) -> list[str]:
        """Genera hasta 2 preguntas de follow-up priorizando campos requeridos."""
        questions: list[str] = []
        priority = missing_required + missing_optional
        for key in priority:
            if len(questions) >= 2:
                break
            questions.append(get_follow_up_question(key))
        return questions

    # ── Método principal ──────────────────────────────────────────────────────

    async def analyze(
        self,
        text: str,
        session_id: uuid.UUID,
        turn: int,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID | None = None,
    ) -> InferenceResult:
        """Analiza texto libre e infiere la industria del negocio.

        Pasos: keyword fast-path → Claude Haiku → campos faltantes →
        follow-up questions → persist → trazar en Langfuse.
        """
        # Paso 1 — fast-path keywords
        preliminary_key, preliminary_conf = self._keyword_inference(text)

        # Paso 2 — confirmación semántica con Claude
        industry_key, confidence, extracted, reasoning = await self._claude_inference(
            text, preliminary_key, preliminary_conf
        )

        # Paso 3 — campos faltantes
        missing_required = get_missing_required(extracted)
        missing_optional = [
            f["key"] for f in OPTIONAL_FIELDS if not extracted.get(f["key"])
        ]

        # Paso 4 — follow-up questions (máx 2 por turno)
        follow_up_questions = self._build_follow_up_questions(
            missing_required, missing_optional
        )

        # Paso 5 — persistir turno en onboarding_conversations
        if tenant_id is not None:
            try:
                db.add(OnboardingConversation(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    turn=turn,
                    user_message=text,
                    extracted_data=extracted,
                    inferred_industry=industry_key,
                    confidence=confidence,
                    follow_up_questions=follow_up_questions,
                ))
                await db.flush()
            except Exception:
                logger.exception(
                    "industry_inference: failed to persist turn session=%s turn=%d",
                    session_id,
                    turn,
                )

        # Paso 6 — trazar en Langfuse
        self._trace(
            session_id=session_id,
            turn=turn,
            industry_key=industry_key,
            confidence=confidence,
            preliminary_key=preliminary_key,
            text_length=len(text),
        )

        return InferenceResult(
            industry_key=industry_key,
            confidence=confidence,
            extracted_data=extracted,
            missing_required=missing_required,
            missing_optional=missing_optional,
            follow_up_questions=follow_up_questions,
            reasoning=reasoning,
        )

    # ── Helper: acumular texto de la sesión ───────────────────────────────────

    async def get_accumulated_text(
        self, session_id: uuid.UUID, db: AsyncSession
    ) -> str:
        """Concatena todos los user_message de la sesión en orden de turn."""
        rows = (
            await db.execute(
                select(OnboardingConversation.user_message)
                .where(OnboardingConversation.session_id == session_id)
                .order_by(OnboardingConversation.turn.asc())
            )
        ).scalars().all()
        return "\n\n".join(rows)

    # ── Langfuse ──────────────────────────────────────────────────────────────

    def _trace(
        self,
        *,
        session_id: uuid.UUID,
        turn: int,
        industry_key: str,
        confidence: float,
        preliminary_key: str,
        text_length: int,
    ) -> None:
        try:
            with _langfuse.start_as_current_observation(
                as_type="generation",
                name="industry_inference",
                model=CLAUDE_MODEL,
                metadata={
                    "session_id": str(session_id),
                    "turn": turn,
                    "industry_key": industry_key,
                    "confidence": confidence,
                    "preliminary_key": preliminary_key,
                    "text_length": text_length,
                    "sprint": "8b",
                    "service": "industry_inference",
                    "tag": f"sprint:8b,service:industry_inference,turn:{turn}",
                },
            ):
                pass
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.run_in_executor(None, _langfuse.flush)
        except Exception:
            logger.exception("industry_inference: Langfuse trace failed session=%s", session_id)
