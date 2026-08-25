"""C2/C3 — Copiloto: definición y dispatcher de tools (lectura + escritura).

C2: 11 tools de lectura (sin side-effects).
C3: 8 tools de escritura ejecutables por el modelo.
Expansión Finanzas/Gastos, Ronda 1: 7 tools de lectura adicionales
  (list_expenses, list_expense_categories, list_recurring_expenses,
  list_expense_rules, list_product_categories, list_goal_assignments,
  list_finance_permissions) — ver más abajo.
Expansión Finanzas/Gastos, Ronda 2a-i: 5 tools de escritura — núcleo de
  gastos (create_expense, update_expense, confirm_expense,
  confirm_all_draft_expenses, trigger_recurring_expense_generation) — ver
  más abajo.
Expansión Finanzas/Gastos, Ronda 2a-ii: 8 tools de escritura — catálogos
  de finanzas, 4 pares create/update (expense_category, recurring_expense,
  expense_rule, product_category) — ver más abajo.
Expansión Finanzas/Gastos, Ronda 2a-iii: 2 tools de escritura — metas
  (update_monthly_goal por id, set_goal_assignments) — cierra la Ronda 2a
  completa. Ver más abajo.

Knowledge Base (app/api/kb.py): 9 tools (1 de escritura fire-and-forget,
  3 de lectura, 4 de escritura, 1 de escritura con confirmación en dos
  pasos) — reindex_kb, kb_status, list_kb_documents, get_kb_document,
  create_kb_document, update_kb_document, delete_kb_document,
  add_kb_fragment, delete_kb_fragment. Primer módulo huérfano fuera de
  Finanzas/Gastos — NO usa require_finance_access, usa control de acceso
  por rol vía check_permission + ActionDefinition.required_role, mismo
  patrón que list_finance_permissions/get_team_performance/
  trigger_recurring_expense_generation (required_role del catálogo es
  metadata declarativa, no se aplica sola — el chequeo real es la llamada
  a check_permission dentro de cada bloque). Ver más abajo.

Política de confirmación:
  create_contact, create_deal, move_deal_stage, add_note, create_task,
  dismiss_suggestion
    → ejecutan de inmediato cuando el modelo las llama.
  prepare_whatsapp_message
    → guarda borrador en AIDraftEdit (Etapa 7.2); NUNCA envía nada.
  set_monthly_goal
    → requiere confirmed=True en el input; si confirmed=False devuelve
      mensaje de confirmación para que Claude lo presente al usuario.
      El chequeo require_finance_access corre ANTES del flujo confirmed
      (hallazgo #6 de docs/PERMISSIONS_DRIFT_BACKLOG.md) — así no se le
      revela el monto/mensaje de confirmación a alguien sin acceso.

dismiss_suggestion (Copiloto Fase 1, ronda de agents.py) valida ownership
real (target_user_id/target_role, mismo patrón que
agents.py::list_suggestions) — a propósito NO reutiliza
agents.py::_get_suggestion_for_user, que solo valida tenant_id (hallazgo #7
de docs/PERMISSIONS_DRIFT_BACKLOG.md). confirm_suggestion queda como stub
sin conectar en app/copilot/actions_catalog.py — dispara ejecución real vía
Celery (puede incluir envío de WhatsApp a un lead), eso es Fase 6.

get_profitability, get_run_rate y get_expenses_summary (hallazgo #8 de
docs/PERMISSIONS_DRIFT_BACKLOG.md) ahora validan acceso a finanzas vía
app/copilot/finance_access.py::require_finance_access antes de ejecutar —
mismo criterio OWNER/PLATFORM_OWNER-o-FinancePermission que ya exigían sus
endpoints REST equivalentes (app/api/finance.py, app/api/profitability.py).

Las 7 tools de lectura de la Ronda 1 de Finanzas/Gastos replican esa misma
protección: list_expenses/list_expense_categories/list_recurring_expenses/
list_expense_rules/list_product_categories/list_goal_assignments llaman
require_finance_access (branch_id del filtro si aplica, None si no);
list_finance_permissions es la excepción — usa check_permission +
ActionDefinition.required_role=_OWNER_TIER (mismo patrón que
get_team_performance), igual que su endpoint REST real
(app/api/finance.py::list_finance_permissions usa _require_owner, no
_require_finance_access — mostrar quién tiene acceso a finanzas es en sí
una acción de owner, no de cualquiera con acceso de lectura a finanzas).

set_monthly_goal (hallazgo #6 de docs/PERMISSIONS_DRIFT_BACKLOG.md) delega
el upsert a app/services/goals_service.py::upsert_monthly_goal, compartido
con app/api/goals.py::create_or_update_monthly_goal — unifica la lógica de
negocio que antes estaba duplicada inline en ambos lados. El chequeo de
acceso (require_finance_access aquí, _require_finance_access en el REST) y
el flujo confirmed=bool del Copiloto quedan fuera del servicio, son
responsabilidad de cada caller.

Las 5 tools de escritura de la Ronda 2a-i (núcleo de gastos) replican la
lógica de sus endpoints REST equivalentes en app/api/finance.py
(create_expense, update_expense, confirm_expense,
confirm_all_draft_expenses, trigger_recurring_expense_generation).
create_expense/update_expense/confirm_expense/confirm_all_draft_expenses
llaman require_finance_access dentro del dispatcher — update_expense y
confirm_expense usan el branch_id DEL GASTO YA EXISTENTE (no el que venga
en args), igual que el REST. trigger_recurring_expense_generation es la
única excepción: su endpoint REST real usa _require_owner, no
_require_finance_access, así que acá usa check_permission +
ActionDefinition.required_role=_OWNER_TIER (mismo patrón que
list_finance_permissions/get_team_performance) en vez de
require_finance_access.

Las 8 tools de escritura de la Ronda 2a-ii (catálogos de finanzas, 4 pares
create/update) replican sus endpoints REST equivalentes en
app/api/finance.py (expense-categories, recurring-expenses, expense-rules)
y app/api/goals.py (product-categories) — todas llaman
require_finance_access(user, None, db), tenant-wide igual que sus 4
hermanas de lectura de la Ronda 1. create_product_category/
update_product_category atrapan IntegrityError (ProductCategory tiene un
unique constraint (tenant_id, name)) con rollback explícito antes de
retornar el error — sin ese rollback la sesión queda inutilizable para el
resto del request. update_expense_rule replica una limitación existente
del REST: deal_type_filter nunca se puede limpiar a None una vez seteado
(mismo patrón `if body.deal_type_filter is not None` del endpoint real).

Las 2 tools de escritura de la Ronda 2a-iii (metas) cierran la Ronda 2a
completa. Son DISTINTAS de set_monthly_goal (arriba) y NO reusan
upsert_monthly_goal — solo importan las funciones puras is_past_period y
goal_as_dict de goals_service.py.
  - update_monthly_goal (por id) replica app/api/goals.py::update_monthly_goal
    (PATCH /goals/monthly-goals/{goal_id}): lógica inline propia del
    endpoint, actualiza una meta YA EXISTENTE por id (no por dimensión),
    con partial update `if "campo" in args and args["campo"] is not None:`
    SIN el sentinel _UNSET de upsert_monthly_goal — mismo estilo que
    update_expense_rule: notes nunca se puede limpiar a None una vez
    seteado, es una limitación existente del REST, no un bug.
  - set_goal_assignments replica app/api/goals.py::set_goal_assignments
    (PUT /goals/monthly-goals/{goal_id}/assignments): reemplaza TODAS las
    asignaciones de una meta de golpe (bulk set, no incremental), patrón
    delete-then-insert con amount auto-calculado
    (goal.amount * share_percent / 100), validación de tenant sobre los
    user_id, regla de suma=100% (tolerancia 0.01) solo para metas
    no-borrador con lista no vacía, y una sola entrada de
    MonthlyGoalHistory (action="assignment_changed") para todo el cambio en
    bloque. A propósito NO valida periodo pasado — el REST real tampoco lo
    hace para esta acción (a diferencia de update_monthly_goal, que sí),
    así que no se agrega esa restricción acá.

Las 9 tools de Knowledge Base replican sus endpoints REST equivalentes en
app/api/kb.py línea por línea — reindex_kb dispara ingest_all_documents vía
asyncio.create_task (fire-and-forget dentro del mismo proceso, NO Celery,
tal como el REST real). create_kb_document/update_kb_document/
add_kb_fragment llaman a app/api/kb.py::_embed_and_store (importada directo
de kb.py, no duplicada — no hay import circular: kb.py no importa
copilot_tools.py ni actions_catalog.py), que a su vez llama a la API de
OpenAI de forma SÍNCRONA dentro del dispatcher — puede tardar varios
segundos, es esperado, no se le agrega timeout ni mecanismo async
adicional. _embed_and_store lanza HTTPException(503) si OPENAI_API_KEY no
está configurado — el dispatcher atrapa esa excepción puntual y la
convierte en {"error": ...}, nunca deja que se propague cruda. Ambas
create_kb_document y add_kb_fragment son idempotentes por content_hash
(mismo contenido = mismo documento, sin regenerar embeddings) — replicado
tal cual del REST. delete_kb_document tiene flujo de confirmación en dos
pasos para documentos is_auto_generated=True (retorna
requires_confirmation=True sin borrar hasta que el caller reintente con
confirm=True); delete_kb_fragment es el alias legacy y a propósito NO
tiene ese guardrail — borra directo incluso si is_auto_generated=True,
mismo comportamiento asimétrico que su endpoint REST real (documentado ahí
como "sin warning de auto-generated", no es un bug de este wireo).
get_kb_document reconstruye el content desde KnowledgeChunk ordenados por
chunk_index cuando doc.content es None (documento file-based) — mismo
fallback exacto que el REST.

Tool-use format: nativo Anthropic SDK 0.104.x
  name, description, input_schema (JSON Schema)
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.bot_engine import find_lead_by_phone
from app.ai.ingestion import _sha256, ingest_all_documents
from app.api.kb import _embed_and_store
from app.copilot.finance_access import require_finance_access
from app.models.activity import Activity
from app.models.agent import AgentSuggestion
from app.models.ai_memory import AIDraftEdit, AIEntityContext, AIMemoryEvent
from app.models.deal import Deal
from app.models.deal_stage_history import DealStageHistory
from app.models.finance import Expense, ExpenseCategory, ExpenseRule, FinancePermission, RecurringExpense
from app.models.goals import MonthlyGoal, MonthlyGoalAssignment, MonthlyGoalHistory, ProductCategory
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus
from app.models.pipeline import PipelineStage
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.expense_generation import generate_recurring_expenses
from app.services.goals_service import goal_as_dict as _goal_as_dict
from app.services.goals_service import is_past_period as _is_past_period
from app.services.goals_service import upsert_monthly_goal
from app.services.profitability import (
    get_current_month_goal,
    get_tenant_profitability,
    get_tenant_run_rate,
    get_user_profitability,
    get_user_run_rate,
)
from app.services.whatsapp import normalize_mx_phone

logger = logging.getLogger(__name__)

_VALID_TASK_KINDS = (
    "cobro", "cotizacion", "servicio", "seguimiento",
    "queja", "refaccion", "facturacion", "devolucion", "otro",
)

# reindex_kb dispara ingest_all_documents fire-and-forget (asyncio.create_task,
# no Celery) — mismo patrón que app/api/kb.py::_background_tasks. Set propio
# acá (no se reutiliza el de kb.py) porque cada proceso/dispatcher gestiona su
# propio ciclo de vida de tasks en background.
_kb_background_tasks: set[asyncio.Task] = set()

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
        "name": "list_expenses",
        "description": (
            "Lists individual expense records with full detail (id, category, amount, kind, "
            "currency, status, date, description, etc.), with optional filters by month, kind "
            "(fijo/variable), category_id, status (draft/confirmed), and branch_id. Unlike "
            "get_expenses_summary (which only returns totals grouped by kind), this returns "
            "the actual list of expense rows. Use when the user wants to see, review, or "
            "filter individual gastos, not just a total."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "format": "date", "description": "Any day within the target month (YYYY-MM-DD)"},
                "kind": {"type": "string", "enum": ["fijo", "variable"]},
                "category_id": {"type": "string", "format": "uuid"},
                "status": {"type": "string", "enum": ["draft", "confirmed"]},
                "branch_id": {"type": "string", "format": "uuid"},
            },
            "required": [],
        },
    },
    {
        "name": "list_expense_categories",
        "description": (
            "Lists expense categories (name, kind, icon, active flag) configured for the "
            "tenant. Use when the user asks what expense categories exist, or before "
            "creating/filtering an expense by category."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_inactive": {"type": "boolean", "description": "Include inactive categories (default false)"},
            },
            "required": [],
        },
    },
    {
        "name": "list_recurring_expenses",
        "description": (
            "Lists recurring (monthly) expense definitions: category, amount, day of month, "
            "description, active flag. Use when asked about gastos recurrentes or fixed "
            "monthly charges configured for the tenant."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_inactive": {"type": "boolean", "description": "Include inactive recurring expenses (default false)"},
            },
            "required": [],
        },
    },
    {
        "name": "list_expense_rules",
        "description": (
            "Lists automatic expense generation rules tied to deals (percent_of_deal, "
            "fixed_per_deal, percent_of_cost), including their category, value, deal type "
            "filter, and auto-confirm flag. Use when asked how expenses are auto-generated "
            "from won deals, or what rules exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_inactive": {"type": "boolean", "description": "Include inactive rules (default false)"},
            },
            "required": [],
        },
    },
    {
        "name": "list_product_categories",
        "description": (
            "Lists product categories used to segment monthly goals by product line. "
            "Use when asked what product categories exist, or before setting a "
            "product-category-scoped monthly goal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_inactive": {"type": "boolean", "description": "Include inactive product categories (default false)"},
            },
            "required": [],
        },
    },
    {
        "name": "list_goal_assignments",
        "description": (
            "Lists how a specific monthly goal is split across team members: each assigned "
            "user, their share percent, and their resulting amount. Requires goal_id. Use "
            "when asked who a monthly goal is assigned to, or how it's distributed across "
            "the team."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "format": "uuid", "description": "UUID of the monthly goal"},
            },
            "required": ["goal_id"],
        },
    },
    {
        "name": "list_finance_permissions",
        "description": (
            "Lists which users have been granted access to financial reports, and whether "
            "that access is tenant-wide or scoped to a specific branch. Only for OWNER and "
            "PLATFORM_OWNER roles. Use when asked who can see finanzas, or to audit finance "
            "access grants."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
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
    {
        "name": "update_monthly_goal",
        "description": (
            "Updates an existing monthly goal identified by its id — partial update, only "
            "the fields provided are changed. Requires goal_id. Editable fields: amount, "
            "currency, notes, is_draft. Note: notes can only be set, never cleared back to "
            "none, through this action. Fails if the goal belongs to a past period. Use "
            "when the user wants to edit a specific monthly goal (found via get_monthly_goal "
            "or list operations), as opposed to set_monthly_goal which upserts by period/dimension."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "format": "uuid", "description": "UUID of the monthly goal to update"},
                "amount": {"type": "number", "description": "New goal amount (optional)"},
                "currency": {"type": "string", "description": "New currency code (optional)"},
                "notes": {"type": "string", "description": "New notes (optional; cannot be cleared once set)"},
                "is_draft": {"type": "boolean", "description": "New draft flag (optional)"},
            },
            "required": ["goal_id"],
        },
    },
    {
        "name": "set_goal_assignments",
        "description": (
            "Replaces the ENTIRE set of user assignments for a monthly goal in one shot — "
            "this is a full replacement, not an incremental add. Each assignment has a "
            "user_id and a share_percent (0-100); each user's resulting amount is "
            "auto-calculated as goal.amount * share_percent / 100. For a non-draft goal "
            "with a non-empty assignment list, the share percentages must sum to exactly "
            "100% (tolerance 0.01) — mark the goal as draft to save a partial split. Use "
            "when the user wants to define or change how a monthly goal is split across "
            "team members."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "format": "uuid", "description": "UUID of the monthly goal"},
                "assignments": {
                    "type": "array",
                    "description": "Full list of assignments to set (replaces any existing ones)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string", "format": "uuid", "description": "UUID of the user"},
                            "share_percent": {"type": "number", "description": "Share percent, 0-100"},
                        },
                        "required": ["user_id", "share_percent"],
                    },
                },
            },
            "required": ["goal_id", "assignments"],
        },
    },
    {
        "name": "dismiss_suggestion",
        "description": (
            "Dismisses an active AI suggestion addressed to the current user, with an "
            "optional reason. Use when the user wants to discard, ignore, or reject a "
            "suggested action (from get_my_suggestions) instead of confirming it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestion_id": {"type": "string", "format": "uuid", "description": "UUID of the suggestion to dismiss"},
                "reason": {"type": "string", "description": "Optional reason for dismissing (optional)"},
            },
            "required": ["suggestion_id"],
        },
    },
    {
        "name": "reindex_kb",
        "description": (
            "Triggers a background re-index of all Knowledge Base .md files on disk for the "
            "tenant. Runs asynchronously — returns immediately with status='processing', the "
            "actual indexing happens in the background. Only for OWNER and IT roles. Use when "
            "the user wants to refresh or rebuild the bot's knowledge base from source files."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kb_status",
        "description": (
            "Returns a summary of the Knowledge Base: each indexed document (filename, title, "
            "chunk count, indexed_at), plus totals (total_documents, total_chunks, "
            "last_indexed). Only for OWNER, GERENTE, and IT roles. Use when asked about the "
            "state or freshness of the knowledge base."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_kb_documents",
        "description": (
            "Lists Knowledge Base documents, paginated, without embeddings — id, title, a "
            "content preview (truncated to 200 chars), chunk_count, is_auto_generated, and "
            "created_at. Only for OWNER, GERENTE, and IT roles. Use when the user wants to "
            "browse or review the documents that feed the bot's answers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page number, 1-based (default 1)"},
                "limit": {"type": "integer", "description": "Results per page, 1-100 (default 20)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_kb_document",
        "description": (
            "Returns a single Knowledge Base document in full, without embeddings — id, title, "
            "content, chunk_count, is_auto_generated, created_at, updated_at. If the document "
            "is file-based (no content stored directly), the content is reconstructed by "
            "concatenating its chunks in order. Only for OWNER, GERENTE, and IT roles. Requires "
            "doc_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID of the KB document"},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "create_kb_document",
        "description": (
            "Creates a new Knowledge Base document and generates its embeddings — this can "
            "take several seconds for long content. Requires title (1-255 chars) and content "
            "(10-20,000 chars). Idempotent by content hash: if a document with the exact same "
            "content already exists for the tenant, returns that existing document instead of "
            "creating a duplicate. Only for OWNER and IT roles. Use when the user wants to add "
            "new information for the bot to use in its answers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title, 1-255 chars"},
                "content": {"type": "string", "description": "Document content, 10-20,000 chars"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "update_kb_document",
        "description": (
            "Updates an existing Knowledge Base document — partial update, only the fields "
            "provided are changed. Requires doc_id. If content changes (different hash from "
            "what's stored), the old embeddings are deleted and regenerated — can take several "
            "seconds. Only for OWNER and IT roles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID of the KB document to update"},
                "title": {"type": "string", "description": "New title, 1-255 chars (optional)"},
                "content": {"type": "string", "description": "New content, 10-20,000 chars (optional)"},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "delete_kb_document",
        "description": (
            "Deletes a Knowledge Base document and its chunks. If the document was "
            "auto-generated from the tenant's onboarding (is_auto_generated=true) and "
            "confirm is not true, this does NOT delete anything — it returns a warning and "
            "requires_confirmation=true instead. In that case, present the warning to the "
            "user and, if they confirm, call this tool again with confirm=true to actually "
            "delete. Only for OWNER and IT roles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID of the KB document to delete"},
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "Set to true to proceed with deleting an auto-generated document after "
                        "the user has explicitly confirmed. Default false."
                    ),
                },
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "add_kb_fragment",
        "description": (
            "Legacy alias of create_kb_document with tighter length limits — title (1-200 "
            "chars) and content (10-10,000 chars). Same content-hash idempotency and embedding "
            "generation as create_kb_document. Only for OWNER and IT roles. Prefer "
            "create_kb_document for new integrations; this exists for backward compatibility."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Fragment title, 1-200 chars"},
                "content": {"type": "string", "description": "Fragment content, 10-10,000 chars"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "delete_kb_fragment",
        "description": (
            "Legacy alias of delete_kb_document — deletes a Knowledge Base document (fragment) "
            "and its chunks immediately, with NO confirmation step, even if the document is "
            "auto-generated from onboarding. Unlike delete_kb_document, this always deletes "
            "right away. Only for OWNER and IT roles. Prefer delete_kb_document for new "
            "integrations, since it protects auto-generated documents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "format": "uuid", "description": "UUID of the KB document/fragment to delete"},
            },
            "required": ["document_id"],
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
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}
        scope = str(args.get("scope", "tenant"))
        result = (
            await get_user_profitability(tenant, user.id, year, month, db)
            if scope == "user"
            else await get_tenant_profitability(tenant, year, month, db)
        )
        return _jsonable(result)

    if name == "get_run_rate":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}
        scope = str(args.get("scope", "tenant"))
        result = (
            await get_user_run_rate(tenant, user.id, year, month, db)
            if scope == "user"
            else await get_tenant_run_rate(tenant, year, month, db)
        )
        return _jsonable(result)

    if name == "get_expenses_summary":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}
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

    if name == "list_expenses":
        branch_id_raw = args.get("branch_id")
        try:
            branch_id = uuid.UUID(str(branch_id_raw)) if branch_id_raw else None
        except (ValueError, AttributeError):
            return {"error": "branch_id inválido"}

        allowed, reason = await require_finance_access(user, branch_id, db)
        if not allowed:
            return {"error": reason}

        category_id_raw = args.get("category_id")
        try:
            category_id = uuid.UUID(str(category_id_raw)) if category_id_raw else None
        except (ValueError, AttributeError):
            return {"error": "category_id inválido"}

        month_filter_raw = args.get("month")
        month_filter = None
        if month_filter_raw:
            try:
                month_filter = date.fromisoformat(str(month_filter_raw))
            except ValueError:
                return {"error": "month inválido, use formato YYYY-MM-DD"}

        kind_filter = args.get("kind")
        status_filter = args.get("status")

        q = select(Expense).where(Expense.tenant_id == user.tenant_id)
        if branch_id is not None:
            q = q.where(Expense.branch_id == branch_id)
        if month_filter is not None:
            first_day = month_filter.replace(day=1)
            last_day = month_filter.replace(day=monthrange(month_filter.year, month_filter.month)[1])
            q = q.where(Expense.incurred_at.between(first_day, last_day))
        if kind_filter is not None:
            q = q.where(Expense.kind == kind_filter)
        if category_id is not None:
            q = q.where(Expense.category_id == category_id)
        if status_filter is not None:
            q = q.where(Expense.status == status_filter)
        q = q.order_by(Expense.incurred_at.desc())
        rows = (await db.execute(q)).scalars().all()
        return _jsonable([
            {
                "id": r.id, "tenant_id": r.tenant_id, "branch_id": r.branch_id,
                "category_id": r.category_id, "owner_id": r.owner_id, "amount": r.amount,
                "kind": r.kind, "currency": r.currency, "incurred_at": r.incurred_at,
                "status": r.status, "source": r.source, "deal_id": r.deal_id,
                "rule_id": r.rule_id, "recurring_id": r.recurring_id,
                "receipt_url": r.receipt_url, "description": r.description,
            }
            for r in rows
        ])

    if name == "list_expense_categories":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}
        include_inactive = bool(args.get("include_inactive", False))
        q = select(ExpenseCategory).where(ExpenseCategory.tenant_id == user.tenant_id)
        if not include_inactive:
            q = q.where(ExpenseCategory.is_active.is_(True))
        q = q.order_by(ExpenseCategory.kind, ExpenseCategory.name)
        rows = (await db.execute(q)).scalars().all()
        return _jsonable([
            {
                "id": r.id, "tenant_id": r.tenant_id, "name": r.name,
                "kind": r.kind, "icon": r.icon, "is_active": r.is_active,
            }
            for r in rows
        ])

    if name == "list_recurring_expenses":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}
        include_inactive = bool(args.get("include_inactive", False))
        q = select(RecurringExpense).where(RecurringExpense.tenant_id == user.tenant_id)
        if not include_inactive:
            q = q.where(RecurringExpense.is_active.is_(True))
        rows = (await db.execute(q)).scalars().all()
        return _jsonable([
            {
                "id": r.id, "tenant_id": r.tenant_id, "category_id": r.category_id,
                "amount": r.amount, "day_of_month": r.day_of_month,
                "description": r.description, "is_active": r.is_active,
            }
            for r in rows
        ])

    if name == "list_expense_rules":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}
        include_inactive = bool(args.get("include_inactive", False))
        q = select(ExpenseRule).where(ExpenseRule.tenant_id == user.tenant_id)
        if not include_inactive:
            q = q.where(ExpenseRule.is_active.is_(True))
        rows = (await db.execute(q)).scalars().all()
        return _jsonable([
            {
                "id": r.id, "tenant_id": r.tenant_id, "category_id": r.category_id,
                "name": r.name, "rule_type": r.rule_type, "value": r.value,
                "deal_type_filter": r.deal_type_filter, "auto_confirm": r.auto_confirm,
                "is_active": r.is_active,
            }
            for r in rows
        ])

    if name == "list_product_categories":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}
        include_inactive = bool(args.get("include_inactive", False))
        q = select(ProductCategory).where(ProductCategory.tenant_id == user.tenant_id)
        if not include_inactive:
            q = q.where(ProductCategory.is_active.is_(True))
        q = q.order_by(ProductCategory.position, ProductCategory.name)
        rows = (await db.execute(q)).scalars().all()
        return _jsonable([
            {
                "id": r.id, "tenant_id": r.tenant_id, "name": r.name,
                "is_active": r.is_active, "position": r.position,
            }
            for r in rows
        ])

    if name == "list_goal_assignments":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        try:
            goal_id = uuid.UUID(str(args.get("goal_id", "")))
        except (ValueError, AttributeError):
            return {"error": "goal_id inválido"}

        goal = (
            await db.execute(
                select(MonthlyGoal).where(
                    MonthlyGoal.id == goal_id,
                    MonthlyGoal.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if goal is None:
            return {"error": "Meta mensual no encontrada"}

        rows = (
            await db.execute(
                select(MonthlyGoalAssignment, User)
                .join(User, User.id == MonthlyGoalAssignment.user_id)
                .where(MonthlyGoalAssignment.goal_id == goal_id)
                .order_by(MonthlyGoalAssignment.share_percent.desc())
            )
        ).all()
        return _jsonable([
            {
                "id": a.id, "goal_id": a.goal_id, "tenant_id": a.tenant_id,
                "user_id": a.user_id, "share_percent": a.share_percent,
                "amount": a.amount, "user_name": u.name, "user_email": u.email,
            }
            for a, u in rows
        ])

    if name == "list_finance_permissions":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["list_finance_permissions"])
        if not allowed:
            return {"error": "Solo el propietario puede ver los permisos de finanzas"}

        rows = (
            await db.execute(
                select(FinancePermission, User)
                .join(User, User.id == FinancePermission.user_id)
                .where(FinancePermission.tenant_id == user.tenant_id)
                .order_by(FinancePermission.created_at)
            )
        ).all()
        return _jsonable([
            {
                "id": fp.id, "tenant_id": fp.tenant_id, "branch_id": fp.branch_id,
                "user_id": fp.user_id, "granted_by": fp.granted_by,
                "user_name": u.name, "user_email": u.email,
            }
            for fp, u in rows
        ])

    # Expansión Finanzas/Gastos, Ronda 2a-i — núcleo de gastos (escritura).
    # create_expense/update_expense/confirm_expense/confirm_all_draft_expenses
    # replican exactamente la lógica de sus endpoints REST equivalentes en
    # app/api/finance.py (create_expense, update_expense, confirm_expense,
    # confirm_all_draft_expenses) y validan acceso vía require_finance_access
    # dentro del dispatcher — mismo patrón que list_expenses/etc (Ronda 1).
    # update_expense/confirm_expense usan el branch_id DEL GASTO YA EXISTENTE
    # para el chequeo de acceso, no el que venga en args — así lo hace el REST.
    if name == "create_expense":
        branch_id_raw = args.get("branch_id")
        try:
            branch_id = uuid.UUID(str(branch_id_raw)) if branch_id_raw else None
        except (ValueError, AttributeError):
            return {"error": "branch_id inválido"}

        category_id_raw = args.get("category_id")
        try:
            category_id = uuid.UUID(str(category_id_raw)) if category_id_raw else None
        except (ValueError, AttributeError):
            return {"error": "category_id inválido"}

        deal_id_raw = args.get("deal_id")
        try:
            deal_id = uuid.UUID(str(deal_id_raw)) if deal_id_raw else None
        except (ValueError, AttributeError):
            return {"error": "deal_id inválido"}

        allowed, reason = await require_finance_access(user, branch_id, db)
        if not allowed:
            return {"error": reason}

        amount_raw = args.get("amount")
        if amount_raw is None:
            return {"error": "El monto (amount) es requerido"}
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError
        except (ValueError, Exception):
            return {"error": f"Monto inválido: {amount_raw}"}

        kind = args.get("kind")
        if kind not in ("fijo", "variable"):
            return {"error": "kind debe ser 'fijo' o 'variable'"}

        incurred_at_raw = args.get("incurred_at")
        if incurred_at_raw:
            try:
                incurred_at = date.fromisoformat(str(incurred_at_raw))
            except ValueError:
                return {"error": "incurred_at inválido, use formato YYYY-MM-DD"}
        else:
            incurred_at = date.today()

        exp = Expense(
            tenant_id=user.tenant_id,
            branch_id=branch_id,
            category_id=category_id,
            owner_id=user.id,
            amount=amount,
            kind=kind,
            currency=str(args.get("currency") or "MXN"),
            incurred_at=incurred_at,
            status="confirmed",
            source="manual",
            deal_id=deal_id,
            receipt_url=args.get("receipt_url"),
            description=args.get("description"),
        )
        db.add(exp)
        await db.commit()
        await db.refresh(exp)
        return _jsonable({
            "id": exp.id, "tenant_id": exp.tenant_id, "branch_id": exp.branch_id,
            "category_id": exp.category_id, "owner_id": exp.owner_id, "amount": exp.amount,
            "kind": exp.kind, "currency": exp.currency, "incurred_at": exp.incurred_at,
            "status": exp.status, "source": exp.source, "deal_id": exp.deal_id,
            "rule_id": exp.rule_id, "recurring_id": exp.recurring_id,
            "receipt_url": exp.receipt_url, "description": exp.description,
        })

    if name == "update_expense":
        try:
            expense_id = uuid.UUID(str(args.get("expense_id", "")))
        except (ValueError, AttributeError):
            return {"error": "expense_id inválido"}

        exp = (
            await db.execute(
                select(Expense).where(Expense.id == expense_id, Expense.tenant_id == user.tenant_id)
            )
        ).scalar_one_or_none()
        if exp is None:
            return {"error": "Gasto no encontrado"}

        allowed, reason = await require_finance_access(user, exp.branch_id, db)
        if not allowed:
            return {"error": reason}

        if "branch_id" in args and args["branch_id"] is not None:
            try:
                exp.branch_id = uuid.UUID(str(args["branch_id"]))
            except (ValueError, AttributeError):
                return {"error": "branch_id inválido"}
        if "category_id" in args and args["category_id"] is not None:
            try:
                exp.category_id = uuid.UUID(str(args["category_id"]))
            except (ValueError, AttributeError):
                return {"error": "category_id inválido"}
        if "amount" in args and args["amount"] is not None:
            try:
                new_amount = Decimal(str(args["amount"]))
                if new_amount <= 0:
                    raise ValueError
            except (ValueError, Exception):
                return {"error": f"Monto inválido: {args['amount']}"}
            exp.amount = new_amount
        if "kind" in args and args["kind"] is not None:
            if args["kind"] not in ("fijo", "variable"):
                return {"error": "kind debe ser 'fijo' o 'variable'"}
            exp.kind = args["kind"]
        if "currency" in args and args["currency"] is not None:
            exp.currency = str(args["currency"])
        if "incurred_at" in args and args["incurred_at"] is not None:
            try:
                exp.incurred_at = date.fromisoformat(str(args["incurred_at"]))
            except ValueError:
                return {"error": "incurred_at inválido, use formato YYYY-MM-DD"}
        if "status" in args and args["status"] is not None:
            if args["status"] not in ("draft", "confirmed"):
                return {"error": "status debe ser 'draft' o 'confirmed'"}
            exp.status = args["status"]
        if "deal_id" in args and args["deal_id"] is not None:
            try:
                exp.deal_id = uuid.UUID(str(args["deal_id"]))
            except (ValueError, AttributeError):
                return {"error": "deal_id inválido"}
        if "receipt_url" in args and args["receipt_url"] is not None:
            exp.receipt_url = args["receipt_url"]
        if "description" in args and args["description"] is not None:
            exp.description = args["description"]

        await db.commit()
        await db.refresh(exp)
        return _jsonable({
            "id": exp.id, "tenant_id": exp.tenant_id, "branch_id": exp.branch_id,
            "category_id": exp.category_id, "owner_id": exp.owner_id, "amount": exp.amount,
            "kind": exp.kind, "currency": exp.currency, "incurred_at": exp.incurred_at,
            "status": exp.status, "source": exp.source, "deal_id": exp.deal_id,
            "rule_id": exp.rule_id, "recurring_id": exp.recurring_id,
            "receipt_url": exp.receipt_url, "description": exp.description,
        })

    if name == "confirm_expense":
        try:
            expense_id = uuid.UUID(str(args.get("expense_id", "")))
        except (ValueError, AttributeError):
            return {"error": "expense_id inválido"}

        exp = (
            await db.execute(
                select(Expense).where(Expense.id == expense_id, Expense.tenant_id == user.tenant_id)
            )
        ).scalar_one_or_none()
        if exp is None:
            return {"error": "Gasto no encontrado"}

        allowed, reason = await require_finance_access(user, exp.branch_id, db)
        if not allowed:
            return {"error": reason}

        exp.status = "confirmed"
        if args.get("amount") is not None:
            try:
                new_amount = Decimal(str(args["amount"]))
                if new_amount <= 0:
                    raise ValueError
            except (ValueError, Exception):
                return {"error": f"Monto inválido: {args['amount']}"}
            exp.amount = new_amount

        await db.commit()
        await db.refresh(exp)
        return _jsonable({
            "id": exp.id, "tenant_id": exp.tenant_id, "branch_id": exp.branch_id,
            "category_id": exp.category_id, "owner_id": exp.owner_id, "amount": exp.amount,
            "kind": exp.kind, "currency": exp.currency, "incurred_at": exp.incurred_at,
            "status": exp.status, "source": exp.source, "deal_id": exp.deal_id,
            "rule_id": exp.rule_id, "recurring_id": exp.recurring_id,
            "receipt_url": exp.receipt_url, "description": exp.description,
        })

    if name == "confirm_all_draft_expenses":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        result = await db.execute(
            update(Expense)
            .where(Expense.tenant_id == user.tenant_id, Expense.status == "draft")
            .values(status="confirmed")
        )
        await db.commit()
        return {"updated": result.rowcount}

    if name == "trigger_recurring_expense_generation":
        # required_role=_OWNER_TIER en el catálogo (app/copilot/actions_catalog.py)
        # es solo metadata declarativa — execute_tool no la aplica automáticamente
        # (ningún caller de execute_tool en copilot_engine.py/capability_runner.py
        # chequea required_role antes de despachar). El chequeo real vive acá,
        # mismo patrón que list_finance_permissions/get_team_performance arriba.
        # NO se llama require_finance_access — el endpoint REST real
        # (app/api/finance.py::trigger_recurring_expense_generation) usa
        # _require_owner, no _require_finance_access, y esto lo replica tal cual.
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["trigger_recurring_expense_generation"])
        if not allowed:
            return {"error": "Solo el propietario puede generar los gastos recurrentes"}

        generated = await generate_recurring_expenses(user.tenant_id, db)
        return {"generated": generated}

    # Expansión Finanzas/Gastos, Ronda 2a-ii — catálogos de finanzas
    # (escritura). Las 8 acciones de abajo replican sus endpoints REST
    # equivalentes en app/api/finance.py (expense-categories,
    # recurring-expenses, expense-rules) y app/api/goals.py
    # (product-categories) — todas tenant-wide (branch_id=None en
    # require_finance_access), igual que sus 4 hermanas de lectura de la
    # Ronda 1 (list_expense_categories/list_recurring_expenses/
    # list_expense_rules/list_product_categories).
    if name == "create_expense_category":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        cat_name = args.get("name")
        if not cat_name or not str(cat_name).strip():
            return {"error": "El nombre (name) es requerido"}

        kind = args.get("kind")
        if kind not in ("fijo", "variable"):
            return {"error": "kind debe ser 'fijo' o 'variable'"}

        cat = ExpenseCategory(
            tenant_id=user.tenant_id,
            name=str(cat_name).strip(),
            kind=kind,
            icon=args.get("icon"),
        )
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        return _jsonable({
            "id": cat.id, "tenant_id": cat.tenant_id, "name": cat.name,
            "kind": cat.kind, "icon": cat.icon, "is_active": cat.is_active,
        })

    if name == "update_expense_category":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        try:
            category_id = uuid.UUID(str(args.get("category_id", "")))
        except (ValueError, AttributeError):
            return {"error": "category_id inválido"}

        cat = (
            await db.execute(
                select(ExpenseCategory).where(
                    ExpenseCategory.id == category_id, ExpenseCategory.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if cat is None:
            return {"error": "Categoría no encontrada"}

        if "name" in args and args["name"] is not None:
            if not str(args["name"]).strip():
                return {"error": "El nombre (name) no puede estar vacío"}
            cat.name = str(args["name"]).strip()
        if "kind" in args and args["kind"] is not None:
            if args["kind"] not in ("fijo", "variable"):
                return {"error": "kind debe ser 'fijo' o 'variable'"}
            cat.kind = args["kind"]
        if "icon" in args and args["icon"] is not None:
            cat.icon = args["icon"]
        if "is_active" in args and args["is_active"] is not None:
            cat.is_active = bool(args["is_active"])

        await db.commit()
        await db.refresh(cat)
        return _jsonable({
            "id": cat.id, "tenant_id": cat.tenant_id, "name": cat.name,
            "kind": cat.kind, "icon": cat.icon, "is_active": cat.is_active,
        })

    if name == "create_recurring_expense":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        category_id_raw = args.get("category_id")
        try:
            category_id = uuid.UUID(str(category_id_raw)) if category_id_raw else None
        except (ValueError, AttributeError):
            return {"error": "category_id inválido"}

        amount_raw = args.get("amount")
        if amount_raw is None:
            return {"error": "El monto (amount) es requerido"}
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError
        except (ValueError, Exception):
            return {"error": f"Monto inválido: {amount_raw}"}

        day_of_month_raw = args.get("day_of_month", 1)
        try:
            day_of_month = int(day_of_month_raw)
        except (ValueError, TypeError):
            return {"error": f"day_of_month inválido: {day_of_month_raw}"}
        if not (1 <= day_of_month <= 28):
            return {"error": "day_of_month debe estar entre 1 y 28"}

        rec = RecurringExpense(
            tenant_id=user.tenant_id,
            category_id=category_id,
            amount=amount,
            day_of_month=day_of_month,
            description=args.get("description"),
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        return _jsonable({
            "id": rec.id, "tenant_id": rec.tenant_id, "category_id": rec.category_id,
            "amount": rec.amount, "day_of_month": rec.day_of_month,
            "description": rec.description, "is_active": rec.is_active,
        })

    if name == "update_recurring_expense":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        try:
            recurring_id = uuid.UUID(str(args.get("recurring_id", "")))
        except (ValueError, AttributeError):
            return {"error": "recurring_id inválido"}

        rec = (
            await db.execute(
                select(RecurringExpense).where(
                    RecurringExpense.id == recurring_id, RecurringExpense.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if rec is None:
            return {"error": "Gasto recurrente no encontrado"}

        if "category_id" in args and args["category_id"] is not None:
            try:
                rec.category_id = uuid.UUID(str(args["category_id"]))
            except (ValueError, AttributeError):
                return {"error": "category_id inválido"}
        if "amount" in args and args["amount"] is not None:
            try:
                new_amount = Decimal(str(args["amount"]))
                if new_amount <= 0:
                    raise ValueError
            except (ValueError, Exception):
                return {"error": f"Monto inválido: {args['amount']}"}
            rec.amount = new_amount
        if "day_of_month" in args and args["day_of_month"] is not None:
            try:
                new_day = int(args["day_of_month"])
            except (ValueError, TypeError):
                return {"error": f"day_of_month inválido: {args['day_of_month']}"}
            if not (1 <= new_day <= 28):
                return {"error": "day_of_month debe estar entre 1 y 28"}
            rec.day_of_month = new_day
        if "description" in args and args["description"] is not None:
            rec.description = args["description"]
        if "is_active" in args and args["is_active"] is not None:
            rec.is_active = bool(args["is_active"])

        await db.commit()
        await db.refresh(rec)
        return _jsonable({
            "id": rec.id, "tenant_id": rec.tenant_id, "category_id": rec.category_id,
            "amount": rec.amount, "day_of_month": rec.day_of_month,
            "description": rec.description, "is_active": rec.is_active,
        })

    if name == "create_expense_rule":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        category_id_raw = args.get("category_id")
        try:
            category_id = uuid.UUID(str(category_id_raw)) if category_id_raw else None
        except (ValueError, AttributeError):
            return {"error": "category_id inválido"}

        rule_name = args.get("name")
        if not rule_name or not str(rule_name).strip():
            return {"error": "El nombre (name) es requerido"}

        rule_type = args.get("rule_type")
        if rule_type not in ("percent_of_deal", "fixed_per_deal", "percent_of_cost"):
            return {"error": "rule_type debe ser 'percent_of_deal', 'fixed_per_deal' o 'percent_of_cost'"}

        value_raw = args.get("value")
        if value_raw is None:
            return {"error": "El valor (value) es requerido"}
        try:
            value = Decimal(str(value_raw))
            if value <= 0:
                raise ValueError
        except (ValueError, Exception):
            return {"error": f"Valor inválido: {value_raw}"}

        rule = ExpenseRule(
            tenant_id=user.tenant_id,
            category_id=category_id,
            name=str(rule_name).strip(),
            rule_type=rule_type,
            value=value,
            deal_type_filter=args.get("deal_type_filter"),
            auto_confirm=bool(args.get("auto_confirm", False)),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return _jsonable({
            "id": rule.id, "tenant_id": rule.tenant_id, "category_id": rule.category_id,
            "name": rule.name, "rule_type": rule.rule_type, "value": rule.value,
            "deal_type_filter": rule.deal_type_filter, "auto_confirm": rule.auto_confirm,
            "is_active": rule.is_active,
        })

    if name == "update_expense_rule":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        try:
            rule_id = uuid.UUID(str(args.get("rule_id", "")))
        except (ValueError, AttributeError):
            return {"error": "rule_id inválido"}

        rule = (
            await db.execute(
                select(ExpenseRule).where(ExpenseRule.id == rule_id, ExpenseRule.tenant_id == user.tenant_id)
            )
        ).scalar_one_or_none()
        if rule is None:
            return {"error": "Regla de gasto no encontrada"}

        if "category_id" in args and args["category_id"] is not None:
            try:
                rule.category_id = uuid.UUID(str(args["category_id"]))
            except (ValueError, AttributeError):
                return {"error": "category_id inválido"}
        if "name" in args and args["name"] is not None:
            if not str(args["name"]).strip():
                return {"error": "El nombre (name) no puede estar vacío"}
            rule.name = str(args["name"]).strip()
        if "rule_type" in args and args["rule_type"] is not None:
            if args["rule_type"] not in ("percent_of_deal", "fixed_per_deal", "percent_of_cost"):
                return {"error": "rule_type debe ser 'percent_of_deal', 'fixed_per_deal' o 'percent_of_cost'"}
            rule.rule_type = args["rule_type"]
        if "value" in args and args["value"] is not None:
            try:
                new_value = Decimal(str(args["value"]))
                if new_value <= 0:
                    raise ValueError
            except (ValueError, Exception):
                return {"error": f"Valor inválido: {args['value']}"}
            rule.value = new_value
        # deal_type_filter: mismo comportamiento que el REST
        # (update_expense_rule, app/api/finance.py) — nunca se puede limpiar
        # a None una vez seteado vía este endpoint, es una limitación
        # existente del REST, no un bug a corregir acá.
        if "deal_type_filter" in args and args["deal_type_filter"] is not None:
            rule.deal_type_filter = args["deal_type_filter"]
        if "auto_confirm" in args and args["auto_confirm"] is not None:
            rule.auto_confirm = bool(args["auto_confirm"])
        if "is_active" in args and args["is_active"] is not None:
            rule.is_active = bool(args["is_active"])

        await db.commit()
        await db.refresh(rule)
        return _jsonable({
            "id": rule.id, "tenant_id": rule.tenant_id, "category_id": rule.category_id,
            "name": rule.name, "rule_type": rule.rule_type, "value": rule.value,
            "deal_type_filter": rule.deal_type_filter, "auto_confirm": rule.auto_confirm,
            "is_active": rule.is_active,
        })

    if name == "create_product_category":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        cat_name = args.get("name")
        if not cat_name or not str(cat_name).strip():
            return {"error": "El nombre (name) es requerido"}

        position_raw = args.get("position", 0)
        try:
            position = int(position_raw)
        except (ValueError, TypeError):
            return {"error": f"position inválido: {position_raw}"}

        cat = ProductCategory(
            tenant_id=user.tenant_id,
            name=str(cat_name).strip(),
            position=position,
        )
        db.add(cat)
        # ProductCategory tiene un unique constraint (tenant_id, name) —
        # mismo manejo que goals.py::create_product_category: rollback
        # explícito tras el IntegrityError, si no la sesión queda inutilizable
        # para el resto del request.
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return {"error": f"Ya existe una categoría de producto con el nombre '{cat_name}' en tu cuenta"}
        await db.refresh(cat)
        return _jsonable({
            "id": cat.id, "tenant_id": cat.tenant_id, "name": cat.name,
            "is_active": cat.is_active, "position": cat.position,
        })

    if name == "update_product_category":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        try:
            category_id = uuid.UUID(str(args.get("category_id", "")))
        except (ValueError, AttributeError):
            return {"error": "category_id inválido"}

        cat = (
            await db.execute(
                select(ProductCategory).where(
                    ProductCategory.id == category_id, ProductCategory.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if cat is None:
            return {"error": "Categoría de producto no encontrada"}

        if "name" in args and args["name"] is not None:
            if not str(args["name"]).strip():
                return {"error": "El nombre (name) no puede estar vacío"}
            cat.name = str(args["name"]).strip()
        if "is_active" in args and args["is_active"] is not None:
            cat.is_active = bool(args["is_active"])
        if "position" in args and args["position"] is not None:
            try:
                cat.position = int(args["position"])
            except (ValueError, TypeError):
                return {"error": f"position inválido: {args['position']}"}

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return {"error": f"Ya existe una categoría de producto con el nombre '{args.get('name')}' en tu cuenta"}
        await db.refresh(cat)
        return _jsonable({
            "id": cat.id, "tenant_id": cat.tenant_id, "name": cat.name,
            "is_active": cat.is_active, "position": cat.position,
        })

    if name == "get_monthly_goal":
        goal = await get_current_month_goal(user.tenant_id, year, month, db)
        if goal is None:
            return {"year": year, "month": month, "goal_set": False, "amount_mxn": None}
        return {"year": year, "month": month, "goal_set": True, "amount_mxn": float(goal.amount), "is_draft": goal.is_draft}

    if name == "get_team_performance":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["get_team_performance"])
        if not allowed:
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
        # Sin normalizar antes, esto guardaba el teléfono tal cual lo haya
        # pasado el modelo/usuario (cualquier formato) — no hacía match
        # contra leads ya creados vía WhatsApp inbound con el mismo número
        # real en formato canónico. Hallazgo de leads duplicados, 2026-08-25
        # — ver app.services.whatsapp.normalize_mx_phone.
        wa_phone = normalize_mx_phone(str(args.get("wa_phone", "")).strip() or None)
        if not contact_name and not wa_phone:
            return {"error": "Se requiere al menos el nombre o el teléfono del contacto"}
        if not user.branch_id:
            return {"error": "El usuario no tiene sucursal asignada — no se puede crear el contacto"}

        if wa_phone:
            existing = await find_lead_by_phone(db, wa_phone, user.branch_id, user.tenant_id)
            if existing is not None:
                return {
                    "error": (
                        f"Ya existe un contacto con este teléfono: "
                        f"{existing.name or existing.wa_phone} (id={existing.id})"
                    ),
                }

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
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

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

        try:
            goal, action = await upsert_monthly_goal(
                db,
                tenant_id=user.tenant_id,
                year=goal_year,
                month=goal_month,
                amount=amount,
                user_id=user.id,
            )
        except ValueError as exc:
            return {"error": str(exc)}

        return {
            "set": True,
            "goal_id": str(goal.id),
            "amount_mxn": float(amount),
            "year": goal_year,
            "month": goal_month,
            "action": action,
        }

    if name == "update_monthly_goal":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        try:
            goal_id = uuid.UUID(str(args.get("goal_id", "")))
        except (ValueError, AttributeError):
            return {"error": "goal_id inválido"}

        goal = (
            await db.execute(
                select(MonthlyGoal).where(
                    MonthlyGoal.id == goal_id,
                    MonthlyGoal.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if goal is None:
            return {"error": "Meta mensual no encontrada"}

        if _is_past_period(goal.period_year, goal.period_month):
            return {
                "error": (
                    f"No se puede editar una meta de un periodo pasado "
                    f"({goal.period_year}/{goal.period_month:02d})"
                )
            }

        before = _goal_as_dict(goal)
        if "amount" in args and args["amount"] is not None:
            try:
                new_amount = Decimal(str(args["amount"]))
                if new_amount < 0:
                    raise ValueError
            except (ValueError, Exception):
                return {"error": f"Monto inválido: {args['amount']}"}
            goal.amount = new_amount
        if "currency" in args and args["currency"] is not None:
            goal.currency = str(args["currency"])
        # notes: mismo comportamiento que el REST (update_monthly_goal,
        # app/api/goals.py) — nunca se puede limpiar a None una vez seteado
        # vía este endpoint, es una limitación existente del REST, no un bug
        # a corregir acá (mismo patrón que deal_type_filter en
        # update_expense_rule).
        if "notes" in args and args["notes"] is not None:
            goal.notes = str(args["notes"])
        if "is_draft" in args and args["is_draft"] is not None:
            goal.is_draft = bool(args["is_draft"])

        await db.flush()
        after = _goal_as_dict(goal)
        db.add(MonthlyGoalHistory(
            tenant_id=user.tenant_id,
            goal_id=goal.id,
            action="goal_updated",
            before_data=before,
            after_data=after,
            changed_by=user.id,
        ))
        await db.commit()
        await db.refresh(goal)
        return _jsonable({
            "id": goal.id, "tenant_id": goal.tenant_id, "period_year": goal.period_year,
            "period_month": goal.period_month, "amount": goal.amount, "currency": goal.currency,
            "dimension": goal.dimension, "dimension_value_text": goal.dimension_value_text,
            "dimension_value_uuid": goal.dimension_value_uuid, "notes": goal.notes,
            "is_draft": goal.is_draft,
        })

    if name == "set_goal_assignments":
        allowed, reason = await require_finance_access(user, None, db)
        if not allowed:
            return {"error": reason}

        try:
            goal_id = uuid.UUID(str(args.get("goal_id", "")))
        except (ValueError, AttributeError):
            return {"error": "goal_id inválido"}

        goal = (
            await db.execute(
                select(MonthlyGoal).where(
                    MonthlyGoal.id == goal_id,
                    MonthlyGoal.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if goal is None:
            return {"error": "Meta mensual no encontrada"}

        assignments_raw = args.get("assignments")
        if not isinstance(assignments_raw, list):
            return {"error": "El campo assignments es requerido y debe ser una lista"}

        parsed: list[tuple[uuid.UUID, Decimal]] = []
        for item in assignments_raw:
            if not isinstance(item, dict):
                return {"error": f"Elemento de assignments inválido: {item}"}
            try:
                item_user_id = uuid.UUID(str(item.get("user_id", "")))
            except (ValueError, AttributeError):
                return {"error": f"user_id inválido: {item.get('user_id')}"}
            try:
                share_percent = Decimal(str(item.get("share_percent")))
                if share_percent < 0 or share_percent > 100:
                    raise ValueError
            except (ValueError, Exception):
                return {"error": f"share_percent inválido: {item.get('share_percent')}"}
            parsed.append((item_user_id, share_percent))

        # (1) validar que todos los user_id pertenezcan al tenant actual
        user_ids = [uid for uid, _ in parsed]
        users_map: dict[uuid.UUID, User] = {}
        if user_ids:
            user_rows = (
                await db.execute(
                    select(User).where(
                        User.id.in_(user_ids),
                        User.tenant_id == user.tenant_id,
                    )
                )
            ).scalars().all()
            users_map = {u.id: u for u in user_rows}
            missing = [str(uid) for uid in user_ids if uid not in users_map]
            if missing:
                return {"error": f"Usuario(s) no encontrado(s) en este tenant: {missing}"}

        # (2) suma == 100 requerida para metas no-borrador con lista no vacía
        if parsed and not goal.is_draft:
            total = sum(share for _, share in parsed)
            if abs(total - Decimal("100")) >= Decimal("0.01"):
                return {
                    "error": (
                        f"La suma de porcentajes debe ser 100% (actual: {total:.2f}%). "
                        "Marca la meta como borrador para guardar parcialmente."
                    )
                }

        # (3) patrón delete-then-insert, capturando estado before/after
        before_rows = (
            await db.execute(
                select(MonthlyGoalAssignment).where(MonthlyGoalAssignment.goal_id == goal_id)
            )
        ).scalars().all()
        before_data = _jsonable([
            {"user_id": r.user_id, "share_percent": r.share_percent, "amount": r.amount}
            for r in before_rows
        ])

        await db.execute(delete(MonthlyGoalAssignment).where(MonthlyGoalAssignment.goal_id == goal_id))

        new_assignments: list[MonthlyGoalAssignment] = []
        for item_user_id, share_percent in parsed:
            calc_amount = (goal.amount * share_percent / Decimal("100")).quantize(Decimal("0.01"))
            a = MonthlyGoalAssignment(
                goal_id=goal_id,
                tenant_id=user.tenant_id,
                user_id=item_user_id,
                share_percent=share_percent,
                amount=calc_amount,
            )
            db.add(a)
            new_assignments.append(a)

        await db.flush()
        after_data = _jsonable([
            {"user_id": a.user_id, "share_percent": a.share_percent, "amount": a.amount}
            for a in new_assignments
        ])

        # (4) una sola entrada de historial para todo el cambio en bloque
        db.add(MonthlyGoalHistory(
            tenant_id=user.tenant_id,
            goal_id=goal_id,
            action="assignment_changed",
            before_data=before_data,
            after_data=after_data,
            changed_by=user.id,
        ))
        await db.commit()

        result_rows = (
            await db.execute(
                select(MonthlyGoalAssignment, User)
                .join(User, User.id == MonthlyGoalAssignment.user_id)
                .where(MonthlyGoalAssignment.goal_id == goal_id)
                .order_by(MonthlyGoalAssignment.share_percent.desc())
            )
        ).all()
        return _jsonable([
            {
                "id": a.id, "goal_id": a.goal_id, "tenant_id": a.tenant_id,
                "user_id": a.user_id, "share_percent": a.share_percent,
                "amount": a.amount, "user_name": u.name, "user_email": u.email,
            }
            for a, u in result_rows
        ])

    if name == "dismiss_suggestion":
        try:
            suggestion_id = uuid.UUID(str(args.get("suggestion_id", "")))
        except (ValueError, AttributeError):
            return {"error": "suggestion_id inválido"}

        # Ownership real (mismo patrón que agents.py::list_suggestions,
        # líneas 82-86) — a propósito NO se usa el helper
        # agents.py::_get_suggestion_for_user, que solo valida tenant_id y
        # no target_user_id/target_role (ver hallazgo #7 de
        # docs/PERMISSIONS_DRIFT_BACKLOG.md). Código nuevo, construido bien
        # desde el inicio en vez de heredar ese gap.
        suggestion = (
            await db.execute(
                select(AgentSuggestion).where(
                    AgentSuggestion.id == suggestion_id,
                    AgentSuggestion.tenant_id == user.tenant_id,
                    or_(
                        AgentSuggestion.target_user_id == user.id,
                        (AgentSuggestion.target_user_id.is_(None))
                        & (AgentSuggestion.target_role == user.role.value),
                    ),
                )
            )
        ).scalar_one_or_none()
        if suggestion is None:
            return {"error": "Sugerencia no encontrada o no dirigida a este usuario"}

        if suggestion.status not in ("suggested", "accepted"):
            return {"error": f"La sugerencia ya está en estado '{suggestion.status}'"}

        suggestion.status = "dismissed"
        suggestion.responded_at = datetime.now(timezone.utc)
        reason = args.get("reason")
        if reason:
            suggestion.execution_result = {"dismissed_reason": str(reason)}

        await db.commit()

        return {
            "dismissed": True,
            "suggestion_id": str(suggestion_id),
            "reason": str(reason) if reason else None,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # KNOWLEDGE BASE (app/api/kb.py) — primer módulo huérfano fuera de
    # Finanzas/Gastos. NO usa require_finance_access — control de acceso por
    # rol vía check_permission + ActionDefinition.required_role, mismo patrón
    # que list_finance_permissions/get_team_performance/
    # trigger_recurring_expense_generation (required_role del catálogo es
    # metadata declarativa, el enforcement real es esta llamada explícita).
    # ─────────────────────────────────────────────────────────────────────────

    if name == "reindex_kb":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["reindex_kb"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        task = asyncio.create_task(
            ingest_all_documents(tenant_id=user.tenant_id, branch_id=user.branch_id)
        )
        _kb_background_tasks.add(task)
        task.add_done_callback(_kb_background_tasks.discard)
        return {"message": "Re-indexación iniciada en background", "status": "processing"}

    if name == "kb_status":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["kb_status"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        rows = (
            await db.execute(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.tenant_id == user.tenant_id)
                .order_by(KnowledgeDocument.filename)
            )
        ).scalars().all()
        documents = [
            {
                "id": d.id, "filename": d.filename, "title": d.title,
                "chunk_count": d.chunk_count, "indexed_at": d.indexed_at,
            }
            for d in rows
        ]
        total_chunks = sum(d["chunk_count"] for d in documents)
        last_indexed = max((d["indexed_at"] for d in documents if d["indexed_at"]), default=None)
        return _jsonable({
            "documents": documents,
            "total_documents": len(documents),
            "total_chunks": total_chunks,
            "last_indexed": last_indexed,
        })

    if name == "list_kb_documents":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["list_kb_documents"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        try:
            page = int(args.get("page") or 1)
        except (ValueError, TypeError):
            page = 1
        try:
            limit = int(args.get("limit") or 20)
        except (ValueError, TypeError):
            limit = 20
        page = max(page, 1)
        limit = min(max(limit, 1), 100)
        offset = (page - 1) * limit

        rows = (
            await db.execute(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.tenant_id == user.tenant_id)
                .order_by(KnowledgeDocument.created_at.desc())
                .offset(offset).limit(limit)
            )
        ).scalars().all()
        return _jsonable([
            {
                "id": d.id, "title": d.title,
                "content_preview": d.content[:200] if d.content else None,
                "chunk_count": d.chunk_count, "is_auto_generated": d.is_auto_generated,
                "created_at": d.created_at,
            }
            for d in rows
        ])

    if name == "get_kb_document":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["get_kb_document"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        try:
            doc_id = uuid.UUID(str(args.get("doc_id", "")))
        except (ValueError, AttributeError):
            return {"error": "doc_id inválido"}

        doc = (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            return {"error": "Documento no encontrado"}

        # Si content no está guardado (doc file-based), reconstruir desde
        # KnowledgeChunk ordenados por chunk_index — mismo fallback exacto
        # que app/api/kb.py::get_document.
        content = doc.content
        if content is None:
            chunk_rows = (
                await db.execute(
                    select(KnowledgeChunk.content, KnowledgeChunk.chunk_index)
                    .where(KnowledgeChunk.document_id == doc_id)
                    .order_by(KnowledgeChunk.chunk_index)
                )
            ).all()
            if chunk_rows:
                content = "\n\n".join(r[0] for r in chunk_rows)

        return _jsonable({
            "id": doc.id, "title": doc.title, "content": content,
            "chunk_count": doc.chunk_count, "is_auto_generated": doc.is_auto_generated,
            "created_at": doc.created_at, "updated_at": doc.updated_at,
        })

    if name == "create_kb_document":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["create_kb_document"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        title_raw = args.get("title")
        content_raw = args.get("content")
        if not title_raw or not str(title_raw).strip():
            return {"error": "El título (title) es requerido"}
        title = str(title_raw)
        if len(title) > 255:
            return {"error": "El título (title) no puede exceder 255 caracteres"}
        if not content_raw or len(str(content_raw)) < 10:
            return {"error": "El contenido (content) debe tener al menos 10 caracteres"}
        content = str(content_raw)
        if len(content) > 20_000:
            return {"error": "El contenido (content) no puede exceder 20,000 caracteres"}

        content_hash = _sha256(content)
        # Idempotente por content_hash — mismo contenido ya indexado en el
        # tenant retorna el documento existente, no regenera embeddings.
        existing = (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == user.tenant_id,
                    KnowledgeDocument.content_hash == content_hash,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return _jsonable({
                "id": existing.id, "title": existing.title, "chunk_count": existing.chunk_count,
                "is_auto_generated": existing.is_auto_generated, "created_at": existing.created_at,
            })

        now = datetime.now(timezone.utc)
        doc_id = uuid.uuid4()
        doc = KnowledgeDocument(
            id=doc_id,
            branch_id=user.branch_id,
            tenant_id=user.tenant_id,
            filename=f"doc_{doc_id.hex[:8]}.txt",
            title=title,
            content=content,
            content_hash=content_hash,
            chunk_count=0,
            indexed_at=now,
            is_auto_generated=False,
        )
        db.add(doc)
        await db.flush()

        # _embed_and_store llama a OpenAI de forma SÍNCRONA acá dentro —
        # puede tardar varios segundos, es esperado (ya decidido, mismo
        # comportamiento que el REST real). Si OPENAI_API_KEY no está
        # configurado, o falla la generación, lanza HTTPException — se
        # atrapa acá para no dejar propagar la excepción cruda, con
        # rollback explícito del doc ya flusheado (mismo motivo que el
        # rollback tras IntegrityError en create_product_category: sin él
        # la sesión queda con un insert pendiente para el resto del request).
        try:
            chunk_count = await _embed_and_store(content, doc_id, user.tenant_id, title, db)
        except HTTPException as exc:
            await db.rollback()
            return {"error": str(exc.detail)}
        doc.chunk_count = chunk_count
        await db.commit()

        return _jsonable({
            "id": doc_id, "title": title, "chunk_count": chunk_count,
            "is_auto_generated": False, "created_at": now,
        })

    if name == "update_kb_document":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["update_kb_document"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        try:
            doc_id = uuid.UUID(str(args.get("doc_id", "")))
        except (ValueError, AttributeError):
            return {"error": "doc_id inválido"}

        doc = (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            return {"error": "Documento no encontrado"}

        if "title" in args and args["title"] is not None:
            new_title = str(args["title"])
            if not new_title.strip():
                return {"error": "El título (title) no puede estar vacío"}
            if len(new_title) > 255:
                return {"error": "El título (title) no puede exceder 255 caracteres"}
            doc.title = new_title

        if "content" in args and args["content"] is not None:
            new_content = str(args["content"])
            if len(new_content) < 10:
                return {"error": "El contenido (content) debe tener al menos 10 caracteres"}
            if len(new_content) > 20_000:
                return {"error": "El contenido (content) no puede exceder 20,000 caracteres"}
            new_hash = _sha256(new_content)
            if new_hash != doc.content_hash:
                # Contenido cambió de verdad (hash distinto) — borra los
                # KnowledgeChunk viejos y regenera embeddings. Mismo manejo
                # de OPENAI_API_KEY faltante que en create_kb_document.
                await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
                await db.flush()
                try:
                    chunk_count = await _embed_and_store(new_content, doc_id, user.tenant_id, doc.title, db)
                except HTTPException as exc:
                    await db.rollback()
                    return {"error": str(exc.detail)}
                doc.content = new_content
                doc.content_hash = new_hash
                doc.chunk_count = chunk_count
                doc.indexed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(doc)
        return _jsonable({
            "id": doc.id, "title": doc.title, "chunk_count": doc.chunk_count,
            "is_auto_generated": doc.is_auto_generated, "created_at": doc.created_at,
        })

    if name == "delete_kb_document":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["delete_kb_document"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        try:
            doc_id = uuid.UUID(str(args.get("doc_id", "")))
        except (ValueError, AttributeError):
            return {"error": "doc_id inválido"}
        confirm = bool(args.get("confirm", False))

        doc = (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            return {"error": "Documento no encontrado"}

        # Flujo de confirmación en dos pasos para documentos auto-generados
        # (from onboarding) — mismo criterio que app/api/kb.py::delete_document,
        # pero con requires_confirmation en vez de confirm_url (no hay URL en
        # el contexto del Copiloto): el modelo debe volver a preguntar al
        # usuario y reintentar con confirm=True si acepta.
        if doc.is_auto_generated and not confirm:
            return {
                "warning": (
                    "Este documento fue generado automáticamente desde tu onboarding. "
                    "Eliminarlo puede afectar la calidad de las respuestas del bot."
                ),
                "requires_confirmation": True,
                "doc_id": str(doc_id),
            }

        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
        await db.delete(doc)
        await db.commit()
        return {"deleted": True, "id": str(doc_id)}

    if name == "add_kb_fragment":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["add_kb_fragment"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        # Alias legacy de create_kb_document — límites de longitud DISTINTOS
        # (title max 200 vs 255, content max 10_000 vs 20_000), propios de
        # FragmentIn en el REST real.
        title_raw = args.get("title")
        content_raw = args.get("content")
        if not title_raw or not str(title_raw).strip():
            return {"error": "El título (title) es requerido"}
        title = str(title_raw)
        if len(title) > 200:
            return {"error": "El título (title) no puede exceder 200 caracteres"}
        if not content_raw or len(str(content_raw)) < 10:
            return {"error": "El contenido (content) debe tener al menos 10 caracteres"}
        content = str(content_raw)
        if len(content) > 10_000:
            return {"error": "El contenido (content) no puede exceder 10,000 caracteres"}

        content_hash = _sha256(content)
        existing = (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == user.tenant_id,
                    KnowledgeDocument.content_hash == content_hash,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return _jsonable({
                "id": existing.id, "title": existing.title, "chunk_count": existing.chunk_count,
                "indexed_at": existing.indexed_at,
            })

        now = datetime.now(timezone.utc)
        doc_id = uuid.uuid4()
        doc = KnowledgeDocument(
            id=doc_id, branch_id=user.branch_id, tenant_id=user.tenant_id,
            filename=f"fragment_{doc_id.hex[:8]}.txt", title=title, content=content,
            content_hash=content_hash, chunk_count=0, indexed_at=now, is_auto_generated=False,
        )
        db.add(doc)
        await db.flush()

        try:
            chunk_count = await _embed_and_store(content, doc_id, user.tenant_id, title, db)
        except HTTPException as exc:
            await db.rollback()
            return {"error": str(exc.detail)}
        doc.chunk_count = chunk_count
        await db.commit()

        return _jsonable({
            "id": doc_id, "title": title, "chunk_count": chunk_count, "indexed_at": now,
        })

    if name == "delete_kb_fragment":
        from app.copilot.actions_catalog import ACTIONS
        from app.copilot.permissions import check_permission

        allowed, _reason = check_permission(user, ACTIONS["delete_kb_fragment"])
        if not allowed:
            return {"error": "No tienes permisos para esta acción"}

        try:
            document_id = uuid.UUID(str(args.get("document_id", "")))
        except (ValueError, AttributeError):
            return {"error": "document_id inválido"}

        doc = (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            return {"error": "Fragmento no encontrado"}

        # Alias legacy — a propósito SIN el flujo de confirmación de
        # auto_generated (borra directo), mismo comportamiento asimétrico
        # que app/api/kb.py::delete_kb_fragment real. No es un bug de este
        # wireo, es el comportamiento legacy documentado en el REST.
        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
        await db.delete(doc)
        await db.commit()
        return {"deleted": True, "id": str(document_id)}

    return {"error": f"Tool '{name}' no reconocida"}
