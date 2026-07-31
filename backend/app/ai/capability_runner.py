"""B3 — Motor de ejecución dinámica de recetas del Walix Builder.

Cuando run_copilot_turn detecta que el mensaje del usuario coincide con la
trigger_phrase de una CopilotCapability activa (kind="recipe"), este módulo
ejecuta los pasos de la receta llamando a execute_tool() — el mismo dispatcher
que usan las 18 tools nativas — antes de entrar al loop normal de Claude.

Decisiones de diseño:
  - Canal: solo "web" está integrado. El webhook de WhatsApp entrante
    (POST /api/webhooks/whatsapp) es un flujo de bot separado que NO pasa por
    run_copilot_turn. Canal "whatsapp" queda fuera de B3 (limitación conocida).
  - Zona horaria para daily_limit: UTC. No existe campo de timezone en el modelo
    Tenant — UTC es el estándar del proyecto para todos los timestamps.
  - Match de trigger_phrases: substring case-insensitive. Sin NLP. Si varias
    capacidades matchean, gana la más recientemente creada (created_at desc).
    Criterio documentado: las recipes deben tener trigger_phrases no solapadas.
  - Pending confirmation: dict en memoria, mismo patrón que _rl_state en
    ai_copilot.py. No persiste entre reinicios ni entre workers. Redis en el futuro.
  - dry_run: el campo existe en copilot_action_log (B1) pero no se expone todavía
    en el flujo de ejecución. Reservado para B4+.
  - Arg inference: solo para write tools. Read tools se invocan con args={} porque
    todos sus args son opcionales en la práctica (ej. year/month defaultean a hoy).

Importación de _WRITE_TOOL_NAMES desde walix_builder:
  Este módulo es importado LAZILY dentro de run_copilot_turn (no en el top-level de
  copilot_engine.py) para evitar la cadena circular:
    copilot_engine → (lazy) capability_runner → walix_builder → copilot_engine
  Cuando esta importación se resuelve en runtime, todos los módulos ya están
  completamente cargados por main.py, por lo que no hay problema de inicialización.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_tools import COPILOT_TOOLS, _serial, execute_tool
from app.models.ai_memory import CopilotActionLog, CopilotCapability
from app.models.tenant import Tenant
from app.models.user import User

# _WRITE_TOOL_NAMES: importado desde walix_builder (B3 prompt: "importarlo desde
# ahí, no duplicarlo"). Safe en runtime: ver nota de importación lazy arriba.
from app.api.walix_builder import _WRITE_TOOL_NAMES

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_ACTIVE_CHANNEL = "web"  # única integración real en B3

_PENDING_TTL_SECS = 300  # 5 min

# Tokens que cuentan como confirmación afirmativa (turno 2 del protocolo).
# El mensaje normalizado (lower/strip) debe EMPEZAR CON uno de estos tokens.
_AFFIRMATIVE_TOKENS: frozenset[str] = frozenset({
    "sí", "si", "confirmo", "confirmar", "adelante", "ok", "dale",
})

# ── Tool index por nombre (lookup O(1)) ────────────────────────────────────────

_TOOL_BY_NAME: dict[str, dict] = {t["name"]: t for t in COPILOT_TOOLS}

# ── Pending confirmation state (in-memory, proceso único) ─────────────────────
# Key: (str(user_id), session_id)
# Value: {capability_id: uuid, original_message: str, expires_at: float (timestamp)}

_pending_lock = asyncio.Lock()
_pending: dict[tuple[str, str], dict[str, Any]] = {}


async def _set_pending(
    user_id: uuid.UUID,
    session_id: str,
    capability_id: uuid.UUID,
    original_message: str,
) -> None:
    key = (str(user_id), session_id)
    async with _pending_lock:
        _pending[key] = {
            "capability_id": capability_id,
            "original_message": original_message,
            "expires_at": datetime.now(timezone.utc).timestamp() + _PENDING_TTL_SECS,
        }


async def _get_pending(
    user_id: uuid.UUID,
    session_id: str,
) -> dict[str, Any] | None:
    key = (str(user_id), session_id)
    async with _pending_lock:
        entry = _pending.get(key)
        if entry is None:
            return None
        if datetime.now(timezone.utc).timestamp() > entry["expires_at"]:
            del _pending[key]
            return None
        return entry


async def _clear_pending(user_id: uuid.UUID, session_id: str) -> None:
    key = (str(user_id), session_id)
    async with _pending_lock:
        _pending.pop(key, None)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _has_write_steps(capability: CopilotCapability) -> bool:
    """True si algún paso de la receta usa una write tool."""
    steps: list[dict] = capability.recipe_json.get("steps", [])
    return any(step.get("tool") in _WRITE_TOOL_NAMES for step in steps)


def _is_affirmative(message: str) -> bool:
    """True si el mensaje es una confirmación simple.

    El mensaje normalizado (lower, strip) debe EMPEZAR CON alguno de los tokens
    en _AFFIRMATIVE_TOKENS. Lista exacta: sí, si, confirmo, confirmar, adelante,
    ok, dale. Heurística deliberadamente estrecha para evitar falsos positivos.
    """
    normalized = message.strip().lower()
    return any(normalized.startswith(tok) for tok in _AFFIRMATIVE_TOKENS)


async def _infer_args_for_step(
    tool_name: str,
    user_message: str,
    previous_outputs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Usa Claude (un solo paso tool-use) para extraer argumentos de un write tool.

    Presenta el schema de la tool y el contexto (mensaje original + outputs previos).
    Si Claude NO puede inferir los argumentos requeridos, no llama la tool y esta
    función devuelve None — la ejecución de la receta se detiene en ese paso.

    Solo se llama para write tools. Read tools se invocan con args={}.

    Import lazy de _anthropic / CLAUDE_MODEL: evitar que este módulo importe
    copilot_engine en el top-level (rompe la cadena circular — ver docstring).
    """
    tool_schema = _TOOL_BY_NAME.get(tool_name)
    if tool_schema is None:
        return None

    # Lazy import: en runtime copilot_engine ya está completamente cargado.
    from app.ai.copilot_engine import CLAUDE_MODEL, _anthropic  # noqa: PLC0415

    context_parts = [f"Mensaje original del usuario: {user_message}"]
    if previous_outputs:
        context_parts.append(
            "Resultados de pasos anteriores:\n"
            + json.dumps(previous_outputs, default=_serial, ensure_ascii=False)
        )
    context = "\n\n".join(context_parts)

    try:
        response = await _anthropic.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=(
                "Eres un extractor de argumentos para un CRM. "
                "Dado el mensaje del usuario y los resultados de pasos previos, "
                "extrae los argumentos necesarios para la herramienta indicada y llámala. "
                "Si no puedes determinar un argumento requerido con la información disponible, "
                "NO llames la herramienta — deja la respuesta sin tool_use."
            ),
            tools=[tool_schema],
            messages=[{"role": "user", "content": context}],
        )
    except Exception:
        logger.exception(
            "capability_runner: arg inference failed for tool '%s'", tool_name
        )
        return None

    if response.stop_reason == "tool_use":
        block = next(
            (b for b in response.content if b.type == "tool_use" and b.name == tool_name),
            None,
        )
        if block:
            return dict(block.input)

    return None  # Claude no pudo inferir los argumentos


