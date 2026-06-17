"""
Sprint 8B — Endpoints de onboarding conversacional e industry settings.

Rutas:
  GET  /api/v1/onboarding/prompt-guide     — guía de qué escribir (sin auth)
  POST /api/v1/onboarding/analyze          — inferencia de industria por texto libre
  POST /api/v1/onboarding/confirm          — confirma y aplica el template al tenant (JWT)
  GET  /api/v1/settings/industry           — industria actual + templates disponibles (owner)
  POST /api/v1/settings/industry           — cambia la industria del tenant (owner)

Convive con app/api/onboarding.py (Sprint 4) que gestiona generate/refine/approve
del ai_config de la branch.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.industry_templates.catalog import INDUSTRY_KEYS, INDUSTRY_TEMPLATES, get_template
from app.industry_templates.onboarding_guide import (
    OPTIONAL_FIELDS,
    PROMPT_EXAMPLE,
    PROMPT_TOPICS,
    REQUIRED_FIELDS,
)
from app.models.user import User, UserRole
from app.services.industry_inference import IndustryInferenceService
from app.services.tenant_setup import TenantSetupService

logger = logging.getLogger(__name__)

# ── Routers ────────────────────────────────────────────────────────────────────

onboarding_router = APIRouter(prefix="/v1/onboarding", tags=["industry-onboarding"])
settings_router = APIRouter(prefix="/v1/settings", tags=["industry-settings"])

_inference_svc = IndustryInferenceService()
_setup_svc = TenantSetupService()

# ── Auth helpers ───────────────────────────────────────────────────────────────

_OWNER_ROLES = (UserRole.OWNER,)


def _require_owner(user: User) -> None:
    if user.role not in _OWNER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner puede gestionar la configuración de industria",
        )


# ── Schemas ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    session_id: uuid.UUID | None = None


class ConfirmRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    industry_key: str
    override_industry: bool = False


class IndustryChangeRequest(BaseModel):
    industry_key: str
    confirm_reset: bool = False


# ── GET /v1/onboarding/prompt-guide ───────────────────────────────────────────

@onboarding_router.get("/prompt-guide")
async def get_prompt_guide() -> dict:
    """Retorna la guía de qué escribir para el onboarding. Sin autenticación."""
    return {
        "example": PROMPT_EXAMPLE,
        "suggested_topics": PROMPT_TOPICS,
        "required_fields": REQUIRED_FIELDS,
        "optional_fields": OPTIONAL_FIELDS,
        "min_words_hint": 30,
    }


# ── POST /v1/onboarding/analyze ───────────────────────────────────────────────

@onboarding_router.post("/analyze")
async def analyze_description(
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Infiere la industria a partir del texto libre del usuario.

    No requiere JWT — el usuario puede describir su negocio antes de crear cuenta.
    Si se provee session_id, concatena los mensajes previos del turno acumulado.
    """
    session_id = body.session_id or uuid.uuid4()

    # Acumular texto de turnos previos para análisis multi-turno
    if body.session_id is not None:
        accumulated = await _inference_svc.get_accumulated_text(session_id, db)
        full_text = f"{accumulated}\n\n{body.description}".strip() if accumulated else body.description
    else:
        full_text = body.description

    # Umbral mínimo de palabras sobre el texto completo acumulado
    if len(full_text.split()) < 20:
        return {
            "session_id": str(session_id),
            "needs_more_info": True,
            "hint": "Cuéntanos un poco más para configurar Walix mejor.",
        }

    # Detectar turno actual
    from sqlalchemy import func, select
    from app.models.onboarding_conversation import OnboardingConversation

    turn_count = (
        await db.execute(
            select(func.count(OnboardingConversation.id)).where(
                OnboardingConversation.session_id == session_id
            )
        )
    ).scalar_one()
    turn = turn_count + 1

    result = await _inference_svc.analyze(
        text=full_text,
        session_id=session_id,
        turn=turn,
        db=db,
    )

    # Si faltan campos requeridos: pedir más info
    if result.missing_required or result.follow_up_questions:
        return {
            "session_id": str(session_id),
            "needs_more_info": True,
            "follow_up_questions": result.follow_up_questions,
            "industry_key": None,
            "turn": turn,
        }

    # Confianza suficiente y campos completos
    if result.confidence >= 0.60 and not result.missing_required:
        tmpl = get_template(result.industry_key)
        return {
            "session_id": str(session_id),
            "needs_more_info": False,
            "industry_key": result.industry_key,
            "industry_label": tmpl["label"],
            "entity_name": tmpl["entity_name"],
            "confidence": result.confidence,
            "pipeline_preview": tmpl["pipeline_stages"],
            "extracted_data": result.extracted_data,
            "reasoning": result.reasoning,
        }

    # Confianza baja: pedir más info
    return {
        "session_id": str(session_id),
        "needs_more_info": True,
        "follow_up_questions": result.follow_up_questions,
        "industry_key": result.industry_key,
        "turn": turn,
    }


