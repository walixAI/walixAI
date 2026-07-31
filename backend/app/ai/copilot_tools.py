"""C2/C3 — Copiloto: definición y dispatcher de tools (lectura + escritura).

C2: 11 tools de lectura (sin side-effects).
C3: 7 tools de escritura ejecutables por el modelo.

Política de confirmación:
  create_contact, create_deal, move_deal_stage, add_note, create_task
    → ejecutan de inmediato cuando el modelo las llama.
  prepare_whatsapp_message
    → guarda borrador en AIDraftEdit (Etapa 7.2); NUNCA envía nada.
  set_monthly_goal
    → requiere confirmed=True en el input; si confirmed=False devuelve
      mensaje de confirmación para que Claude lo presente al usuario.

Tool-use format: nativo Anthropic SDK 0.104.x
  name, description, input_schema (JSON Schema)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.agent import AgentSuggestion
from app.models.ai_memory import AIDraftEdit, AIEntityContext, AIMemoryEvent
from app.models.deal import Deal
from app.models.deal_stage_history import DealStageHistory
from app.models.finance import Expense
from app.models.goals import MonthlyGoal, MonthlyGoalHistory
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.profitability import (
    get_current_month_goal,
    get_tenant_profitability,
    get_tenant_run_rate,
    get_user_profitability,
    get_user_run_rate,
)

logger = logging.getLogger(__name__)

# ── Role guard ────────────────────────────────────────────────────────────────

_OWNER_ROLES = (UserRole.OWNER, UserRole.PLATFORM_OWNER)

_VALID_TASK_KINDS = (
    "cobro", "cotizacion", "servicio", "seguimiento",
    "queja", "refaccion", "facturacion", "devolucion", "otro",
)

# ── Tool catalog (Anthropic native format) ────────────────────────────────────

COPILOT_TOOLS: list[dict[str, Any]] = [
    # ── READ TOOLS ─────────────────────────────────────────────────────────────
    {
        "name": "get_pipeline_status",
        "description": (
            "Returns the current sales pipeline: number of active deals and total MXN value "
            "per stage, ordered from first to last stage. Use this when the user asks about "
            "their pipeline, how many deals they have, or what's in each stage."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_contacts",
        "description": (
            "Searches contacts (leads) by name or WhatsApp phone number. "
            "Returns basic info: id, name, phone, status, assigned agent. "
            "Use when the user asks about a specific client or contact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name fragment or phone number to search"},
                "limit": {"type": "integer", "description": "Max results (default 10, max 20)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_contact_context",
        "description": (
            "Returns AI memory context for a specific contact: summary, key facts, sentiment, "
            "urgency score, and recent events. Requires contact_id (UUID from search_contacts)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "UUID of the contact (lead)"},
            },
            "required": ["contact_id"],
        },
    },
    {
        "name": "get_my_tasks",
        "description": (
            "Returns pending tasks for the current user: title, kind, due date, overdue flag, "
            "and associated contact/deal. Use when asked about pending tasks or activities."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_my_suggestions",
        "description": (
            "Returns active AI suggestions (follow-up recommendations, pipeline alerts, etc.) "
            "for the current user. Use when asked for recommendations or what to do next."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_my_deals",
        "description": (
            "Returns a list of deals. scope='mine' = current user's deals; "
            "scope='tenant' = all tenant deals. Use when asked about deals or opportunities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["mine", "tenant"], "default": "mine"},
                "include_won": {"type": "boolean", "default": False},
                "include_lost": {"type": "boolean", "default": False},
            },
            "required": [],
        },
    },
    {
        "name": "get_profitability",
        "description": (
            "Returns profitability: revenue, expenses, profit, profit % and label. "
            "scope='tenant' for overall; scope='user' for the current user. "
            "Use when asked about profit margin, rentabilidad, or financial health."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["tenant", "user"], "default": "tenant"},
                "year": {"type": "integer"},
                "month": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_run_rate",
        "description": (
            "Returns run-rate: won revenue, projected month-end revenue, goal %, gap, "
            "and recommendations. scope='tenant' or scope='user'. "
            "Use when asked about run rate, sales projection, or monthly progress."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["tenant", "user"], "default": "tenant"},
                "year": {"type": "integer"},
                "month": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_expenses_summary",
        "description": (
            "Returns confirmed expenses for a period grouped by kind (fijo/variable). "
            "Use when asked about gastos, expenses, or costs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_monthly_goal",
        "description": (
            "Returns the current global monthly sales goal: target amount and period. "
            "Use when asked about the monthly goal or meta mensual."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_team_performance",
        "description": (
            "Returns performance data per team member: won revenue, run rate, profit margin. "
            "Only for OWNER and PLATFORM_OWNER roles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
            },
            "required": [],
        },
    },

    # ── WRITE TOOLS ────────────────────────────────────────────────────────────
    {
        "name": "create_contact",
        "description": (
            "Creates a new contact (lead) in the CRM. Requires at least a name or phone number. "
            "Use when the user explicitly asks to add or create a new contact or client."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "First name of the contact"},
                "last_name": {"type": "string", "description": "Last name (optional)"},
                "wa_phone": {"type": "string", "description": "WhatsApp phone in E.164 format (e.g. +5215512345678)"},
                "company": {"type": "string", "description": "Company name (optional)"},
                "source": {
                    "type": "string",
                    "description": "Origin: whatsapp_inbound, form, referral, manual",
                    "default": "manual",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_deal",
        "description": (
            "Creates a new deal (opportunity) for an existing contact. "
            "Requires lead_id, pipeline_stage_id, and a title. "
            "Use when the user asks to open, register, or create a new deal or sale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "UUID of the existing contact (lead)"},
                "pipeline_stage_id": {"type": "string", "description": "UUID of the pipeline stage"},
                "title": {"type": "string", "description": "Deal title or description"},
                "amount": {"type": "number", "description": "Deal value in MXN (optional, default 0)"},
                "expected_close_date": {
                    "type": "string",
                    "description": "Expected close date in ISO format YYYY-MM-DD (optional)",
                },
            },
            "required": ["lead_id", "pipeline_stage_id", "title"],
        },
    },
    {
        "name": "move_deal_stage",
        "description": (
            "Moves a deal to a different pipeline stage. "
            "If the new stage is a winning stage, marks the deal as won and generates expense drafts. "
            "Use when the user asks to advance, move, or change a deal's stage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "UUID of the deal"},
                "new_stage_id": {"type": "string", "description": "UUID of the target pipeline stage"},
            },
            "required": ["deal_id", "new_stage_id"],
        },
    },
    {
        "name": "add_note",
        "description": (
            "Adds a note to a contact or deal. "
            "Use when the user wants to record information, observations, or comments about a contact or deal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["contact", "deal"],
                    "description": "Whether the note is for a contact or a deal",
                    "default": "contact",
                },
                "entity_id": {"type": "string", "description": "UUID of the contact or deal"},
                "body": {"type": "string", "description": "Note content (2-500 chars)"},
                "title": {"type": "string", "description": "Short title for the note (optional)"},
            },
            "required": ["entity_id", "body"],
        },
    },
    {
        "name": "create_task",
        "description": (
            "Creates a pending task for a contact. "
            "Use when the user wants to schedule an activity: follow-up, quote, collection, service, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "UUID of the contact (lead)"},
                "title": {"type": "string", "description": "Task title"},
                "task_kind": {
                    "type": "string",
                    "enum": list(_VALID_TASK_KINDS),
                    "description": "Type of task",
                    "default": "seguimiento",
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date and time in ISO 8601 format (e.g. 2026-08-01T10:00:00)",
                },
                "body": {"type": "string", "description": "Additional description (optional)"},
                "assignee_id": {
                    "type": "string",
                    "description": "UUID of the user to assign the task to (default: current user)",
                },
            },
            "required": ["lead_id", "title"],
        },
    },
    {
        "name": "prepare_whatsapp_message",
        "description": (
            "Prepares a WhatsApp message draft for a contact and saves it for human review. "
            "IMPORTANT: This tool NEVER sends messages. It only creates a draft that the user "
            "must review and send manually. Use when the user asks to draft or prepare a message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "UUID of the contact to message"},
                "message": {"type": "string", "description": "The prepared message text"},
            },
            "required": ["contact_id", "message"],
        },
    },
    {
        "name": "set_monthly_goal",
        "description": (
            "Sets or updates the global monthly sales goal for the current or future month. "
            "REQUIRES confirmed=true — only call this after the user has explicitly confirmed "
            "the new goal amount. If confirmed=false, the tool returns a confirmation request "
            "that you must present to the user before proceeding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "total": {
                    "type": "number",
                    "description": "New goal amount in MXN",
                },
                "year": {
                    "type": "integer",
                    "description": "Target year (default: current year)",
                },
                "month": {
                    "type": "integer",
                    "description": "Target month 1-12 (default: current month)",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": (
                        "Must be true to execute. Call with confirmed=false only to generate "
                        "a confirmation message to show the user."
                    ),
                },
            },
            "required": ["total", "confirmed"],
        },
    },
]

# ── Serialization helpers ──────────────────────────────────────────────────────

def _serial(obj: Any) -> Any:
    """json default= handler for types not natively serializable."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def _jsonable(obj: Any) -> Any:
    """Recursively serialize via _serial."""
    return json.loads(json.dumps(obj, default=_serial))