async def _log_step(
    db: AsyncSession,
    capability: CopilotCapability,
    user: User,
    step_index: int,
    step_name: str,
    input_data: dict,
    output_data: dict | None,
    step_status: str,
    error_message: str | None = None,
) -> None:
    db.add(
        CopilotActionLog(
            tenant_id=user.tenant_id,
            capability_id=capability.id,
            user_id=user.id,
            step_index=step_index,
            step_name=step_name,
            input=input_data,
            output=output_data,
            status=step_status,
            error_message=error_message,
        )
    )
    await db.flush()


# ── Core functions ─────────────────────────────────────────────────────────────

async def find_matching_capability(
    message: str,
    user: User,
    db: AsyncSession,
) -> CopilotCapability | None:
    """Devuelve la capability más reciente que matchea el mensaje del usuario, o None.

    Criterios (todos deben pasar):
    1. is_active=True, kind="recipe", tenant_id=user.tenant_id
    2. Al menos una trigger_phrase está contenida en el mensaje (case-insensitive)
    3. El scope aplica al usuario actual (all / role match / user match)
    4. "web" está en channels (único canal integrado en B3)

    Tie-breaking: si varias matchean, gana la más recientemente creada (created_at desc).
    """
    rows = (
        await db.execute(
            select(CopilotCapability)
            .where(
                CopilotCapability.tenant_id == user.tenant_id,
                CopilotCapability.is_active.is_(True),
                CopilotCapability.kind == "recipe",
            )
            .order_by(CopilotCapability.created_at.desc())
        )
    ).scalars().all()

    msg_lower = message.lower()

    for cap in rows:
        # Channel
        if _ACTIVE_CHANNEL not in (cap.channels or []):
            continue

        # Trigger phrase (substring, case-insensitive)
        phrases: list[str] = cap.trigger_phrases or []
        if not any(phrase.lower() in msg_lower for phrase in phrases):
            continue

        # Scope
        scope_type: str = cap.scope_type or "all"
        if scope_type == "role":
            if user.role.value not in (cap.scope_roles or []):
                continue
        elif scope_type == "user":
            if str(user.id) not in (cap.scope_user_ids or []):
                continue
        elif scope_type != "all":
            continue  # unknown scope_type → skip

        return cap

    return None


