"""Walix AI Bar — command interpreter.

Responsible for three things:
  1. enrich_context()  — loads screen-specific data before calling Claude
  2. build_interpreter_prompt() — builds the system prompt with role + context
  3. execute_actions() — runs validated actions returned by the interpreter
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityType, LeadActivity
from app.models.ai_log import AICommandLog
from app.models.alert import AlertRule
from app.models.conversation import Message
from app.models.lead import Lead, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# ── Permission matrix ──────────────────────────────────────────────────────────

# All roles can perform contact CRUD via the AIBar
_CONTACT_CRUD = {
    "contact_create", "contact_read", "contact_update",
    "contact_activity", "contact_delete",
}

_ROLE_ACTIONS: dict[UserRole, set[str]] = {
    UserRole.OWNER:   {"move_lead_stage", "assign_lead", "update_ai_config", "create_alert_rule", "navigate"} | _CONTACT_CRUD,
    UserRole.GERENTE: {"move_lead_stage", "assign_lead", "update_ai_config", "create_alert_rule", "navigate"} | _CONTACT_CRUD,
    UserRole.ASESOR:  {"move_lead_stage", "assign_lead", "navigate"} | _CONTACT_CRUD,
    UserRole.DOCTOR:  {"move_lead_stage", "assign_lead", "navigate"} | _CONTACT_CRUD,
    UserRole.SOPORTE: {"navigate"} | _CONTACT_CRUD,
    UserRole.IT:      {"navigate", "update_ai_config"} | _CONTACT_CRUD,
}


def _allowed_actions(role: UserRole) -> set[str]:
    return _ROLE_ACTIONS.get(role, {"navigate"})


def _resolve_branch_id(context: dict, user: User) -> uuid.UUID | None:
    raw = context.get("branch_id")
    if raw:
        try:
            return uuid.UUID(str(raw))
        except ValueError:
            pass
    return user.branch_id


# ── 1. Context enrichment ──────────────────────────────────────────────────────

async def enrich_context(context: dict, user: User, db: AsyncSession) -> dict:
    """Adds screen-specific data to context before passing it to Claude."""
    enriched = dict(context)
    screen = context.get("screen", "")
    branch_id = _resolve_branch_id(context, user)

    if screen == "pipeline" and branch_id:
        enriched.update(await _enrich_pipeline(branch_id, user.tenant_id, db))

    elif screen == "lead":
        raw_lead_id = context.get("lead_id")
        if raw_lead_id:
            try:
                lead_id = uuid.UUID(str(raw_lead_id))
                enriched.update(await _enrich_lead(lead_id, db))
            except ValueError:
                pass

    elif screen == "dashboard":
        enriched.update(await _enrich_dashboard(user.tenant_id, branch_id, db))

    return enriched


async def _enrich_pipeline(
    branch_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> dict:
    stages_result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.branch_id == branch_id, PipelineStage.is_active.is_(True))
        .order_by(PipelineStage.order_index)
    )
    stages = stages_result.scalars().all()

    # Count leads per stage
    counts_result = await db.execute(
        select(Lead.pipeline_stage_id, func.count(Lead.id))
        .where(Lead.branch_id == branch_id)
        .group_by(Lead.pipeline_stage_id)
    )
    counts = {str(row[0]): row[1] for row in counts_result.fetchall()}

    # High-risk leads
    risk_result = await db.execute(
        select(Lead.id, Lead.name, Lead.risk_score, Lead.pipeline_stage_id)
        .where(Lead.branch_id == branch_id, Lead.risk_score > 0.7)
        .order_by(Lead.risk_score.desc())
        .limit(5)
    )
    high_risk = [
        {"id": str(r.id), "name": r.name, "risk_score": r.risk_score, "stage_id": str(r.pipeline_stage_id)}
        for r in risk_result.fetchall()
    ]

    return {
        "pipeline_stages": [
            {
                "id": str(s.id),
                "name": s.name,
                "slug": s.slug,
                "lead_count": counts.get(str(s.id), 0),
                "is_won": s.is_won,
                "is_lost": s.is_lost,
            }
            for s in stages
        ],
        "high_risk_leads": high_risk,
    }


async def _enrich_lead(lead_id: uuid.UUID, db: AsyncSession) -> dict:
    from app.models.conversation import Conversation

    lead = await db.get(Lead, lead_id)
    if lead is None:
        return {}

    conv_result = await db.execute(
        select(Conversation.id)
        .where(Conversation.lead_id == lead_id)
        .order_by(Conversation.started_at.desc())
        .limit(1)
    )
    conv_row = conv_result.scalar_one_or_none()

    recent_messages: list[dict] = []
    if conv_row:
        msgs_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv_row)
            .order_by(Message.created_at.desc())
            .limit(3)
        )
        recent_messages = [
            {"role": getattr(m.role, "value", m.role), "content": m.content}
            for m in reversed(msgs_result.scalars().all())
        ]

    return {
        "lead": {
            "id": str(lead.id),
            "name": lead.name,
            "status": lead.status if isinstance(lead.status, str) else lead.status.value,
            "sentiment": lead.sentiment if isinstance(lead.sentiment, str) else lead.sentiment.value,
            "qualification_score": lead.qualification_score,
            "qualification_data": lead.qualification_data or {},
            "risk_score": lead.risk_score,
            "risk_reason": lead.risk_reason,
        },
        "recent_messages": recent_messages,
    }


async def _enrich_dashboard(
    tenant_id: uuid.UUID, branch_id: uuid.UUID | None, db: AsyncSession
) -> dict:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    base_filter = [Lead.tenant_id == tenant_id]
    if branch_id:
        base_filter.append(Lead.branch_id == branch_id)

    leads_today_result = await db.execute(
        select(func.count(Lead.id)).where(*base_filter, Lead.created_at >= today_start)
    )
    leads_today = leads_today_result.scalar() or 0

    calificados_result = await db.execute(
        select(func.count(Lead.id)).where(
            *base_filter,
            Lead.created_at >= today_start,
            Lead.status == LeadStatus.CALIFICADO,
        )
    )
    calificados = calificados_result.scalar() or 0

    latency_result = await db.execute(
        select(func.avg(Message.latency_ms)).where(
            Message.latency_ms.isnot(None),
            Message.created_at >= today_start,
        )
    )
    avg_latency_ms = latency_result.scalar()
    avg_response_s = round(avg_latency_ms / 1000, 1) if avg_latency_ms else None

    high_risk_result = await db.execute(
        select(func.count(Lead.id)).where(*base_filter, Lead.risk_score > 0.7)
    )
    high_risk_count = high_risk_result.scalar() or 0

    return {
        "stats": {
            "leads_today": leads_today,
            "calificados_today": calificados,
            "avg_response_s": avg_response_s,
            "high_risk_count": high_risk_count,
        }
    }


# ── 2. System prompt ───────────────────────────────────────────────────────────

_INTENT_SCHEMA = """{
  "intent_type": "accion|consulta|analisis|config|alerta",
  "response_text": "Respuesta concisa (máx 2 oraciones)",
  "requires_confirmation": false,
  "actions": [
    {"type": "move_lead_stage", "lead_id": "uuid", "stage_id": "uuid"},
    {"type": "assign_lead", "lead_id": "uuid", "user_id": "uuid"},
    {"type": "update_ai_config", "branch_id": "uuid", "patch": {}},
    {"type": "create_alert_rule", "branch_id": "uuid", "alert_type": "str", "threshold_hours": 48},
    {"type": "navigate", "destination": "pipeline|lead|dashboard|settings"},
    {"type": "contact_create", "params": {"name": "str", "last_name": "str|null", "phone": "str|null", "email": "str|null", "company": "str|null", "prospection_source": "manual|whatsapp|form|referral"}},
    {"type": "contact_read", "params": {"q": "str|null", "status": ["nuevo","calificado","..."], "company": "str|null", "date_range": "today|this_week|this_month|null", "sort_by": "score|name|lastActivity|null"}},
    {"type": "contact_update", "params": {"contact_ref": "nombre o teléfono del contacto", "field": "status|company|assigned_to|tag|...", "new_value": "valor nuevo"}},
    {"type": "contact_activity", "params": {"contact_ref": "nombre o teléfono (vacío si hay contacto en pantalla)", "activity_type": "note|call|meeting|task|email", "title": "str|null", "body": "descripción", "due_date": "ISO fecha|null"}},
    {"type": "contact_delete", "params": {"contact_ref": "nombre o teléfono", "bulk": false}}
  ],
  "data_query": null,
  "suggested_actions": ["Acción sugerida 1", "Acción sugerida 2"]
}"""

_CONTACT_INTENT_GUIDE = """
INTENTS DE CONTACTOS (disponibles para todos los roles):