# ── Tool dispatcher ───────────────────────────────────────────────────────────

async def execute_tool(
    name: str,
    args: dict[str, Any],
    user: User,
    tenant: Tenant,
    db: AsyncSession,
) -> dict[str, Any]:
    """Dispatch any tool call (read or write) to the appropriate service/model.

    All results are JSON-serializable. Tenant boundary enforced throughout.
    Business errors return {"error": "..."} — never raise raw exceptions.
    """
    today = date.today()
    year: int = int(args.get("year") or today.year)
    month: int = int(args.get("month") or today.month)

    # ─────────────────────────────────────────────────────────────────────────
    # READ TOOLS
    # ─────────────────────────────────────────────────────────────────────────

    if name == "get_pipeline_status":
        rows = (
            await db.execute(
                select(
                    PipelineStage.name,
                    PipelineStage.order_index,
                    func.count(Deal.id).label("deal_count"),
                    func.coalesce(func.sum(Deal.amount), 0).label("total_value"),
                )
                .outerjoin(
                    Deal,
                    and_(
                        Deal.pipeline_stage_id == PipelineStage.id,
                        Deal.is_won.is_(False),
                        Deal.is_lost.is_(False),
                    ),
                )
                .where(
                    PipelineStage.tenant_id == user.tenant_id,
                    PipelineStage.is_archived.is_(False),
                    PipelineStage.is_won.is_(False),
                    PipelineStage.is_lost.is_(False),
                )
                .group_by(PipelineStage.id, PipelineStage.name, PipelineStage.order_index)
                .order_by(PipelineStage.order_index)
            )
        ).fetchall()
        stages = [
            {"stage": r.name, "deal_count": r.deal_count, "total_value_mxn": float(r.total_value)}
            for r in rows
        ]
        return {
            "stages": stages,
            "total_active_deals": sum(s["deal_count"] for s in stages),
            "total_pipeline_value_mxn": sum(s["total_value_mxn"] for s in stages),
        }

    if name == "search_contacts":
        query = str(args.get("query", "")).strip()
        limit = min(int(args.get("limit", 10)), 20)
        if not query:
            return {"contacts": [], "count": 0}
        rows = (
            await db.execute(
                select(Lead)
                .where(
                    Lead.tenant_id == user.tenant_id,
                    Lead.deleted_at.is_(None),
                    or_(
                        Lead.name.ilike(f"%{query}%"),
                        Lead.last_name.ilike(f"%{query}%"),
                        Lead.wa_phone.ilike(f"%{query}%"),
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        contacts = [
            {
                "id": str(lead.id),
                "name": " ".join(filter(None, [lead.name, lead.last_name])) or "Sin nombre",
                "wa_phone": lead.wa_phone,
                "status": lead.status.value if lead.status else None,
                "assigned_to": str(lead.assigned_to) if lead.assigned_to else None,
            }
            for lead in rows
        ]
        return {"contacts": contacts, "count": len(contacts)}

    if name == "get_contact_context":
        try:
            contact_id = uuid.UUID(str(args.get("contact_id", "")))
        except (ValueError, AttributeError):
            return {"error": "contact_id inválido"}
        ctx_row = (
            await db.execute(
                select(AIEntityContext).where(
                    AIEntityContext.tenant_id == user.tenant_id,
                    AIEntityContext.entity_type == "contact",
                    AIEntityContext.entity_id == contact_id,
                )
            )
        ).scalar_one_or_none()
        events_rows = (
            await db.execute(
                select(AIMemoryEvent)
                .where(AIMemoryEvent.tenant_id == user.tenant_id, AIMemoryEvent.entity_id == contact_id)
                .order_by(AIMemoryEvent.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
        return {
            "contact_id": str(contact_id),
            "context": {
                "summary": ctx_row.context_summary if ctx_row else None,
                "key_facts": ctx_row.key_facts if ctx_row else [],
                "sentiment": ctx_row.sentiment if ctx_row else "unknown",
                "urgency_score": ctx_row.urgency_score if ctx_row else 0,
                "last_interaction": _serial(ctx_row.last_interaction) if ctx_row else None,
            },
            "recent_events": [
                {"event_type": e.event_type, "data": e.event_data, "occurred_at": _serial(e.created_at)}
                for e in events_rows
            ],
        }

    if name == "get_my_tasks":
        now_utc = datetime.now(timezone.utc)
        rows = (
            await db.execute(
                select(Activity, Lead.name, Lead.last_name)
                .join(Lead, Activity.lead_id == Lead.id)
                .where(
                    Activity.tenant_id == user.tenant_id,
                    Activity.activity_type == "task",
                    Activity.completed_at.is_(None),
                    or_(
                        Activity.assignee_id == user.id,
                        and_(Activity.assignee_id.is_(None), Activity.created_by == user.id),
                    ),
                )
                .order_by(Activity.due_date.asc())
                .limit(20)
            )
        ).fetchall()

        def _overdue(due: datetime | None) -> bool:
            if due is None:
                return False
            aware = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
            return aware < now_utc

        tasks = [
            {
                "id": str(r.Activity.id),
                "title": r.Activity.title,
                "task_kind": r.Activity.task_kind,
                "due_date": _serial(r.Activity.due_date),
                "overdue": _overdue(r.Activity.due_date),
                "contact_name": " ".join(filter(None, [r[1], r[2]])) or "Sin nombre",
                "lead_id": str(r.Activity.lead_id),
            }
            for r in rows
        ]
        return {"tasks": tasks, "total": len(tasks), "overdue": sum(1 for t in tasks if t["overdue"])}

    if name == "get_my_suggestions":
        rows = (
            await db.execute(
                select(AgentSuggestion)
                .where(
                    AgentSuggestion.tenant_id == user.tenant_id,
                    AgentSuggestion.status == "suggested",
                    AgentSuggestion.expires_at > func.now(),
                    or_(AgentSuggestion.target_user_id == user.id, AgentSuggestion.target_user_id.is_(None)),
                )
                .order_by(AgentSuggestion.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
        return {
            "suggestions": [
                {
                    "id": str(s.id),
                    "agent_type": s.agent_type,
                    "text": s.suggestion_text,
                    "trigger": s.trigger_description,
                    "entity_type": s.entity_type,
                    "entity_id": str(s.entity_id) if s.entity_id else None,
                    "expires_at": _serial(s.expires_at),
                }
                for s in rows
            ],
            "count": len(rows),
        }

    if name == "get_my_deals":
        scope = str(args.get("scope", "mine"))
        include_won = bool(args.get("include_won", False))
        include_lost = bool(args.get("include_lost", False))
        filters = [Deal.tenant_id == user.tenant_id]
        if scope == "mine":
            filters.append(Deal.owner_id == user.id)
        if not include_won and not include_lost:
            filters += [Deal.is_won.is_(False), Deal.is_lost.is_(False)]
        else:
            status_f = []
            if include_won:
                status_f.append(Deal.is_won.is_(True))
            if include_lost:
                status_f.append(Deal.is_lost.is_(True))
            if status_f:
                filters.append(or_(*status_f))
        rows = (
            await db.execute(
                select(Deal, PipelineStage.name.label("stage_name"))
                .join(PipelineStage, Deal.pipeline_stage_id == PipelineStage.id)
                .where(*filters)
                .order_by(Deal.updated_at.desc())
                .limit(20)
            )
        ).fetchall()
        deals = [
            {
                "id": str(r.Deal.id),
                "title": r.Deal.title,
                "amount_mxn": float(r.Deal.amount),
                "stage": r.stage_name,
                "is_won": r.Deal.is_won,
                "is_lost": r.Deal.is_lost,
                "deal_type": r.Deal.deal_type,
                "expected_close": _serial(r.Deal.expected_close_date),
                "lead_id": str(r.Deal.lead_id),
            }
            for r in rows
        ]
        active_value = sum(d["amount_mxn"] for d in deals if not d["is_won"] and not d["is_lost"])
        return {"deals": deals, "count": len(deals), "active_pipeline_value_mxn": active_value}

    if name == "get_profitability":
        scope = str(args.get("scope", "tenant"))
        result = (
            await get_user_profitability(tenant, user.id, year, month, db)
            if scope == "user"
            else await get_tenant_profitability(tenant, year, month, db)
        )
        return _jsonable(result)

    if name == "get_run_rate":
        scope = str(args.get("scope", "tenant"))
        result = (
            await get_user_run_rate(tenant, user.id, year, month, db)
            if scope == "user"
            else await get_tenant_run_rate(tenant, year, month, db)
        )
        return _jsonable(result)

    if name == "get_expenses_summary":
        kind_rows = (
            await db.execute(
                select(Expense.kind, func.sum(Expense.amount).label("total"))
                .where(
                    Expense.tenant_id == user.tenant_id,
                    Expense.status == "confirmed",
                    func.extract("year", Expense.incurred_at) == year,
                    func.extract("month", Expense.incurred_at) == month,
                )
                .group_by(Expense.kind)
            )
        ).fetchall()
        by_kind = {r.kind: float(r.total) for r in kind_rows}
        return {
            "year": year, "month": month,
            "by_kind": by_kind,
            "total_mxn": sum(by_kind.values()),
            "fijo_mxn": by_kind.get("fijo", 0.0),
            "variable_mxn": by_kind.get("variable", 0.0),
        }

    if name == "get_monthly_goal":
        goal = await get_current_month_goal(user.tenant_id, year, month, db)
        if goal is None:
            return {"year": year, "month": month, "goal_set": False, "amount_mxn": None}
        return {"year": year, "month": month, "goal_set": True, "amount_mxn": float(goal.amount), "is_draft": goal.is_draft}

    if name == "get_team_performance":
        if user.role not in _OWNER_ROLES:
            return {"error": "Sin acceso. Solo el propietario puede ver el rendimiento individual del equipo."}
        team_users = (
            await db.execute(
                select(User).where(
                    User.tenant_id == user.tenant_id,
                    User.is_active.is_(True),
                    User.role != UserRole.PLATFORM_OWNER,
                )
            )
        ).scalars().all()
        members = []
        for u in team_users:
            rr = await get_user_run_rate(tenant, u.id, year, month, db)
            prof = await get_user_profitability(tenant, u.id, year, month, db)
            members.append({
                "user_id": str(u.id), "name": u.name, "role": u.role.value,
                "won_revenue_mxn": rr["won_revenue"], "run_rate_mxn": rr["run_rate"],
                "user_goal_mxn": rr.get("user_goal"), "pct_of_goal": rr.get("pct_of_goal"),
                "expenses_mxn": prof["expenses"], "profit_mxn": prof["profit"],
                "profit_pct": prof["profit_pct"], "label": prof["label"],
            })
        members.sort(key=lambda m: m["won_revenue_mxn"], reverse=True)
        return {"year": year, "month": month, "team": members, "count": len(members)}

    # ─────────────────────────────────────────────────────────────────────────
    # WRITE TOOLS
    # ─────────────────────────────────────────────────────────────────────────

    if name == "create_contact":
        contact_name = str(args.get("name", "")).strip() or None
        wa_phone = str(args.get("wa_phone", "")).strip() or None
        if not contact_name and not wa_phone:
            return {"error": "Se requiere al menos el nombre o el teléfono del contacto"}
        if not user.branch_id:
            return {"error": "El usuario no tiene sucursal asignada — no se puede crear el contacto"}

        lead = Lead(
            branch_id=user.branch_id,
            tenant_id=user.tenant_id,
            wa_phone=wa_phone,
            name=contact_name,
            last_name=str(args.get("last_name", "")).strip() or None,
            company=str(args.get("company", "")).strip() or None,
            prospection_source=str(args.get("source", "manual")),
            assigned_to=user.id,
            status=LeadStatus.NUEVO,
            source=LeadSource.MANUAL,
            sentiment=LeadSentiment.NEUTRAL,
        )
        db.add(lead)
        await db.flush()
        lead_id = lead.id
        await db.commit()

        return {
            "created": True,
            "contact_id": str(lead_id),
            "name": contact_name or "Sin nombre",
            "wa_phone": wa_phone,
        }

    if name == "create_deal":
        try:
            lead_id = uuid.UUID(str(args.get("lead_id", "")))
            stage_id = uuid.UUID(str(args.get("pipeline_stage_id", "")))
        except (ValueError, AttributeError):
            return {"error": "lead_id o pipeline_stage_id inválidos"}

        lead = await db.get(Lead, lead_id)
        if not lead or lead.tenant_id != user.tenant_id or lead.deleted_at is not None:
            return {"error": "Contacto no encontrado en este tenant"}

        stage = await db.get(PipelineStage, stage_id)
        if not stage or stage.tenant_id != user.tenant_id:
            return {"error": "Etapa de pipeline no encontrada en este tenant"}

        title = str(args.get("title", "")).strip()
        if not title:
            return {"error": "El título del deal es requerido"}

        amount_raw = args.get("amount")
        amount = Decimal(str(amount_raw)) if amount_raw is not None else Decimal("0")

        close_date = None
        if args.get("expected_close_date"):
            try:
                close_date = date.fromisoformat(str(args["expected_close_date"]))
            except ValueError:
                pass

        deal = Deal(
            tenant_id=user.tenant_id,
            lead_id=lead_id,
            pipeline_stage_id=stage_id,
            title=title,
            amount=amount,
            probability=stage.probability_default,
            expected_close_date=close_date,
            owner_id=user.id,
        )
        db.add(deal)
        await db.flush()
        deal_id_new = deal.id
        await db.commit()

        try:
            evt = AIMemoryEvent(
                tenant_id=user.tenant_id,
                entity_type="deal",
                entity_id=deal_id_new,
                event_type="deal_created",
                event_data={"title": title, "amount": str(amount)},
                actor_id=user.id,
            )
            db.add(evt)
            await db.flush()
            evt_id = str(evt.id)
            await db.commit()
            from app.tasks.ai_memory_tasks import update_entity_context_task
            update_entity_context_task.delay(evt_id)
        except Exception:
            logger.exception("copilot create_deal: AIMemoryEvent failed for deal %s", deal_id_new)

        return {
            "created": True,
            "deal_id": str(deal_id_new),
            "title": title,
            "amount_mxn": float(amount),
            "stage": stage.name,
            "lead_id": str(lead_id),
        }

    if name == "move_deal_stage":
        try:
            deal_id = uuid.UUID(str(args.get("deal_id", "")))
            new_stage_id = uuid.UUID(str(args.get("new_stage_id", "")))
        except (ValueError, AttributeError):
            return {"error": "deal_id o new_stage_id inválidos"}

        deal = await db.get(Deal, deal_id)
        if not deal or deal.tenant_id != user.tenant_id:
            return {"error": "Deal no encontrado en este tenant"}

        new_stage = await db.get(PipelineStage, new_stage_id)
        if not new_stage or new_stage.tenant_id != user.tenant_id:
            return {"error": "Etapa de pipeline no encontrada en este tenant"}

        prev_stage_id = deal.pipeline_stage_id
        prev_is_won = deal.is_won

        deal.pipeline_stage_id = new_stage_id
        deal.probability = new_stage.probability_default
        if new_stage.is_won:
            deal.is_won = True
        if new_stage.is_lost:
            deal.is_lost = True

        db.add(DealStageHistory(
            tenant_id=user.tenant_id,
            deal_id=deal_id,
            from_stage_id=prev_stage_id,
            to_stage_id=new_stage_id,
        ))
        await db.commit()
        await db.refresh(deal)

        try:
            evt = AIMemoryEvent(
                tenant_id=user.tenant_id,
                entity_type="deal",
                entity_id=deal_id,
                event_type="deal_stage_changed",
                event_data={
                    "from_stage_id": str(prev_stage_id) if prev_stage_id else None,
                    "to_stage_id": str(new_stage_id),
                },
                actor_id=user.id,
            )
            db.add(evt)
            await db.flush()
            evt_id = str(evt.id)
            await db.commit()
            from app.tasks.ai_memory_tasks import update_entity_context_task
            update_entity_context_task.delay(evt_id)
        except Exception:
            logger.exception("copilot move_deal_stage: AIMemoryEvent failed for deal %s", deal_id)

        expense_drafts = 0
        if new_stage.is_won and not prev_is_won:
            try:
                from app.services.expense_generation import generate_deal_expense_drafts
                drafts = await generate_deal_expense_drafts(deal, db)
                await db.commit()
                expense_drafts = len(drafts)
            except Exception:
                logger.exception("copilot move_deal_stage: expense drafts failed for deal %s", deal_id)

        return {
            "moved": True,
            "deal_id": str(deal_id),
            "new_stage": new_stage.name,
            "is_won": deal.is_won,
            "is_lost": deal.is_lost,
            "expense_drafts_generated": expense_drafts,
        }

    if name == "add_note":
        try:
            entity_id = uuid.UUID(str(args.get("entity_id", "")))
        except (ValueError, AttributeError):
            return {"error": "entity_id inválido"}

        note_body = str(args.get("body", "")).strip()
        if len(note_body) < 2:
            return {"error": "El contenido de la nota debe tener al menos 2 caracteres"}

        entity_type = str(args.get("entity_type", "contact"))
        lead_id: uuid.UUID
        deal_id_for_note: uuid.UUID | None = None

        if entity_type == "deal":
            deal = await db.get(Deal, entity_id)
            if not deal or deal.tenant_id != user.tenant_id:
                return {"error": "Deal no encontrado en este tenant"}
            lead_id = deal.lead_id
            deal_id_for_note = entity_id
        else:
            lead = await db.get(Lead, entity_id)
            if not lead or lead.tenant_id != user.tenant_id or lead.deleted_at is not None:
                return {"error": "Contacto no encontrado en este tenant"}
            lead_id = entity_id

        title_raw = args.get("title")
        title_str = str(title_raw)[:255] if title_raw else None

        activity = Activity(
            lead_id=lead_id,
            tenant_id=user.tenant_id,
            activity_type="note",
            title=title_str,
            body=note_body[:500],
            created_by=user.id,
            deal_id=deal_id_for_note,
        )
        db.add(activity)

        lead_obj = await db.get(Lead, lead_id)
        if lead_obj:
            lead_obj.last_activity_summary = (title_str or note_body[:255])[:255]

        await db.flush()
        activity_id = activity.id
        await db.commit()

        try:
            evt = AIMemoryEvent(
                tenant_id=user.tenant_id,
                entity_type="contact",
                entity_id=lead_id,
                event_type="note_added",
                event_data={"title": title_str, "body": note_body[:200]},
                actor_id=user.id,
            )
            db.add(evt)
            await db.flush()
            evt_id = str(evt.id)
            await db.commit()
            from app.tasks.ai_memory_tasks import update_entity_context_task
            update_entity_context_task.delay(evt_id)
        except Exception:
            logger.exception("copilot add_note: AIMemoryEvent failed")

        return {
            "created": True,
            "activity_id": str(activity_id),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
        }

    if name == "create_task":
        try:
            lead_id = uuid.UUID(str(args.get("lead_id", "")))
        except (ValueError, AttributeError):
            return {"error": "lead_id inválido"}

        lead = await db.get(Lead, lead_id)
        if not lead or lead.tenant_id != user.tenant_id or lead.deleted_at is not None:
            return {"error": "Contacto no encontrado en este tenant"}

        task_kind_raw = str(args.get("task_kind", "seguimiento"))
        task_kind = task_kind_raw if task_kind_raw in _VALID_TASK_KINDS else "otro"

        due_date: datetime | None = None
        if args.get("due_date"):
            try:
                due_date = datetime.fromisoformat(str(args["due_date"]))
                if due_date.tzinfo is None:
                    due_date = due_date.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        assignee_id = user.id
        if args.get("assignee_id"):
            try:
                a_id = uuid.UUID(str(args["assignee_id"]))
                assignee = await db.get(User, a_id)
                if assignee and assignee.tenant_id == user.tenant_id:
                    assignee_id = a_id
            except (ValueError, AttributeError):
                pass

        title_str = str(args.get("title", "")).strip()[:255] or None
        body_str = str(args.get("body", "")).strip()[:500] or None

        activity = Activity(
            lead_id=lead_id,
            tenant_id=user.tenant_id,
            activity_type="task",
            title=title_str,
            body=body_str,
            due_date=due_date,
            created_by=user.id,
            task_kind=task_kind,
            assignee_id=assignee_id,
        )
        db.add(activity)
        lead.last_activity_summary = f"Tarea: {title_str or task_kind}"
        await db.flush()
        activity_id = activity.id
        await db.commit()

        return {
            "created": True,
            "task_id": str(activity_id),
            "task_kind": task_kind,
            "lead_id": str(lead_id),
            "due_date": _serial(due_date) if due_date else None,
            "assignee_id": str(assignee_id),
        }

    if name == "prepare_whatsapp_message":
        # Reusar AIDraftEdit (Etapa 7.2 — leads.py:667-683)
        # original = AI draft; edited = "" (not sent); message_id = None (no message yet)
        try:
            contact_id = uuid.UUID(str(args.get("contact_id", "")))
        except (ValueError, AttributeError):
            return {"error": "contact_id inválido"}

        lead = await db.get(Lead, contact_id)
        if not lead or lead.tenant_id != user.tenant_id or lead.deleted_at is not None:
            return {"error": "Contacto no encontrado en este tenant"}

        message_text = str(args.get("message", "")).strip()
        if not message_text:
            return {"error": "El texto del mensaje es requerido"}

        draft = AIDraftEdit(
            tenant_id=user.tenant_id,
            user_id=user.id,
            contact_id=contact_id,
            original=message_text,
            edited="",
            char_delta=0,
        )
        db.add(draft)
        await db.flush()
        draft_id = draft.id
        await db.commit()

        contact_name = " ".join(filter(None, [lead.name, lead.last_name])) or "el contacto"
        return {
            "draft_saved": True,
            "draft_id": str(draft_id),
            "message": message_text,
            "contact_name": contact_name,
            "wa_phone": lead.wa_phone or "desconocido",
            "note": (
                f"Borrador listo para {contact_name}. "
                "NO fue enviado — el usuario debe revisarlo y enviarlo manualmente."
            ),
        }

    if name == "set_monthly_goal":
        confirmed = bool(args.get("confirmed", False))
        total_raw = args.get("total")

        if total_raw is None:
            return {"error": "El monto (total) es requerido"}

        try:
            amount = Decimal(str(total_raw))
            if amount < 0:
                raise ValueError
        except (ValueError, Exception):
            return {"error": f"Monto inválido: {total_raw}"}

        if not confirmed:
            return {
                "pending_confirmation": True,
                "amount_requested_mxn": float(amount),
                "message": (
                    f"¿Confirmas que deseas establecer la meta mensual global en "
                    f"${float(amount):,.0f} MXN para {year}/{month:02d}? "
                    "Responde 'sí' para proceder."
                ),
            }

        goal_year = year
        goal_month = month

        if (goal_year, goal_month) < (today.year, today.month):
            return {"error": f"No se puede modificar la meta de un periodo pasado ({goal_year}/{goal_month:02d})"}

        # _find_existing_goal logic inline (reutiliza el mismo patrón de goals.py:47-71)
        existing = (
            await db.execute(
                select(MonthlyGoal).where(
                    MonthlyGoal.tenant_id == user.tenant_id,
                    MonthlyGoal.period_year == goal_year,
                    MonthlyGoal.period_month == goal_month,
                    MonthlyGoal.dimension == "global",
                    MonthlyGoal.dimension_value_text.is_(None),
                    MonthlyGoal.dimension_value_uuid.is_(None),
                )
            )
        ).scalar_one_or_none()

        def _goal_as_dict(g: MonthlyGoal) -> dict:
            return {
                "id": str(g.id),
                "period_year": g.period_year,
                "period_month": g.period_month,
                "amount": str(g.amount),
                "dimension": g.dimension,
                "is_draft": g.is_draft,
            }

        if existing:
            before = _goal_as_dict(existing)
            existing.amount = amount
            existing.is_draft = False
            await db.flush()
            after = _goal_as_dict(existing)
            db.add(MonthlyGoalHistory(
                tenant_id=user.tenant_id,
                goal_id=existing.id,
                action="goal_updated",
                before_data=before,
                after_data=after,
                changed_by=user.id,
            ))
            await db.commit()
            return {
                "set": True,
                "goal_id": str(existing.id),
                "amount_mxn": float(amount),
                "year": goal_year,
                "month": goal_month,
                "action": "updated",
            }

        goal = MonthlyGoal(
            tenant_id=user.tenant_id,
            period_year=goal_year,
            period_month=goal_month,
            amount=amount,
            currency="MXN",
            dimension="global",
            is_draft=False,
            created_by=user.id,
        )
        db.add(goal)
        await db.flush()
        after = _goal_as_dict(goal)
        db.add(MonthlyGoalHistory(
            tenant_id=user.tenant_id,
            goal_id=goal.id,
            action="goal_created",
            before_data=None,
            after_data=after,
            changed_by=user.id,
        ))
        await db.commit()
        return {
            "set": True,
            "goal_id": str(goal.id),
            "amount_mxn": float(amount),
            "year": goal_year,
            "month": goal_month,
            "action": "created",
        }

    return {"error": f"Tool '{name}' no reconocida"}