async def check_daily_limit(
    capability: CopilotCapability,
    user: User,
    db: AsyncSession,
) -> bool:
    """True si el usuario aún puede ejecutar esta capacidad hoy.

    Si daily_limit is None, siempre devuelve True (sin límite).
    Cuenta ejecuciones status="ok" de hoy en copilot_action_log.
    Zona horaria: UTC (no existe campo timezone en Tenant — decisión documentada).
    """
    if capability.daily_limit is None:
        return True

    today_utc_start = datetime.combine(
        date.today(), datetime.min.time()
    ).replace(tzinfo=timezone.utc)

    count = (
        await db.execute(
            select(func.count(CopilotActionLog.id)).where(
                CopilotActionLog.capability_id == capability.id,
                CopilotActionLog.user_id == user.id,
                CopilotActionLog.status == "ok",
                CopilotActionLog.created_at >= today_utc_start,
            )
        )
    ).scalar_one()

    return count < capability.daily_limit


async def run_capability_steps(
    capability: CopilotCapability,
    user: User,
    tenant: Tenant,
    db: AsyncSession,
    original_message: str,
) -> dict[str, Any]:
    """Ejecuta todos los pasos de la receta en orden.

    Write tools: llama Claude para inferir argumentos desde original_message +
    outputs de pasos anteriores. Si Claude no puede inferir un arg requerido,
    el paso queda como "error" y se detiene la ejecución (no cascada con estado
    inconsistente).

    Read tools: invocadas con args={} (todos sus args son opcionales en práctica).
    Los outputs anteriores se acumulan para que pasos posteriores puedan referenciarlos
    (importante cuando step 1 devuelve IDs que step 2 necesita — Claude los verá en
    previous_outputs en la llamada de inferencia de argumentos).

    Returns:
        {
            "executed_steps": list[dict],  # uno por paso intentado
            "stopped_at": int | None,       # step_index donde se detuvo (o None si terminó)
            "success": bool,
            "tool_names": list[str],        # nombres de tools que corrieron (ok o error)
        }
    """
    steps: list[dict] = capability.recipe_json.get("steps", [])
    executed: list[dict] = []
    previous_outputs: list[dict[str, Any]] = []
    tool_names: list[str] = []

    for i, step in enumerate(steps):
        tool_name: str = step.get("tool", "")
        note: str = step.get("note") or ""

        if tool_name not in _TOOL_BY_NAME:
            error_msg = f"Tool '{tool_name}' no existe en el catálogo"
            await _log_step(db, capability, user, i, tool_name, {}, None, "error", error_msg)
            executed.append({"step_index": i, "tool": tool_name, "note": note,
                             "status": "error", "error": error_msg})
            await db.commit()
            return {"executed_steps": executed, "stopped_at": i,
                    "success": False, "tool_names": tool_names}

        tool_names.append(tool_name)
        is_write = tool_name in _WRITE_TOOL_NAMES

        # ── Argument resolution ───────────────────────────────────────────────
        if is_write:
            args = await _infer_args_for_step(tool_name, original_message, previous_outputs)
            if args is None:
                error_msg = (
                    f"No se pudieron inferir los argumentos requeridos para '{tool_name}'. "
                    "Proporciona más contexto en tu mensaje (por ejemplo: nombre del contacto, "
                    "ID del deal, etc.) e intenta de nuevo."
                )
                await _log_step(db, capability, user, i, tool_name, {}, None, "error", error_msg)
                executed.append({"step_index": i, "tool": tool_name, "note": note,
                                 "status": "error", "error": error_msg})
                await db.commit()
                return {"executed_steps": executed, "stopped_at": i,
                        "success": False, "tool_names": tool_names}
        else:
            args = {}  # read tools: all args optional, use defaults

        # ── Tool execution ────────────────────────────────────────────────────
        try:
            output = await execute_tool(tool_name, args, user, tenant, db)
        except Exception:
            logger.exception(
                "capability_runner: tool '%s' raised exception (step=%d cap=%s)",
                tool_name, i, capability.id,
            )
            output = {"error": f"Error interno al ejecutar '{tool_name}'"}

        has_error = isinstance(output, dict) and "error" in output
        step_status = "error" if has_error else "ok"

        await _log_step(
            db, capability, user, i, tool_name, args, output, step_status,
            output.get("error") if has_error else None,
        )

        executed.append({
            "step_index": i, "tool": tool_name, "note": note,
            "status": step_status, "output": output,
        })

        if has_error:
            await db.commit()
            return {"executed_steps": executed, "stopped_at": i,
                    "success": False, "tool_names": tool_names}

        previous_outputs.append({"step": i, "tool": tool_name, "output": output})

    await db.commit()
    return {"executed_steps": executed, "stopped_at": None,
            "success": True, "tool_names": tool_names}