contact_create — cuando el usuario quiere agregar/crear/añadir un contacto.
  Extraer: name (obligatorio), last_name, phone (normalizar 10 dígitos → +52...), company, prospection_source.
  Ejemplos: "agrega a María López, tel 81 1234 5678", "nuevo contacto: Juan García de ACME"

contact_read — cuando busca, filtra o quiere ver contactos.
  Extraer: q (búsqueda libre), status, company, date_range (today/this_week/this_month), sort_by.
  Ejemplos: "busca a Carlos", "muéstrame los calificados de este mes", "cuántos leads hay"

contact_update — cuando quiere cambiar un campo de un contacto.
  Extraer: contact_ref (nombre/tel para identificar), field (status/company/assigned_to...), new_value.
  Si el usuario está en la ficha de un contacto (screen empieza con "contacts/"), contact_ref puede estar vacío.
  Ejemplos: "cambia el estatus de Ana García a calificado", "asigna a Juan al vendedor Carlos"

contact_activity — cuando registra nota, llamada, tarea, reunión o email sobre un contacto.
  Extraer: contact_ref, activity_type (note/call/meeting/task/email), title, body, due_date.
  Si screen empieza con "contacts/", el contact_ref puede omitirse (aplica al contacto en pantalla).
  Ejemplos: "anota llamada con Pedro: interesado en plan premium", "agenda reunión con Sofía el 15 jun"

