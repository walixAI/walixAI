"""Onboarding AI endpoints for Walix.

Workflow:
  1. POST /generate  — Claude Sonnet generates a full ai_config from a business description
  2. POST /refine    — Owner refines a single section via natural language
  3. POST /approve   — Owner promotes the draft to branch.ai_config and activates pipeline
  4. GET  /drafts/{id} — Inspect a draft
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.industry_templates import INDUSTRY_TEMPLATES, _QUALIFICATION_PROMPT_TEMPLATE
from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.onboarding import OnboardingDraft
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch
from app.models.user import User, UserRole

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"
_OWNER_IT = (UserRole.OWNER, UserRole.IT)

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── Fixed values Claude must not override ─────────────────────────────────────
_FIXED_QUAL_KEYS = {
    "prompt_template": _QUALIFICATION_PROMPT_TEMPLATE,
    "status_map": {
        "calificado": "calificado",
        "no_calificado": "perdido",
        "incompleto": "en_calificacion",
        "escalar": "escalado",
    },
    "sentiment_map": {
        "calificado": "interesado",
        "no_calificado": "negativo",
        "incompleto": "neutral",
        "escalar": "urgente",
    },
}

# Text keys that the qualifier's .format() call requires — Claude may omit them.
_REQUIRED_QUAL_TEXT_KEYS = ("objective", "criteria", "disqualifiers", "escalation_triggers")


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    branch_id: uuid.UUID
    business_description: str
    industry: str


class ApproveRequest(BaseModel):
    draft_id: uuid.UUID


class RefineRequest(BaseModel):
    draft_id: uuid.UUID
    section: str   # "bot_persona" | "qualification" | "messages" | "pipeline_stages"
    instruction: str


class DraftOut(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    tenant_id: uuid.UUID
    generated_config: dict[str, Any]
    business_input: str
    status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BranchOnboardingOut(BaseModel):
    id: uuid.UUID
    name: str
    ai_config: dict[str, Any] | None
    onboarding_status: str
    bot_name: str | None
    industry: str | None

    model_config = ConfigDict(from_attributes=True)


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _require_owner_it(user: User) -> None:
    if user.role not in _OWNER_IT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner o IT pueden gestionar el onboarding",
        )


def _require_owner(user: User) -> None:
    if user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner puede aprobar la configuración",
        )


async def _get_branch_for_tenant(
    branch_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> Branch:
    branch = await db.get(Branch, branch_id)
    if branch is None or branch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return branch


async def _get_draft_for_tenant(
    draft_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> OnboardingDraft:
    draft = await db.get(OnboardingDraft, draft_id)
    if draft is None or draft.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Draft no encontrado")
    return draft


# ── Claude helpers ─────────────────────────────────────────────────────────────

def _build_generator_prompt(
    industry: str,
    business_description: str,
    base_template: dict[str, Any],
) -> str:
    # Strip the heavy prompt_template and fixed maps from the template shown to Claude
    # to avoid noise — we inject them ourselves after generation.
    qual_ctx = {
        k: v for k, v in base_template["qualification"].items()
        if k not in ("prompt_template", "status_map", "sentiment_map")
    }
    template_ctx = {
        "bot_persona": base_template["bot_persona"],
        "qualification": qual_ctx,
        "messages": base_template["messages"],
        "channel_rules": base_template["channel_rules"],
    }

    schema = {
        "bot_persona": {
            "name": "NombreBot (corto, 1-2 palabras)",
            "system_prompt": "Eres [nombre], asistente virtual de [negocio]. [Persona, tono, restricciones, objetivo]",
        },
        "qualification": {
            "prompt_template": "__FIXED__",
            "objective": "descripción del negocio para el calificador en una línea",
            "criteria": "criterio 1, criterio 2, criterio 3",
            "disqualifiers": "descalificador explícito 1, descalificador 2",
            "escalation_triggers": "trigger de escalado 1, trigger 2",
            "required_fields": [
                {"name": "nombre_campo", "description": "qué contiene o null"}
            ],
            "name_field": "campo_del_nombre_del_prospecto",
            "phone_field": None,
            "status_map": "__FIXED__",
            "sentiment_map": "__FIXED__",
        },
        "messages": {
            "welcome_meta": "Mensaje de bienvenida con {name} como placeholder",
            "escalation": "Frase de transición a agente humano",
        },
        "channel_rules": {
            "max_chars": 300,
            "extra_rules": ["regla específica 1", "regla específica 2"],
        },
        "pipeline_stages": [
            {"name": "Nuevo", "slug": "nuevo", "color": "#9B9893", "order_index": 0, "is_won": False, "is_lost": False},
            {"name": "...", "slug": "...", "color": "#hex", "order_index": 1, "is_won": False, "is_lost": False},
            {"name": "Ganado", "slug": "ganado", "color": "#0F6E56", "order_index": 5, "is_won": True, "is_lost": False},
            {"name": "No califica", "slug": "no_califica", "color": "#993C1D", "order_index": 6, "is_won": False, "is_lost": True},
        ],
    }

    return (
        f"Genera la configuración personalizada de un bot de WhatsApp para el siguiente negocio.\n\n"
        f"INDUSTRIA: {industry}\n\n"
        f"DESCRIPCIÓN DEL NEGOCIO:\n{business_description}\n\n"
        f"PLANTILLA BASE DE LA INDUSTRIA (punto de partida y referencia):\n"
        f"{json.dumps(template_ctx, indent=2, ensure_ascii=False)}\n\n"
        f"Responde ÚNICAMENTE con JSON que siga esta estructura exacta:\n"
        f"{json.dumps(schema, indent=2, ensure_ascii=False)}\n\n"
        f"INSTRUCCIONES:\n"
        f"1. prompt_template, status_map y sentiment_map: escribe exactamente \"__FIXED__\", el sistema los inyecta automáticamente.\n"
        f"2. system_prompt: adapta la plantilla base al negocio — nombre real, servicios, precios si los mencionan, zonas de cobertura, restricciones propias.\n"
        f"3. required_fields: define 4-8 campos relevantes para calificar un prospecto de ESTE negocio.\n"
        f"4. pipeline_stages: propón 4-7 etapas apropiadas para el ciclo de ventas de este negocio. Al menos una is_won=true y una is_lost=true.\n"
        f"5. welcome_meta: cálido, menciona el nombre del negocio, usa {{name}} como placeholder, hace la primera pregunta relevante.\n"
        f"6. Los slugs deben ser snake_case, sin acentos."
    )


def _build_refine_prompt(section: str, instruction: str, current_value: Any) -> str:
    current_json = json.dumps(current_value, indent=2, ensure_ascii=False)
    note = ""
    if section == "qualification":
        note = (
            "\nNOTA: Los campos prompt_template, status_map y sentiment_map son fijos. "
            "Si aparecen en el JSON actual con sus valores reales, devuélvelos exactamente igual. "
            "No los modifiques bajo ninguna circunstancia."
        )
    return (
        f"El owner quiere modificar la sección \"{section}\" de la configuración del bot.\n\n"
        f"Instrucción del owner: {instruction}\n\n"
        f"Configuración actual de la sección \"{section}\":\n{current_json}\n"
        f"{note}\n"
        f"Retorna ÚNICAMENTE el JSON actualizado de la sección \"{section}\", "
        f"sin texto adicional, sin markdown, sin comentarios."
    )


def _extract_json(text: str) -> Any:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    # Try full parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Find first JSON object or array
    match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in response: {text[:300]}")
    return json.loads(match.group())


def _apply_fixed_qualification_keys(config: dict[str, Any], industry: str = "salud") -> None:
    """Forces fixed qualification fields and fills any text keys Claude may have omitted."""
    if "qualification" not in config:
        return
    config["qualification"].update(_FIXED_QUAL_KEYS)

    # Fill any text key that was skipped by Claude, using the industry template as fallback.
    base_qual = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["salud"])["qualification"]
    for key in _REQUIRED_QUAL_TEXT_KEYS:
        if not config["qualification"].get(key):
            config["qualification"][key] = base_qual.get(key, "")
            logger.warning(
                "onboarding: generated config missing '%s' — using %s template fallback",
                key, industry,
            )


async def _call_claude_generate(prompt: str) -> dict[str, Any]:
    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=(
            "Eres un especialista en configuración de bots conversacionales de WhatsApp "
            "para empresas mexicanas. Responde ÚNICAMENTE con JSON válido, "
            "sin markdown, sin comentarios, sin texto adicional."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(response.content[0].text)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=DraftOut, status_code=201)
async def generate_onboarding(
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftOut:
    """Generates a new ai_config draft using Claude Sonnet from a business description."""
    _require_owner_it(current_user)

    branch = await _get_branch_for_tenant(body.branch_id, current_user.tenant_id, db)

    industry = body.industry if body.industry in INDUSTRY_TEMPLATES else "salud"
    base_template = INDUSTRY_TEMPLATES[industry]

    prompt = _build_generator_prompt(industry, body.business_description, base_template)

    # Call Claude — retry once on parse failure
    generated: dict[str, Any] = {}
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            generated = await _call_claude_generate(prompt)
            break
        except (ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
            logger.warning("generate_onboarding: parse attempt %d failed: %s", attempt + 1, exc)
    else:
        logger.error("generate_onboarding: both attempts failed for branch %s", body.branch_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo generar la configuración. Intenta de nuevo.",
        ) from last_exc

    # Always enforce fixed qualification values + fill any keys Claude omitted
    _apply_fixed_qualification_keys(generated, industry)

    # Persist draft
    draft = OnboardingDraft(
        branch_id=branch.id,
        tenant_id=current_user.tenant_id,
        generated_config=generated,
        business_input=body.business_description,
        status="pending_review",
    )
    db.add(draft)

    # Update branch
    branch.business_description = body.business_description
    branch.industry = industry
    branch.onboarding_status = "draft"

    await db.commit()
    await db.refresh(draft)
    return DraftOut.model_validate(draft)


@router.post("/approve", response_model=BranchOnboardingOut)
async def approve_onboarding(
    body: ApproveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BranchOnboardingOut:
    """Promotes a pending_review draft to branch.ai_config and activates pipeline stages."""
    _require_owner(current_user)

    draft = await _get_draft_for_tenant(body.draft_id, current_user.tenant_id, db)

    if draft.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El draft tiene status '{draft.status}', solo se puede aprobar uno en 'pending_review'",
        )

    branch = await _get_branch_for_tenant(draft.branch_id, current_user.tenant_id, db)
    config = draft.generated_config

    # 1. Copy config to branch
    branch.ai_config = config
    branch.bot_name = config.get("bot_persona", {}).get("name")
    branch.onboarding_status = "active"

    # 2. Replace pipeline stages for this branch
    if "pipeline_stages" in config and config["pipeline_stages"]:
        # Deactivate existing stages
        existing_rows = await db.execute(
            select(PipelineStage).where(
                PipelineStage.branch_id == branch.id,
                PipelineStage.is_active.is_(True),
            )
        )
        for stage in existing_rows.scalars().all():
            stage.is_active = False

        # Create new stages from generated config
        for idx, spec in enumerate(config["pipeline_stages"]):
            db.add(
                PipelineStage(
                    branch_id=branch.id,
                    tenant_id=current_user.tenant_id,
                    name=spec.get("name", f"Etapa {idx + 1}"),
                    slug=spec.get("slug", f"etapa_{idx + 1}"),
                    color=spec.get("color"),
                    order_index=spec.get("order_index", idx),
                    is_won=bool(spec.get("is_won", False)),
                    is_lost=bool(spec.get("is_lost", False)),
                )
            )

    # 3. Mark draft approved
    draft.status = "approved"
    draft.approved_by = current_user.id
    draft.approved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(branch)
    return BranchOnboardingOut.model_validate(branch)


@router.post("/refine", response_model=DraftOut)
async def refine_onboarding(
    body: RefineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftOut:
    """Refines a single section of a draft using a natural language instruction."""
    _require_owner_it(current_user)

    _VALID_SECTIONS = {"bot_persona", "qualification", "messages", "pipeline_stages", "channel_rules"}
    if body.section not in _VALID_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Sección inválida. Opciones: {', '.join(sorted(_VALID_SECTIONS))}",
        )

    draft = await _get_draft_for_tenant(body.draft_id, current_user.tenant_id, db)

    if draft.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede refinar un draft ya aprobado",
        )

    current_section = draft.generated_config.get(body.section)
    if current_section is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La sección '{body.section}' no existe en este draft",
        )

    prompt = _build_refine_prompt(body.section, body.instruction, current_section)

    try:
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=(
                "Eres un especialista en configuración de bots de WhatsApp. "
                "Retorna ÚNICAMENTE el JSON solicitado, sin texto adicional ni markdown."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        updated_section = _extract_json(response.content[0].text)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("refine_onboarding: parse failed for draft %s section %s: %s", body.draft_id, body.section, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo refinar la sección. Intenta de nuevo.",
        ) from exc

    # Merge updated section into the config (copy to avoid SQLAlchemy mutation tracking issues)
    new_config = dict(draft.generated_config)
    new_config[body.section] = updated_section

    # Re-enforce fixed qualification fields after any refine
    branch = await db.get(Branch, draft.branch_id)
    branch_industry = (branch.industry if branch else None) or "salud"
    _apply_fixed_qualification_keys(new_config, branch_industry)

    draft.generated_config = new_config

    await db.commit()
    await db.refresh(draft)
    return DraftOut.model_validate(draft)


@router.get("/drafts/{draft_id}", response_model=DraftOut)
async def get_draft(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftOut:
    """Returns a draft by ID. Accessible by owner or IT of the same tenant."""
    _require_owner_it(current_user)
    draft = await _get_draft_for_tenant(draft_id, current_user.tenant_id, db)
    return DraftOut.model_validate(draft)
