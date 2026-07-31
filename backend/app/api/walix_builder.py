"""B2 — Walix Builder: chat de composición de recetas + guardado en copilot_capabilities.

Separado de ai_copilot.py porque es un sistema distinto:
  - ai_copilot.py: sesión conversacional multi-turno para usuarios finales,
                   historial persistido en DB, 18 tools nativas del CRM.
  - walix_builder.py: chat de diseño para admins, conversación stateless
                      (el estado vive en el frontend, no hay tabla de historial),
                      solo compone y guarda recetas — NO ejecuta ninguna tool del
                      CRM todavía (la ejecución dinámica real es B3).

Rutas:
  POST /api/ai/builder/chat  — un turno de composición (OWNER/PLATFORM_OWNER only)
  POST /api/ai/builder/save  — guarda la receta en copilot_capabilities (OWNER only)
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_engine import CLAUDE_MODEL, _anthropic  # reusar cliente y modelo
from app.ai.copilot_tools import COPILOT_TOOLS
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.ai_memory import CopilotCapability
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["builder"])

# ── Auth guard ─────────────────────────────────────────────────────────────────

_OWNER_ROLES = (UserRole.OWNER, UserRole.PLATFORM_OWNER)


def _require_owner(current_user: User) -> None:
    if current_user.role not in _OWNER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el propietario puede gestionar recetas del Walix Builder",
        )


# ── Primitive catalog (derived from COPILOT_TOOLS — never a manual parallel list) ──

# Names of the 7 write tools from C3. This set is the single source of truth
# for risk classification in the system prompt; keeping it adjacent to COPILOT_TOOLS
# (same package) avoids drift between catalog and risk tags.
_WRITE_TOOL_NAMES: frozenset[str] = frozenset({
    "create_contact",
    "create_deal",
    "move_deal_stage",
    "add_note",
    "create_task",
    "prepare_whatsapp_message",
    "set_monthly_goal",
})

_MAX_STEPS = 5

# Derived at import time from the live catalog — always in sync.
_VALID_TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in COPILOT_TOOLS)
_VALID_ROLES: frozenset[str] = frozenset(r.value for r in UserRole)


# ── System prompt (built once at import from live COPILOT_TOOLS) ───────────────

def _build_system_prompt() -> str:
    """Generate the Builder system prompt from the real COPILOT_TOOLS catalog.

    This function is called ONCE at module load so the prompt is always in sync
    with the actual tool definitions — no manual copy that can drift.
    risk=write if tool is in _WRITE_TOOL_NAMES, else risk=read.
    """
    lines: list[str] = []
    for tool in COPILOT_TOOLS:
        risk = "write" if tool["name"] in _WRITE_TOOL_NAMES else "read"
        lines.append(f"- **{tool['name']}** (risk={risk}): {tool['description']}")
    primitives_block = "\n".join(lines)

    return f"""Eres el asistente de diseño del Walix Builder. Tu único rol es ayudar al administrador a componer una receta: una secuencia de hasta {_MAX_STEPS} pasos que encadena primitivas del catálogo de walixAI. NO ejecutas nada del CRM — solo diseñas y, cuando el admin confirme, produces el JSON final para que la UI lo guarde.

## Catálogo de primitivas disponibles

{primitives_block}

## Flujo obligatorio (5 pasos en orden)

1. **Entender el objetivo**: Pregunta qué quiere automatizar el admin. Reformula con tus propias palabras para confirmar que lo entendiste correctamente.

2. **Proponer la receta** (máx. {_MAX_STEPS} pasos): Sugiere la secuencia de primitivas con una nota breve de para qué sirve cada paso. Si el objetivo requiere una capacidad que no existe en el catálogo, díselo explícitamente — nunca inventes herramientas fuera del catálogo.

3. **Confirmar la receta**: Espera que el admin apruebe o pida ajustes. Itera hasta tener aprobación explícita.

4. **Preguntar configuración UNO A UNO** (en este orden, nunca agrupados en una sola pregunta):
   a. ¿Quién puede activar esta receta? (todos / por rol / usuarios específicos)
   b. ¿En qué canal estará disponible? (web / whatsapp / ambos)
   c. ¿Requiere confirmación antes de ejecutar?
   d. ¿Tiene límite de ejecuciones diarias? (número exacto o sin límite)
   e. ¿Cuál es el nombre de la receta?
   f. ¿Qué frases de disparo la activarán? (lista de frases clave separadas por coma)