contact_delete — cuando quiere archivar o eliminar un contacto. SIEMPRE pedir confirmación.
  Extraer: contact_ref (nombre/teléfono).
  IMPORTANTE: requiere confirmation_required: true. Nunca decir "eliminar" — decir "archivar".
  Ejemplos: "archiva a Juan García", "elimina el contacto de ACME"
"""

_ROLE_DESCRIPTIONS: dict[UserRole, str] = {
    UserRole.OWNER:   "Owner — acceso total al sistema",
    UserRole.GERENTE: "Gerente — gestión de equipo y leads, puede configurar el bot",
    UserRole.ASESOR:  "Asesor — puede mover leads entre etapas y asignar, no puede cambiar config",
    UserRole.DOCTOR:  "Doctor — igual que asesor, vista de sus pacientes/leads",
    UserRole.SOPORTE: "Soporte Walix — solo lectura y navegación",
    UserRole.IT:      "IT — puede navegar y actualizar configuración técnica",
}


def build_interpreter_prompt(role: UserRole, context: dict) -> str:
    allowed = sorted(_allowed_actions(role))
    role_desc = _ROLE_DESCRIPTIONS.get(role, str(role))
    context_json = json.dumps(context, ensure_ascii=False, default=str, indent=2)

    return (
        "Eres el intérprete de comandos de Walix, un CRM de WhatsApp para PyMEs mexicanas.\n"
        "Analiza el mensaje del usuario, determina su intención y devuelve las acciones a ejecutar.\n\n"
        f"ROL: {role_desc}\n"
        f"ACCIONES PERMITIDAS: {', '.join(allowed)}\n\n"
        f"CONTEXTO DE PANTALLA:\n{context_json}\n\n"
        + _CONTACT_INTENT_GUIDE + "\n"
        "REGLAS GENERALES:\n"
        "- Solo propón acciones que estén en ACCIONES PERMITIDAS.\n"
        "- requires_confirmation: true si la acción modifica datos de forma irreversible (incluyendo contact_delete siempre).\n"
        "- response_text: máximo 2 oraciones, en español, directo al punto.\n"
        "- Si el usuario solo pregunta, deja actions vacío.\n"
        "- suggested_actions: 2-3 acciones contextuales relevantes para el estado actual.\n"
        "- Para contact_activity y contact_update: si context.screen empieza con 'contacts/' y contact_ref está vacío, usa el contacto en pantalla.\n\n"
        "Responde ÚNICAMENTE con este JSON (sin markdown, sin texto adicional):\n"
        + _INTENT_SCHEMA
    )


# ── 3. Action executor ─────────────────────────────────────────────────────────

async def execute_actions(
    actions: list[dict],
    user: User,
    db: AsyncSession,
    context: dict | None = None,
) -> list[dict]:
    """Executes each action after permission check. Returns a result list."""
    allowed = _allowed_actions(user.role)
    results: list[dict] = []

    for action in actions:
        action_type = action.get("type", "")
        if action_type not in allowed:
            results.append({
                "type": action_type,
                "success": False,
                "error": f"Rol '{user.role}' no tiene permiso para '{action_type}'",
            })
            continue

        try:
            result = await _dispatch_action(action_type, action, user, db, context)
            results.append({"type": action_type, "success": True, "result": result})
        except Exception as exc:
            logger.exception("execute_actions: failed action=%s", action_type)
            results.append({"type": action_type, "success": False, "error": str(exc)})

    return results


async def _dispatch_action(
    action_type: str, action: dict, user: User, db: AsyncSession,
    context: dict | None = None,
) -> dict:
    if action_type == "move_lead_stage":
        return await _action_move_lead_stage(action, user, db)
    if action_type == "assign_lead":
        return await _action_assign_lead(action, user, db)
    if action_type == "update_ai_config":
        return await _action_update_ai_config(action, user, db)
    if action_type == "create_alert_rule":
        return await _action_create_alert_rule(action, user, db)
    if action_type == "navigate":
        return {"destination": action.get("destination")}

    # Contact CRUD
    if action_type.startswith("contact_"):
        return await _dispatch_contact_action(action_type, action, user, db, context or {})

    raise ValueError(f"Unsupported action type: {action_type}")


async def _dispatch_contact_action(
    action_type: str, action: dict, user: User, db: AsyncSession, context: dict
) -> dict:
    from app.ai.contact_executor import (
        execute_contact_activity,
        execute_contact_create,
        execute_contact_delete,
        execute_contact_read,
        execute_contact_update,
    )

    params: dict = action.get("params", {})
    ctx_contact_id = str(context.get("contact_id", "")) or None

    if action_type == "contact_create":
        return await execute_contact_create(params, user, db)
    if action_type == "contact_read":
        return await execute_contact_read(params, user, db)
    if action_type == "contact_update":
        return await execute_contact_update(params, user, db, context_contact_id=ctx_contact_id)
    if action_type == "contact_activity":
        return await execute_contact_activity(params, user, db, ctx_contact_id)
    if action_type == "contact_delete":
        return await execute_contact_delete(params, user, db)

    raise ValueError(f"Unsupported contact action: {action_type}")


async def _action_move_lead_stage(action: dict, user: User, db: AsyncSession) -> dict:
    lead_id = uuid.UUID(str(action["lead_id"]))
    stage_id = uuid.UUID(str(action["stage_id"]))

    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise ValueError(f"Lead {lead_id} not found")
    if lead.tenant_id != user.tenant_id:
        raise PermissionError("Lead belongs to a different tenant")

    stage = await db.get(PipelineStage, stage_id)
    if stage is None or stage.tenant_id != user.tenant_id:
        raise ValueError(f"Stage {stage_id} not found")

    old_stage_id = lead.pipeline_stage_id
    lead.pipeline_stage_id = stage_id

    db.add(LeadActivity(
        lead_id=lead_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        activity_type=ActivityType.STATUS_CHANGE,
        payload={"from_stage": str(old_stage_id), "to_stage": str(stage_id), "via": "ai_bar"},
    ))
    await db.commit()
    return {"lead_id": str(lead_id), "new_stage": stage.name}


async def _action_assign_lead(action: dict, user: User, db: AsyncSession) -> dict:
    lead_id = uuid.UUID(str(action["lead_id"]))
    assignee_id = uuid.UUID(str(action["user_id"]))

    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise ValueError(f"Lead {lead_id} not found")
    if lead.tenant_id != user.tenant_id:
        raise PermissionError("Lead belongs to a different tenant")

    assignee = await db.get(User, assignee_id)
    if assignee is None or assignee.tenant_id != user.tenant_id:
        raise ValueError(f"User {assignee_id} not found in tenant")

    lead.assigned_to = assignee_id
    db.add(LeadActivity(
        lead_id=lead_id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        activity_type=ActivityType.ASSIGN,
        payload={"assigned_to": str(assignee_id), "assignee_name": assignee.name, "via": "ai_bar"},
    ))
    await db.commit()
    return {"lead_id": str(lead_id), "assigned_to": assignee.name}


async def _action_update_ai_config(action: dict, user: User, db: AsyncSession) -> dict:
    branch_id = uuid.UUID(str(action["branch_id"]))
    patch: dict = action.get("patch", {})

    branch = await db.get(Branch, branch_id)
    if branch is None or branch.tenant_id != user.tenant_id:
        raise ValueError(f"Branch {branch_id} not found")

    current = dict(branch.ai_config or {})
    _deep_merge(current, patch)
    branch.ai_config = current
    await db.commit()
    return {"branch_id": str(branch_id), "patched_keys": list(patch.keys())}


async def _action_create_alert_rule(action: dict, user: User, db: AsyncSession) -> dict:
    branch_id = uuid.UUID(str(action["branch_id"]))
    branch = await db.get(Branch, branch_id)
    if branch is None or branch.tenant_id != user.tenant_id:
        raise ValueError(f"Branch {branch_id} not found")

    rule = AlertRule(
        branch_id=branch_id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        alert_type=str(action.get("alert_type", "inactivity")),
        threshold_hours=int(action.get("threshold_hours", 48)),
        schedule_hour=int(action.get("schedule_hour", 9)),
        silence_start=int(action.get("silence_start", 21)),
        silence_end=int(action.get("silence_end", 8)),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {"rule_id": str(rule.id), "alert_type": rule.alert_type}


def _deep_merge(base: dict, patch: dict) -> None:
    """Merges patch into base in-place (one level deep for nested dicts)."""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key].update(value)
        else:
            base[key] = value