# ── Response formatting ────────────────────────────────────────────────────────

def _format_result(capability: CopilotCapability, result: dict[str, Any]) -> str:
    """Formatea el resultado de ejecución como respuesta legible en español."""
    name = capability.name
    steps = result["executed_steps"]
    success = result["success"]
    stopped_at = result.get("stopped_at")

    lines: list[str] = []
    if success:
        lines.append(f"✓ Receta **{name}** ejecutada ({len(steps)} paso/s):\n")
    else:
        lines.append(f"⚠ La receta **{name}** se detuvo en el paso {(stopped_at or 0) + 1}:\n")

    for step in steps:
        icon = "✓" if step["status"] == "ok" else "✗"
        note_str = f" — {step['note']}" if step.get("note") else ""
        lines.append(f"  {icon} Paso {step['step_index'] + 1}: `{step['tool']}`{note_str}")

        if step["status"] == "error":
            # error may be stored in step["error"] (arg inference) or step["output"]["error"] (tool failure)
            error_detail = step.get("error") or (step.get("output") or {}).get("error", "desconocido")
            lines.append(f"     Error: {error_detail}")
        elif step.get("output"):
            out = step["output"]
            summaries = []
            if out.get("created"):
                if "contact_id" in out:
                    summaries.append(f"contacto creado (id: {out.get('contact_id', '?')[:8]}…)")
                elif "deal_id" in out:
                    summaries.append(f"deal creado: '{out.get('title', '?')}'")
                elif "activity_id" in out:
                    summaries.append("nota/tarea registrada")
                else:
                    summaries.append("creado")
            if out.get("set"):
                summaries.append(f"meta guardada: ${out.get('amount_mxn', 0):,.0f} MXN")
            if out.get("moved"):
                summaries.append(f"deal movido a '{out.get('new_stage', '?')}'")
            if out.get("draft_saved"):
                summaries.append("borrador de WhatsApp guardado")
            if out.get("stages"):
                count = out.get("total_active_deals", 0)
                summaries.append(f"{count} deal/s activos encontrados")
            if out.get("tasks"):
                count = out.get("total", 0)
                summaries.append(f"{count} tarea/s pendientes")
            if summaries:
                lines.append(f"     → {', '.join(summaries)}")

    return "\n".join(lines)


