"""Walix AI Bar — API endpoints.

POST /api/ai/command       — interprets a natural-language command and executes actions
GET  /api/ai/context-insight — generates a proactive insight for the current screen
"""

import json
import logging
import re
import time
import uuid
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.command_interpreter import (
    build_interpreter_prompt,
    enrich_context,
    execute_actions,
)
from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.ai_log import AICommandLog
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── Pydantic schemas ───────────────────────────────────────────────────────────


class CommandRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, str]] = Field(default_factory=list)


class ActionResult(BaseModel):
    type: str
    success: bool
    error: str | None = None
    result: dict[str, Any] | None = None


class CommandResult(BaseModel):
    intent_type: str
    response_text: str
    requires_confirmation: bool
    actions_taken: list[ActionResult]
    suggested_actions: list[str]
    data_query: Any | None
    action_data: dict[str, Any] | None = None
    tokens_used: int
    latency_ms: int


class ContextInsightResponse(BaseModel):
    insight: str
    urgency: str  # "low" | "medium" | "high"
    suggested_actions: list[str]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in Claude response: {text[:200]}")
    return json.loads(match.group())


def _build_insight_prompt(screen: str, enriched: dict) -> str:
    ctx_json = json.dumps(enriched, ensure_ascii=False, default=str, indent=2)
    return (
        f"Eres un analista de CRM para PyMEs mexicanas. Analiza el contexto de la pantalla '{screen}' "
        f"y genera una recomendación accionable.\n\n"
        f"DATOS DEL CONTEXTO:\n{ctx_json}\n\n"
        "Responde ÚNICAMENTE con este JSON:\n"
        "{\n"
        '  "insight": "Una recomendación concisa y accionable (máx 2 oraciones)",\n'
        '  "urgency": "low|medium|high",\n'
        '  "suggested_actions": ["acción 1", "acción 2", "acción 3"]\n'
        "}"
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/command", response_model=CommandResult)
async def interpret_command(
    body: CommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommandResult:
    """Interprets a natural-language command from the AI Bar and executes actions."""
    start = time.monotonic()

    # 0. Shortcut: direct confirmation actions bypass Claude entirely
    if body.message == "__confirm__" and body.context.get("confirmation_action"):
        from app.ai.contact_executor import execute_contact_delete
        conf = body.context["confirmation_action"]
        if conf.get("type") == "contact_delete":
            params = {"confirmation_id": conf.get("confirmation_id"), "contact_id": conf.get("contact_id")}
            result = await execute_contact_delete(params, current_user, db)
            return CommandResult(
                intent_type="accion",
                response_text=result.get("message", "Contacto archivado"),
                requires_confirmation=False,
                actions_taken=[ActionResult(type="contact_delete", success=True, result=result)],
                suggested_actions=[],
                data_query=None,
                action_data=result,
                tokens_used=0,
                latency_ms=0,
            )

    # 1. Enrich context with screen-specific data
    enriched = await enrich_context(body.context, current_user, db)

    # 2. Build Claude messages: optional history + current user turn
    system_prompt = build_interpreter_prompt(current_user.role, enriched)
    messages: list[dict] = []
    for h in body.history[-6:]:  # cap history at 6 turns to control tokens
        role = h.get("role", "user")
        if role in ("user", "assistant") and h.get("content"):
            messages.append({"role": role, "content": h["content"]})
    messages.append({"role": "user", "content": body.message})

    # 3. Call Claude Haiku
    try:
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=system_prompt,
            messages=messages,
        )
        raw_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
    except Exception as exc:
        logger.exception("ai/command: Claude call failed for user=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo procesar el comando. Intenta de nuevo.",
        ) from exc

    # 4. Parse interpreter response
    try:
        parsed = _extract_json(raw_text)
    except (ValueError, json.JSONDecodeError):
        logger.error("ai/command: failed to parse Claude JSON: %s", raw_text[:300])
        parsed = {
            "intent_type": "consulta",
            "response_text": raw_text[:300],
            "requires_confirmation": False,
            "actions": [],
            "data_query": None,
            "suggested_actions": [],
        }

    latency_ms = int((time.monotonic() - start) * 1000)
    total_tokens = input_tokens + output_tokens

    # 5. Execute actions unless confirmation is required
    actions_taken: list[ActionResult] = []
    proposed_actions: list[dict] = parsed.get("actions") or []
    if proposed_actions and not parsed.get("requires_confirmation", False):
        raw_results = await execute_actions(proposed_actions, current_user, db, context=body.context)
        actions_taken = [ActionResult(**r) for r in raw_results]

    # Extract rich action_data from first successful contact action
    action_data: dict | None = None
    for ar in actions_taken:
        if ar.success and ar.result and ar.result.get("action"):
            action_data = ar.result
            break

    # 6. Persist to ai_command_logs
    db.add(AICommandLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        message=body.message,
        intent_type=parsed.get("intent_type", "consulta")[:20],
        screen_context=str(body.context.get("screen", ""))[:50],
        actions_taken={
            "proposed": proposed_actions,
            "results": [r.model_dump() for r in actions_taken],
        },
        tokens_used=total_tokens,
        latency_ms=latency_ms,
    ))
    await db.commit()

    return CommandResult(
        intent_type=parsed.get("intent_type", "consulta"),
        response_text=parsed.get("response_text", ""),
        requires_confirmation=bool(parsed.get("requires_confirmation", False)),
        actions_taken=actions_taken,
        suggested_actions=parsed.get("suggested_actions") or [],
        data_query=parsed.get("data_query"),
        action_data=action_data,
        tokens_used=total_tokens,
        latency_ms=latency_ms,
    )


@router.get("/context-insight", response_model=ContextInsightResponse)
async def get_context_insight(
    screen: str = Query(..., description="pipeline|lead|dashboard"),
    branch_id: uuid.UUID | None = Query(default=None),
    lead_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContextInsightResponse:
    """Returns a proactive AI insight for the current screen."""
    context: dict[str, Any] = {"screen": screen}
    if branch_id:
        context["branch_id"] = str(branch_id)
    if lead_id:
        context["lead_id"] = str(lead_id)

    enriched = await enrich_context(context, current_user, db)

    prompt = _build_insight_prompt(screen, enriched)
    try:
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = _extract_json(response.content[0].text)
    except Exception:
        logger.exception(
            "ai/context-insight: failed for user=%s screen=%s", current_user.id, screen
        )
        return ContextInsightResponse(
            insight="No se pudo generar el análisis en este momento.",
            urgency="low",
            suggested_actions=[],
        )

    return ContextInsightResponse(
        insight=str(parsed.get("insight", "")),
        urgency=str(parsed.get("urgency", "low")),
        suggested_actions=list(parsed.get("suggested_actions") or []),
    )