5. **Producir el resultado final**: Cuando el admin confirme toda la configuración, responde EXACTAMENTE con la palabra clave `RECIPE_READY` en su propia línea, seguida inmediatamente de un bloque ```json con el JSON de la receta:

RECIPE_READY
```json
{{
  "name": "...",
  "description": "...",
  "steps": [{{"tool": "nombre_primitiva", "note": "para qué sirve este paso"}}],
  "trigger_phrases": ["frase 1", "frase 2"],
  "scope_type": "all",
  "scope_roles": [],
  "scope_user_ids": [],
  "channels": ["web"],
  "require_confirmation": true,
  "daily_limit": null
}}
```

## Restricciones

- Solo usa primitivas del catálogo de arriba. Nunca inventes nombres de herramientas.
- Máximo {_MAX_STEPS} pasos por receta.
- `scope_roles` solo acepta valores del enum UserRole de walixAI en minúsculas: owner, gerente, asesor, doctor, soporte, it, platform_owner.
- `channels` solo acepta "web" y/o "whatsapp".
- `scope_type` solo acepta: "all", "role", "user".
- Responde siempre en español.
- No ejecutas nada del CRM en esta conversación — solo compones y guardas la receta.
"""


_SYSTEM_PROMPT = _build_system_prompt()


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class BuilderMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class BuilderChatRequest(BaseModel):
    messages: list[BuilderMessage] = Field(..., min_length=1, max_length=40)


class BuilderChatResponse(BaseModel):
    reply: str


class RecipeStep(BaseModel):
    tool: str
    note: str | None = None


class BuilderSaveRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    steps: list[RecipeStep] = Field(..., min_length=1, max_length=_MAX_STEPS)
    trigger_phrases: list[str] = Field(default_factory=list)
    scope_type: str = Field(default="all", pattern="^(all|role|user)$")
    scope_roles: list[str] = Field(default_factory=list)
    scope_user_ids: list[uuid.UUID] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=lambda: ["web"])
    require_confirmation: bool = True
    daily_limit: int | None = Field(default=None, ge=1)


class BuilderSaveResponse(BaseModel):
    id: uuid.UUID


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/builder/chat", response_model=BuilderChatResponse)
async def builder_chat(
    body: BuilderChatRequest,
    current_user: User = Depends(get_current_user),
) -> BuilderChatResponse:
    """One stateless turn of the recipe composition chat.

    Conversation state lives in the frontend — no DB persistence.
    OWNER / PLATFORM_OWNER only.
    """
    _require_owner(current_user)

    messages: list[dict[str, Any]] = [
        {"role": m.role, "content": m.content} for m in body.messages
    ]

    response = await _anthropic.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=messages,
    )

    reply = next(
        (block.text for block in response.content if hasattr(block, "text")),
        "",
    )
    return BuilderChatResponse(reply=reply)


@router.post(
    "/builder/save",
    response_model=BuilderSaveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def builder_save(
    body: BuilderSaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BuilderSaveResponse:
    """Validates and persists a recipe in copilot_capabilities.

    Validation (hard reject — never silently filter):
    - Each step.tool must exist in COPILOT_TOOLS.
    - scope_roles values must be valid UserRole enum values.
    - channels must contain only "web" and/or "whatsapp".
    OWNER / PLATFORM_OWNER only.
    """
    _require_owner(current_user)

    # Reject unknown step tools — don't silently filter, so the caller knows
    unknown_tools = [s.tool for s in body.steps if s.tool not in _VALID_TOOL_NAMES]
    if unknown_tools:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Herramientas desconocidas en los pasos: {unknown_tools}. "
                f"Solo se permiten herramientas del catálogo de walixAI."
            ),
        )

    invalid_roles = [r for r in body.scope_roles if r not in _VALID_ROLES]
    if invalid_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Roles inválidos: {invalid_roles}. "
                f"Valores permitidos: {sorted(_VALID_ROLES)}"
            ),
        )

    valid_channels = {"web", "whatsapp"}
    invalid_channels = [c for c in body.channels if c not in valid_channels]
    if invalid_channels:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Canales inválidos: {invalid_channels}. Solo se permite 'web' y/o 'whatsapp'.",
        )

    recipe_json: dict[str, Any] = {
        "steps": [{"tool": s.tool, "note": s.note} for s in body.steps],
    }

    capability = CopilotCapability(
        tenant_id=current_user.tenant_id,
        name=body.name,
        description=body.description,
        kind="recipe",
        recipe_json=recipe_json,
        trigger_phrases=body.trigger_phrases,
        scope_type=body.scope_type,
        scope_roles=body.scope_roles,
        scope_user_ids=[str(uid) for uid in body.scope_user_ids],
        channels=body.channels,
        require_confirmation=body.require_confirmation,
        daily_limit=body.daily_limit,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(capability)
    await db.flush()
    cap_id = capability.id
    await db.commit()

    logger.info(
        "Builder recipe saved: id=%s name=%r tenant=%s by=%s",
        cap_id,
        body.name,
        current_user.tenant_id,
        current_user.id,
    )
    return BuilderSaveResponse(id=cap_id)