# ── POST /v1/onboarding/confirm ───────────────────────────────────────────────

@onboarding_router.post("/confirm")
async def confirm_onboarding(
    body: ConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Confirma la industria y aplica el template al tenant del usuario autenticado."""
    from app.models.tenant import Tenant

    if body.industry_key not in INDUSTRY_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"industry_key inválido. Opciones: {', '.join(INDUSTRY_KEYS)}",
        )

    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    # Recuperar extracted_data de la sesión si existe, o inferir ahora
    extracted_data: dict = {}
    try:
        analyze_result = await _inference_svc.analyze(
            text=body.description,
            session_id=None,
            turn=1,
            db=db,
        )
        extracted_data = analyze_result.extracted_data or {}
    except Exception:
        pass

    summary = await _setup_svc.apply_industry_template(
        tenant=tenant,
        industry_key=body.industry_key,
        onboarding_description=body.description,
        extracted_data=extracted_data,
        db=db,
    )

    template = get_template(body.industry_key)
    await db.refresh(tenant)

    # Obtener stages recién creadas para la respuesta
    from sqlalchemy import select
    from app.models.pipeline import PipelineStage

    stages = (
        await db.execute(
            select(PipelineStage)
            .where(
                PipelineStage.tenant_id == tenant.id,
                PipelineStage.is_archived.is_(False),
            )
            .order_by(PipelineStage.order_index)
        )
    ).scalars().all()

    bot_config_generated: bool = summary.get("bot_config_generated", False)
    bot_config: dict | None = summary.get("bot_config")

    next_steps = [
        "Conecta tu número de WhatsApp Business",
        "Invita a tu equipo",
    ]
    if bot_config_generated:
        next_steps.insert(0, "Tu bot ya está configurado — puedes ajustarlo en Configuración")
    else:
        next_steps.insert(0, "Configura tu bot de WhatsApp en Configuración → Bot IA")

    return {
        "message": f"Tu Walix está configurado para {template['label']}",
        "entity_name": tenant.entity_name,
        "entity_plural": tenant.entity_plural,
        "pipeline_stages": [
            {"key": s.stage_key, "label": s.name, "color": s.color}
            for s in stages
        ],
        "bot_config_generated": bot_config_generated,
        "bot_config": bot_config,
        "next_steps": next_steps,
    }


# ── GET /v1/settings/industry ─────────────────────────────────────────────────

@settings_router.get("/industry")
async def get_industry_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retorna la industria actual del tenant y los templates disponibles."""
    _require_owner(current_user)

    from app.models.tenant import Tenant
    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    current_tmpl = get_template(tenant.industry_key)

    available = [
        {
            "key": key,
            "label": tmpl["label"],
            "entity_name": tmpl["entity_name"],
            "entity_plural": tmpl["entity_plural"],
            "pipeline_stages_count": len(tmpl["pipeline_stages"]),
        }
        for key, tmpl in INDUSTRY_TEMPLATES.items()
    ]

    return {
        "current": {
            "industry_key": tenant.industry_key,
            "industry_label": tenant.industry_label or current_tmpl["label"],
            "entity_name": tenant.entity_name,
            "entity_plural": tenant.entity_plural,
            "onboarding_completed_at": (
                tenant.onboarding_completed_at.isoformat()
                if tenant.onboarding_completed_at
                else None
            ),
        },
        "available_templates": available,
    }


# ── POST /v1/settings/industry ────────────────────────────────────────────────

@settings_router.post("/industry")
async def change_industry(
    body: IndustryChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cambia la industria del tenant y recrea el pipeline.

    Requiere confirm_reset=true para evitar cambios accidentales.
    Las leads existentes conservan su stage_key; el frontend mostrará
    'Etapa anterior' si el stage_key no está entre las stages activas.
    """
    _require_owner(current_user)

    if not body.confirm_reset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debes confirmar el cambio de industria (confirm_reset=true)",
        )

    if body.industry_key not in INDUSTRY_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"industry_key inválido. Opciones: {', '.join(INDUSTRY_KEYS)}",
        )

    from app.models.tenant import Tenant
    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    summary = await _setup_svc.apply_industry_template(
        tenant=tenant,
        industry_key=body.industry_key,
        onboarding_description=tenant.onboarding_description or "",
        extracted_data={},
        db=db,
    )

    return {
        **summary,
        "warning": (
            "Las etapas anteriores han sido archivadas. "
            "Los contactos en etapas anteriores mostrarán 'Etapa anterior' "
            "hasta que sean reasignados manualmente."
        ),
    }