def _format_confirmation_request(capability: CopilotCapability) -> str:
    """Formatea el mensaje de confirmación (turno 1 del protocolo)."""
    steps = capability.recipe_json.get("steps", [])
    steps_txt = "\n".join(
        f"  {i + 1}. `{s.get('tool', '?')}`"
        + (f" — {s['note']}" if s.get("note") else "")
        for i, s in enumerate(steps)
    )
    return (
        f"He detectado la receta **{capability.name}** que aplica aquí.\n\n"
        f"Pasos que se ejecutarían:\n{steps_txt}\n\n"
        "¿Confirmas que deseas ejecutar esta receta? Responde 'sí' para continuar."
    )


# ── High-level entry point ─────────────────────────────────────────────────────

async def handle_capability_turn(
    message: str,
    session_id: str,
    user: User,
    tenant: Tenant,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """Punto de entrada principal: gestiona un turno del Copiloto con capability matching.

    Llamado desde run_copilot_turn (lazy import) ANTES del loop normal de Claude.

    Returns:
        {"reply": str, "tool_calls_made": list[str]}  → se encontró y gestionó una capability.
        None                                           → sin match; el caller sigue el flujo normal.
    """
    # ── 1. Verificar estado de confirmación pendiente ─────────────────────────
    pending = await _get_pending(user.id, session_id)
    if pending is not None:
        if _is_affirmative(message):
            cap = await db.get(CopilotCapability, pending["capability_id"])
            await _clear_pending(user.id, session_id)
            if cap and cap.is_active and cap.tenant_id == user.tenant_id:
                result = await run_capability_steps(
                    cap, user, tenant, db, pending["original_message"]
                )
                return {"reply": _format_result(cap, result),
                        "tool_calls_made": result["tool_names"]}
            return {"reply": "La receta ya no está disponible. ¿En qué más puedo ayudarte?",
                    "tool_calls_made": []}
        else:
            # No afirmativo → cancelación; limpiar estado y dejar que el mensaje
            # siga el flujo normal del Copiloto (puede ser otra solicitud distinta).
            await _clear_pending(user.id, session_id)
            return None

    # ── 2. Buscar nueva capability que matchee ────────────────────────────────
    cap = await find_matching_capability(message, user, db)
    if cap is None:
        return None

    # ── 3. Verificar límite diario ────────────────────────────────────────────
    if not await check_daily_limit(cap, user, db):
        return {
            "reply": (
                f"Se alcanzó el límite diario de ejecuciones para la receta "
                f"**{cap.name}** ({cap.daily_limit} ejecución/es por día). "
                "Intenta de nuevo mañana."
            ),
            "tool_calls_made": [],
        }

    # ── 4. Protocolo de confirmación (write tools + require_confirmation=True) ─
    if cap.require_confirmation and _has_write_steps(cap):
        await _set_pending(user.id, session_id, cap.id, message)
        return {"reply": _format_confirmation_request(cap), "tool_calls_made": []}

    # ── 5. Ejecución inmediata (solo lectura, o no requiere confirmación) ──────
    result = await run_capability_steps(cap, user, tenant, db, message)
    return {"reply": _format_result(cap, result), "tool_calls_made": result["tool_names"]}
