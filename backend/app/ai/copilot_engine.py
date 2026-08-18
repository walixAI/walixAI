"""C2/C4 — Copiloto: loop agéntico multi-turno con tool-use nativo de Claude.

SDK: anthropic 0.104.x — usa tools=[...] con input_schema JSON Schema,
stop_reason == "tool_use", content blocks tipo ToolUseBlock, responde con
bloques tool_result en un mensaje role="user".

Este archivo expone dos funciones públicas:
  build_system_prompt(user, tenant, db, entity_type, entity_id) -> str
  run_copilot_turn(message, session_id, user, tenant, db,
                   entity_type, entity_id, max_iterations) -> dict
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid_mod
from datetime import date
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_tools import COPILOT_TOOLS, execute_tool, _serial
from app.core.ai_config import get_model_for_tier
from app.core.config import settings
from app.models.agent import AgentSuggestion
from app.models.ai_memory import AIConversationMessage
from app.models.pipeline import PipelineStage
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.profitability import get_current_month_goal

logger = logging.getLogger(__name__)

# Fallback / valor histórico — sigue exportado porque app/api/walix_builder.py
# lo reusa directo ("reusar cliente y modelo"). El loop de este módulo ya NO
# lo usa: resuelve el modelo real por tier vía get_model_for_tier (Fase 1,
# Parte B) en cada turno, así platform_owner puede cambiarlo sin deploy.
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
_MODEL_TIER = "simple"
_HISTORY_LIMIT = 20   # max turns loaded from DB per session
_MAX_TOKENS = 2048    # higher than single-shot endpoints — tool results take space

_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# ── System prompt ─────────────────────────────────────────────────────────────

_ROLE_LABELS: dict[UserRole, str] = {
    UserRole.OWNER: "Propietario",
    UserRole.GERENTE: "Gerente",
    UserRole.ASESOR: "Asesor de ventas",
    UserRole.DOCTOR: "Doctor",
    UserRole.SOPORTE: "Soporte",
    UserRole.IT: "Administrador de sistemas",
    UserRole.PLATFORM_OWNER: "Administrador de plataforma",
}


async def _resolve_entity_name(
    entity_type: str,
    entity_id: _uuid_mod.UUID,
    tenant_id: _uuid_mod.UUID,
    db: AsyncSession,
) -> str:
    """Returns a human-readable name for the active entity, for system-prompt injection."""
    try:
        if entity_type == "deal":
            from app.models.deal import Deal
            obj = await db.get(Deal, entity_id)
            if obj and obj.tenant_id == tenant_id:
                return obj.title
        elif entity_type in ("contact", "lead"):
            from app.models.lead import Lead
            obj = await db.get(Lead, entity_id)
            if obj and obj.tenant_id == tenant_id and not obj.deleted_at:
                return " ".join(filter(None, [obj.name, obj.last_name])) or "Sin nombre"
    except Exception:
        logger.debug("_resolve_entity_name: lookup failed for %s %s", entity_type, entity_id)
    return str(entity_id)


async def build_system_prompt(
    user: User,
    tenant: Tenant,
    db: AsyncSession,
    entity_type: str | None = None,
    entity_id: _uuid_mod.UUID | None = None,
) -> str:
    today = date.today()
    year, month = today.year, today.month

    # Active pipeline stage names (non-terminal, non-archived)
    stage_rows = (
        await db.execute(
            select(PipelineStage.name)
            .where(
                PipelineStage.tenant_id == tenant.id,
                PipelineStage.is_archived.is_(False),
                PipelineStage.is_won.is_(False),
                PipelineStage.is_lost.is_(False),
            )
            .order_by(PipelineStage.order_index)
            .limit(12)
        )
    ).scalars().all()
    stage_list = (
        "\n".join(f"  - {s}" for s in stage_rows) or "  (sin etapas configuradas)"
    )

    # Current month global goal
    goal = await get_current_month_goal(tenant.id, year, month, db)
    goal_line = (
        f"Meta mensual global: ${float(goal.amount):,.0f} MXN"
        if goal
        else "Sin meta mensual configurada para este mes."
    )

    # Top 3 pending suggestions
    sugg_rows = (
        await db.execute(
            select(AgentSuggestion.suggestion_text)
            .where(
                AgentSuggestion.tenant_id == tenant.id,
                AgentSuggestion.status == "suggested",
                AgentSuggestion.expires_at > func.now(),
            )
            .order_by(AgentSuggestion.created_at.desc())
            .limit(3)
        )
    ).scalars().all()
    sugg_block = (
        "\n".join(f"  - {s}" for s in sugg_rows)
        if sugg_rows
        else "  (sin sugerencias proactivas activas)"
    )

    role_label = _ROLE_LABELS.get(user.role, str(user.role))

    # Active-screen context (C4: entity_type/entity_id from HTTP request)
    entity_block = ""
    if entity_type and entity_id:
        entity_name = await _resolve_entity_name(entity_type, entity_id, tenant.id, db)
        entity_block = (
            f"\nCONTEXTO DE PANTALLA ACTIVA:\n"
            f"  Tipo: {entity_type}\n"
            f"  ID: {entity_id}\n"
            f"  Nombre: {entity_name}\n"
            f"  → Cuando el usuario mencione 'este {entity_type}' o el {entity_type} actual, "
            f"referirse a este registro específico.\n"
        )

    return (
        "Eres Walix Copiloto, el asistente de inteligencia artificial del CRM Walix "
        "para PyMEs mexicanas. Tu función es ayudar al equipo de ventas a consultar "
        "información, entender su rendimiento y tomar mejores decisiones de negocio.\n\n"
        f"CONTEXTO DEL TENANT:\n"
        f"  Empresa: {tenant.name}\n"
        f"  Industria: {tenant.industry or 'No especificada'}\n"
        f"  Plan: {tenant.plan.value}\n"
        f"  Hoy: {today.strftime('%d/%m/%Y')}\n\n"
        f"USUARIO ACTUAL:\n"
        f"  Nombre: {user.name}\n"
        f"  Rol: {role_label}\n\n"
        f"ETAPAS DEL PIPELINE ACTIVO:\n{stage_list}\n\n"
        f"FINANZAS DEL MES ACTUAL:\n  {goal_line}\n\n"
        f"SUGERENCIAS PROACTIVAS PENDIENTES:\n{sugg_block}\n"
        f"{entity_block}\n"
        "INSTRUCCIONES DE COMPORTAMIENTO — LECTURA:\n"
        "- Responde SIEMPRE en español, con tono profesional y directo.\n"
        "- Usa las tools disponibles para obtener datos antes de responder. "
        "No inventes ni estimes cifras: si no tienes datos, dilo.\n"
        "- Cuando el usuario pregunte por el pipeline o deals activos → get_pipeline_status.\n"
        "- Cuando pregunte por un cliente o contacto específico → search_contacts, "
        "luego get_contact_context para profundidad.\n"
        "- Cuando pregunte por sus tareas pendientes → get_my_tasks.\n"
        "- Cuando pregunte por rentabilidad, margen o utilidad → get_profitability.\n"
        "- Cuando pregunte por run rate, proyección o avance del mes → get_run_rate.\n"
        "- Cuando pregunte por gastos → get_expenses_summary.\n"
        "- Cuando pregunte por la meta mensual → get_monthly_goal.\n"
        "- Cuando pregunte por el equipo o rendimiento individual (solo propietario) "
        "→ get_team_performance.\n"
        "- Cuando pregunte por recomendaciones del sistema → get_my_suggestions.\n"
        "- Cuando pregunte por sus oportunidades → get_my_deals.\n"
        "- Formatea cantidades monetarias en MXN con $ y comas (ej. $12,500).\n"
        "- Sé conciso. No menciones nombres técnicos de herramientas al usuario.\n"
        "- Si el usuario no tiene acceso a cierta información, explícalo brevemente "
        "sin revelar detalles técnicos.\n\n"
        "INSTRUCCIONES DE COMPORTAMIENTO — ESCRITURA:\n"
        "- Solo ejecuta acciones de escritura cuando el usuario lo haya pedido "
        "de forma explícita. No actúes proactivamente.\n"
        "- create_contact: cuando el usuario pida agregar o registrar un nuevo contacto o cliente.\n"
        "- create_deal: cuando el usuario pida abrir o crear una oportunidad o deal "
        "para un contacto existente. Si no sabes el lead_id, usa search_contacts primero.\n"
        "- move_deal_stage: cuando el usuario pida mover, avanzar o cambiar la etapa de un deal. "
        "Si no sabes el deal_id o stage_id, usa get_my_deals / get_pipeline_status primero.\n"
        "- add_note: cuando el usuario quiera registrar observaciones o comentarios "
        "sobre un contacto o deal.\n"
        "- create_task: cuando el usuario quiera programar un seguimiento, cotización, "
        "cobro u otra actividad pendiente.\n"
        "- prepare_whatsapp_message: cuando el usuario pida redactar o preparar un mensaje "
        "de WhatsApp. IMPORTANTE: esta tool NUNCA envía el mensaje; solo guarda el borrador. "
        "Después de llamarla, muestra el borrador al usuario y recuérdale que debe enviarlo manualmente.\n"
        "- set_monthly_goal — PROTOCOLO OBLIGATORIO DE CONFIRMACIÓN:\n"
        "  1. Cuando el usuario pida cambiar la meta, NO llames set_monthly_goal todavía.\n"
        "  2. Primero explica qué vas a hacer y pregunta: '¿Confirmas que quieres "
        "establecer la meta mensual en $XX,XXX MXN para MM/AAAA?'\n"
        "  3. SOLO cuando el usuario responda afirmativamente, llama set_monthly_goal "
        "con confirmed=true.\n"
        "  4. NUNCA llames esta herramienta con confirmed=false — ese valor solo existe "
        "como salvaguarda interna."
    )

# ── History loading & serialization ──────────────────────────────────────────

async def _load_history(
    session_id: str,
    user: User,
    db: AsyncSession,
    limit: int = _HISTORY_LIMIT,
) -> list[AIConversationMessage]:
    # Filter by user_id (not just tenant_id) — history is private per user.
    # Two users from the same tenant with session_id="global" must not see each other's turns.
    rows = (
        await db.execute(
            select(AIConversationMessage)
            .where(
                AIConversationMessage.session_id == session_id,
                AIConversationMessage.tenant_id == user.tenant_id,
                AIConversationMessage.user_id == user.id,
            )
            .order_by(AIConversationMessage.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


def _rows_to_api_messages(rows: list[AIConversationMessage]) -> list[dict[str, Any]]:
    """Reconstruct Anthropic API messages from stored history rows.

    row.role="user"      → {"role": "user", "content": text}
    row.role="assistant" → {"role": "assistant", "content": text or content blocks}
    row.role="tool"      → {"role": "user", "content": [tool_result blocks]}
    """
    messages: list[dict[str, Any]] = []
    for row in rows:
        if row.role == "user":
            messages.append({"role": "user", "content": row.content})

        elif row.role == "assistant":
            if row.tool_calls:
                content: list[dict] = []
                if row.content:
                    content.append({"type": "text", "text": row.content})
                for tc in row.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["input"],
                        }
                    )
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "assistant", "content": row.content})

        elif row.role == "tool":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tc["tool_use_id"],
                            "content": json.dumps(tc["result"], default=_serial),
                        }
                        for tc in row.tool_calls
                    ],
                }
            )
    return messages


def _content_blocks_to_dicts(blocks: list[Any]) -> list[dict[str, Any]]:
    """Convert SDK ContentBlock objects to plain dicts for next API call."""
    result = []
    for b in blocks:
        if b.type == "text":
            result.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            result.append(
                {
                    "type": "tool_use",
                    "id": b.id,
                    "name": b.name,
                    "input": dict(b.input),
                }
            )
    return result


async def _save_row(
    db: AsyncSession,
    user: User,
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
) -> None:
    db.add(
        AIConversationMessage(
            tenant_id=user.tenant_id,
            user_id=user.id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            context_snapshot={},
        )
    )
    await db.flush()  # ensure row is written but don't commit yet


# ── Main copilot loop ─────────────────────────────────────────────────────────

async def run_copilot_turn(
    message: str,
    session_id: str,
    user: User,
    tenant: Tenant,
    db: AsyncSession,
    entity_type: str | None = None,
    entity_id: _uuid_mod.UUID | None = None,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Execute one user turn of the Copiloto conversation.

    Loads history, calls Claude with tool-use, executes each tool, and
    iterates until stop_reason != "tool_use" or max_iterations is reached.

    Returns:
        {"reply": str, "tool_calls_made": list[str]}
    """
    # 1. Load existing history BEFORE saving the new user message
    history_rows = await _load_history(session_id, user, db)

    # 2. Save the incoming user message
    await _save_row(db, user, session_id, "user", message)

    # B3: Capability fast path — check BEFORE the normal tool-use loop.
    # Lazy import breaks the circular chain: copilot_engine → capability_runner
    # → walix_builder → copilot_engine. By the time this line runs, all modules
    # are fully initialized (FastAPI startup completes before any request arrives).
    from app.ai.capability_runner import handle_capability_turn  # noqa: PLC0415
    cap_result = await handle_capability_turn(message, session_id, user, tenant, db)
    if cap_result is not None:
        await _save_row(db, user, session_id, "assistant", cap_result["reply"])
        await db.commit()
        return cap_result

    # 3. Build system prompt (includes entity context if provided)
    system = await build_system_prompt(user, tenant, db, entity_type, entity_id)

    # 4. Build API message list: history + current user turn
    api_messages = _rows_to_api_messages(history_rows)
    api_messages.append({"role": "user", "content": message})

    tool_calls_made: list[str] = []
    iteration = 0
    model_name = await get_model_for_tier(_MODEL_TIER, db)

    while iteration < max_iterations:
        # ── Call Claude ───────────────────────────────────────────────────────
        try:
            response = await _anthropic.messages.create(
                model=model_name,
                max_tokens=_MAX_TOKENS,
                system=system,
                tools=COPILOT_TOOLS,
                messages=api_messages,
            )
        except Exception:
            logger.exception(
                "copilot_engine: Claude call failed (session=%s user=%s iteration=%d)",
                session_id,
                user.id,
                iteration,
            )
            fallback = (
                "No pude conectarme con el asistente en este momento. "
                "Por favor intenta de nuevo en unos segundos."
            )
            await _save_row(db, user, session_id, "assistant", fallback)
            await db.commit()
            return {"reply": fallback, "tool_calls_made": tool_calls_made}

        # ── Final text response ───────────────────────────────────────────────
        if response.stop_reason != "tool_use":
            final_text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            await _save_row(db, user, session_id, "assistant", final_text)
            await db.commit()
            return {"reply": final_text, "tool_calls_made": tool_calls_made}

        # ── Tool use response — execute each requested tool ───────────────────
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        text_content = next(
            (b.text for b in response.content if b.type == "text"), ""
        )

        # Save assistant turn (with tool call references)
        await _save_row(
            db,
            user,
            session_id,
            "assistant",
            text_content,
            tool_calls=[
                {"id": b.id, "name": b.name, "input": dict(b.input)}
                for b in tool_use_blocks
            ],
        )

        # Execute each tool and collect results
        tool_result_api_blocks: list[dict[str, Any]] = []
        tool_result_records: list[dict[str, Any]] = []

        for block in tool_use_blocks:
            tool_calls_made.append(block.name)
            try:
                result = await execute_tool(
                    block.name, dict(block.input), user, tenant, db
                )
            except Exception:
                logger.exception(
                    "copilot_engine: tool '%s' raised an exception (session=%s)",
                    block.name,
                    session_id,
                )
                result = {
                    "error": f"La herramienta '{block.name}' encontró un error interno."
                }

            result_json = json.dumps(result, default=_serial)
            tool_result_api_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_json,
                }
            )
            tool_result_records.append(
                {
                    "tool_use_id": block.id,
                    "name": block.name,
                    "result": result,
                }
            )

        # Save tool result row (role="tool")
        await _save_row(
            db, user, session_id, "tool", "", tool_calls=tool_result_records
        )

        # Extend messages for next iteration
        api_messages.append(
            {
                "role": "assistant",
                "content": _content_blocks_to_dicts(response.content),
            }
        )
        api_messages.append(
            {"role": "user", "content": tool_result_api_blocks}
        )

        iteration += 1

    # ── Guardrail: max iterations reached without a final answer ──────────────
    logger.warning(
        "copilot_engine: max_iterations=%d reached (session=%s user=%s tools=%s)",
        max_iterations,
        session_id,
        user.id,
        tool_calls_made,
    )
    fallback = (
        "No pude completar la consulta en este momento. "
        "Por favor reformula tu pregunta o intenta de nuevo."
    )
    await _save_row(db, user, session_id, "assistant", fallback)
    await db.commit()
    return {"reply": fallback, "tool_calls_made": tool_calls_made}
