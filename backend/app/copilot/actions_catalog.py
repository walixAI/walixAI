"""Copiloto — Fase 1: catálogo declarativo de acciones.

Este módulo NO reimplementa ejecución — el Copiloto conversacional
(app/ai/copilot_engine.py + app/ai/copilot_tools.py, ya en producción desde
C2/C3/C4) tiene sus tools nativas de Claude con su propio dispatcher
(copilot_tools.execute_tool). Este catálogo formaliza esas tools (41
wireadas al día de la Ronda 2a-iii de Finanzas/Gastos) con la metadata
declarativa que hoy vive dispersa o no existe en absoluto: risk_tier,
requires_confirmation y required_role centralizados, en vez de checks de
rol sueltos dentro de execute_tool (ver el que reemplaza en
get_team_performance).

description de cada ActionDefinition = la misma string que ya se manda hoy
a Claude vía COPILOT_TOOLS (copilot_tools.py) — no se reescriben, son
literalmente lo que el modelo ya lee para decidir cuándo llamar cada tool.

handler:
  - Para las acciones ya wireadas: copilot_tools.execute_tool — el
    dispatcher real. Se invoca con el `name` de esta acción como primer
    argumento (execute_tool(action.name, args, user, tenant, db)).
  - Para las 4 acciones representativas TODAVÍA NO conectadas al Copiloto
    (assign_lead, delete_deal, send_whatsapp_message, cancel_subscription):
    handler=None. Existen para validar que el catálogo cubre los 3 tiers de
    riesgo con acciones reales de la app (mapean a endpoints REST ya
    existentes — ver el comentario de cada una), pero conectarlas al
    Copiloto es trabajo de una fase futura, no de esta.

requires_confirmation:
  TRUE para TODAS las acciones sin excepción — decisión de producto ya
  tomada (ver prompt de Fase 1). Hoy NO se aplica de forma uniforme: de las
  7 write tools existentes, solo set_monthly_goal tiene un protocolo de
  confirmación real (confirmed: bool en su propio input_schema); las otras
  6 ejecutan de inmediato. Ese enforcement declarativo y centralizado es
  Fase 6 ("habilitar ejecución real de acciones") — acá el campo es
  metadata, no todavía una puerta que bloquea nada.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.ai.copilot_tools import execute_tool
from app.models.user import UserRole

RiskTier = Literal["low", "medium", "high"]

_ALL_ROLES = frozenset(UserRole)
# Mismo set que _OWNER_ROLES en copilot_tools.py / billing.py::_require_owner.
#
# OJO: este set NO incluye IT a propósito — cancel_subscription,
# get_team_performance y list_finance_permissions son intencionalmente más
# restrictivos que otras acciones "owner-tier" del código (ver hallazgo #4
# de docs/PERMISSIONS_DRIFT_BACKLOG.md). Si en el futuro se conecta
# re_execute_automation o patch_automation (app/api/automations.py) al
# catálogo, usar un set que SÍ incluya IT — como
# app/api/automations.py::_OWNER_PLUS del REST equivalente — NO reutilizar
# _OWNER_TIER. automations.py::_OWNER_PLUS ya es correcto tal como está;
# no se tocó en ese hallazgo, solo se documentó esta divergencia
# intencional para que no se junten por error.
_OWNER_TIER = frozenset({UserRole.OWNER, UserRole.PLATFORM_OWNER})

ActionHandler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    description: str
    risk_tier: RiskTier
    requires_confirmation: bool
    required_role: frozenset[UserRole]
    handler: ActionHandler | None


def _wired(
    name: str,
    description: str,
    risk_tier: RiskTier,
    required_role: frozenset[UserRole] = _ALL_ROLES,
) -> ActionDefinition:
    """Acción ya ejecutable hoy vía copilot_tools.execute_tool."""
    return ActionDefinition(
        name=name,
        description=description,
        risk_tier=risk_tier,
        requires_confirmation=True,
        required_role=required_role,
        handler=execute_tool,
    )


def _stub(
    name: str,
    description: str,
    risk_tier: RiskTier,
    required_role: frozenset[UserRole] = _ALL_ROLES,
) -> ActionDefinition:
    """Acción representativa NO conectada al Copiloto todavía — Fase 6."""
    return ActionDefinition(
        name=name,
        description=description,
        risk_tier=risk_tier,
        requires_confirmation=True,
        required_role=required_role,
        handler=None,
    )


# ── Acciones de bajo riesgo (lectura + escritura no destructiva/interna) ──────

_LOW_RISK: list[ActionDefinition] = [
    _wired(
        "get_pipeline_status",
        "Returns the current sales pipeline: number of active deals and total MXN value "
        "per stage, ordered from first to last stage. Use this when the user asks about "
        "their pipeline, how many deals they have, or what's in each stage.",
        "low",
    ),
    _wired(
        "search_contacts",
        "Searches contacts (leads) by name or WhatsApp phone number. "
        "Returns basic info: id, name, phone, status, assigned agent. "
        "Use when the user asks about a specific client or contact.",
        "low",
    ),
    _wired(
        "get_contact_context",
        "Returns AI memory context for a specific contact: summary, key facts, sentiment, "
        "urgency score, and recent events. Requires contact_id (UUID from search_contacts).",
        "low",
    ),
    _wired(
        "get_my_tasks",
        "Returns pending tasks for the current user: title, kind, due date, overdue flag, "
        "and associated contact/deal. Use when asked about pending tasks or activities.",
        "low",
    ),
    _wired(
        "get_my_suggestions",
        "Returns active AI suggestions (follow-up recommendations, pipeline alerts, etc.) "
        "for the current user. Use when asked for recommendations or what to do next.",
        "low",
    ),
    _wired(
        "get_my_deals",
        "Returns a list of deals. scope='mine' = current user's deals; "
        "scope='tenant' = all tenant deals. Use when asked about deals or opportunities.",
        "low",
    ),
    _wired(
        "get_profitability",
        "Returns profitability: revenue, expenses, profit, profit % and label. "
        "scope='tenant' for overall; scope='user' for the current user. "
        "Use when asked about profit margin, rentabilidad, or financial health.",
        "low",
    ),
    _wired(
        "get_run_rate",
        "Returns run-rate: won revenue, projected month-end revenue, goal %, gap, "
        "and recommendations. scope='tenant' or scope='user'. "
        "Use when asked about run rate, sales projection, or monthly progress.",
        "low",
    ),
    _wired(
        "get_expenses_summary",
        "Returns confirmed expenses for a period grouped by kind (fijo/variable). "
        "Use when asked about gastos, expenses, or costs.",
        "low",
    ),
    _wired(
        "get_monthly_goal",
        "Returns the current global monthly sales goal: target amount and period. "
        "Use when asked about the monthly goal or meta mensual.",
        "low",
    ),
    _wired(
        "get_team_performance",
        "Returns performance data per team member: won revenue, run rate, profit margin. "
        "Only for OWNER and PLATFORM_OWNER roles.",
        "low",
        required_role=_OWNER_TIER,
    ),
    _wired(
        "add_note",
        "Adds a note to a contact or deal. "
        "Use when the user wants to record information, observations, or comments about a contact or deal.",
        "low",
    ),
    _wired(
        "create_task",
        "Creates a pending task for a contact. "
        "Use when the user wants to schedule an activity: follow-up, quote, collection, service, etc.",
        "low",
    ),
    _wired(
        "dismiss_suggestion",
        "Dismisses an active AI suggestion addressed to the current user, with an "
        "optional reason. Use when the user wants to discard, ignore, or reject a "
        "suggested action (from get_my_suggestions) instead of confirming it.",
        "low",
    ),
    # Expansión Finanzas/Gastos, Ronda 1 — las 6 de abajo (todas menos
    # list_finance_permissions) validan acceso real vía
    # app/copilot/finance_access.py::require_finance_access dentro del
    # dispatcher, no vía required_role acá — mismo patrón que
    # get_profitability/get_run_rate/get_expenses_summary (hallazgo #8).
    _wired(
        "list_expenses",
        "Lists individual expense records with full detail (id, category, amount, kind, "
        "currency, status, date, description, etc.), with optional filters by month, kind "
        "(fijo/variable), category_id, status (draft/confirmed), and branch_id. Unlike "
        "get_expenses_summary (which only returns totals grouped by kind), this returns "
        "the actual list of expense rows. Use when the user wants to see, review, or "
        "filter individual gastos, not just a total.",
        "low",
    ),
    _wired(
        "list_expense_categories",
        "Lists expense categories (name, kind, icon, active flag) configured for the "
        "tenant. Use when the user asks what expense categories exist, or before "
        "creating/filtering an expense by category.",
        "low",
    ),
    _wired(
        "list_recurring_expenses",
        "Lists recurring (monthly) expense definitions: category, amount, day of month, "
        "description, active flag. Use when asked about gastos recurrentes or fixed "
        "monthly charges configured for the tenant.",
        "low",
    ),
    _wired(
        "list_expense_rules",
        "Lists automatic expense generation rules tied to deals (percent_of_deal, "
        "fixed_per_deal, percent_of_cost), including their category, value, deal type "
        "filter, and auto-confirm flag. Use when asked how expenses are auto-generated "
        "from won deals, or what rules exist.",
        "low",
    ),
    _wired(
        "list_product_categories",
        "Lists product categories used to segment monthly goals by product line. "
        "Use when asked what product categories exist, or before setting a "
        "product-category-scoped monthly goal.",
        "low",
    ),
    _wired(
        "list_goal_assignments",
        "Lists how a specific monthly goal is split across team members: each assigned "
        "user, their share percent, and their resulting amount. Requires goal_id. Use "
        "when asked who a monthly goal is assigned to, or how it's distributed across "
        "the team.",
        "low",
    ),
    # list_finance_permissions SÍ usa required_role acá (_OWNER_TIER) — su
    # endpoint REST real (app/api/finance.py::list_finance_permissions) usa
    # _require_owner, no _require_finance_access: ver quién tiene acceso a
    # finanzas es una acción de owner, no de cualquiera con acceso de
    # lectura a finanzas. El dispatcher (execute_tool) valida esto vía
    # check_permission + ACTIONS["list_finance_permissions"], mismo patrón
    # que get_team_performance.
    _wired(
        "list_finance_permissions",
        "Lists which users have been granted access to financial reports, and whether "
        "that access is tenant-wide or scoped to a specific branch. Only for OWNER and "
        "PLATFORM_OWNER roles. Use when asked who can see finanzas, or to audit finance "
        "access grants.",
        "low",
        required_role=_OWNER_TIER,
    ),
]

# ── Acciones de riesgo medio (escritura sobre datos propios del tenant) ───────

_MEDIUM_RISK: list[ActionDefinition] = [
    _wired(
        "create_contact",
        "Creates a new contact (lead) in the CRM. Requires at least a name or phone number. "
        "Use when the user explicitly asks to add or create a new contact or client.",
        "medium",
    ),
    _wired(
        "create_deal",
        "Creates a new deal (opportunity) for an existing contact. "
        "Requires lead_id, pipeline_stage_id, and a title. "
        "Use when the user asks to open, register, or create a new deal or sale.",
        "medium",
    ),
    _wired(
        "move_deal_stage",
        "Moves a deal to a different pipeline stage. "
        "If the new stage is a winning stage, marks the deal as won and generates expense drafts. "
        "Use when the user asks to advance, move, or change a deal's stage.",
        "medium",
    ),
    _wired(
        "prepare_whatsapp_message",
        "Prepares a WhatsApp message draft for a contact and saves it for human review. "
        "IMPORTANT: This tool NEVER sends messages. It only creates a draft that the user "
        "must review and send manually. Use when the user asks to draft or prepare a message.",
        "medium",
    ),
    _wired(
        "set_monthly_goal",
        "Sets or updates the global monthly sales goal for the current or future month. "
        "REQUIRES confirmed=true — only call this after the user has explicitly confirmed "
        "the new goal amount. If confirmed=false, the tool returns a confirmation request "
        "that you must present to the user before proceeding.",
        "medium",
    ),
    # Expansión Finanzas/Gastos, Ronda 2a-iii — metas (cierra la Ronda 2a
    # completa). Ambas validan acceso real vía require_finance_access
    # dentro del dispatcher (branch_id=None, tenant-wide), mismo patrón que
    # sus hermanas de las Rondas 2a-i/2a-ii. Son DISTINTAS de
    # set_monthly_goal (arriba): actualizan/reemplazan por goal_id, no
    # hacen upsert por dimensión.
    _wired(
        "update_monthly_goal",
        "Updates an existing monthly goal identified by its id — partial update, only "
        "the fields provided are changed. Requires goal_id. Editable fields: amount, "
        "currency, notes, is_draft. Note: notes can only be set, never cleared back to "
        "none, through this action. Fails if the goal belongs to a past period. Use "
        "when the user wants to edit a specific monthly goal (found via get_monthly_goal "
        "or list operations), as opposed to set_monthly_goal which upserts by period/dimension.",
        "medium",
    ),
    # set_goal_assignments reemplaza TODAS las asignaciones de una meta de
    # golpe (bulk set, no incremental) — destructivo para las asignaciones
    # existentes de esa meta, aunque reversible (queda antes/después en
    # MonthlyGoalHistory y se puede volver a llamar con el set anterior).
    # Tier medium por analogía con confirm_all_draft_expenses/
    # trigger_recurring_expense_generation (arriba): escritura masiva sobre
    # datos propios del tenant, no sobre terceros, y sin borrado permanente
    # de datos fuera de esa meta. Decisión reportada en el chat, no
    # asumida — mismo criterio que trigger_recurring_expense_generation en
    # la Ronda 2a-i.
    _wired(
        "set_goal_assignments",
        "Replaces the ENTIRE set of user assignments for a monthly goal in one shot — "
        "this is a full replacement, not an incremental add. Each assignment has a "
        "user_id and a share_percent (0-100); each user's resulting amount is "
        "auto-calculated as goal.amount * share_percent / 100. For a non-draft goal "
        "with a non-empty assignment list, the share percentages must sum to exactly "
        "100% (tolerance 0.01) — mark the goal as draft to save a partial split. Use "
        "when the user wants to define or change how a monthly goal is split across "
        "team members.",
        "medium",
    ),
    # Representativa, NO conectada al Copiloto — mapea a POST /leads/{id}/assign
    # (app/api/leads.py::assign_lead), que hoy tampoco restringe por rol.
    _stub(
        "assign_lead",
        "Reassigns a contact (lead) to a different user on the team. "
        "Use when the user asks to hand off or reassign a contact to a colleague.",
        "medium",
    ),
    # Expansión Finanzas/Gastos, Ronda 2a-i — núcleo de gastos (escritura).
    # Las 4 de abajo validan acceso real vía require_finance_access dentro
    # del dispatcher, no vía required_role acá — mismo patrón que las 6
    # tools de lectura de Finanzas/Gastos de la Ronda 1 (hallazgo #8).
    _wired(
        "create_expense",
        "Creates a new expense record for the tenant, immediately confirmed "
        "(status='confirmed'). Requires category_id, amount (>0), and kind "
        "('fijo' or 'variable'). Optional: branch_id, currency (defaults to MXN), "
        "incurred_at (defaults to today), deal_id, receipt_url, description. "
        "Use when the user wants to log, register, or add a new gasto/expense.",
        "medium",
    ),
    _wired(
        "update_expense",
        "Updates an existing expense record — partial update, only the fields "
        "provided are changed. Requires expense_id. Editable fields: branch_id, "
        "category_id, amount, kind, currency, incurred_at, status, deal_id, "
        "receipt_url, description. Use when the user wants to edit, correct, or "
        "change details of an existing gasto/expense.",
        "medium",
    ),
    _wired(
        "confirm_expense",
        "Confirms a draft expense, setting its status to 'confirmed'. Optionally "
        "updates its amount at the same time. Requires expense_id. Use when the "
        "user wants to approve or confirm a pending (draft) gasto/expense.",
        "medium",
    ),
    _wired(
        "confirm_all_draft_expenses",
        "Confirms ALL draft expenses for the tenant at once, setting their "
        "status to 'confirmed'. Returns the number of expenses updated. Use "
        "when the user wants to bulk-confirm or approve all pending draft "
        "gastos/expenses in one go.",
        "medium",
    ),
    # trigger_recurring_expense_generation SÍ usa required_role acá
    # (_OWNER_TIER) — su endpoint REST real
    # (app/api/finance.py::trigger_recurring_expense_generation) usa
    # _require_owner, no _require_finance_access: generar los gastos
    # recurrentes del mes es una acción de owner, no de cualquiera con
    # acceso de lectura/escritura a finanzas. El dispatcher (execute_tool)
    # valida esto vía check_permission + ACTIONS[name], mismo patrón que
    # list_finance_permissions/get_team_performance. Tier medium por
    # analogía con confirm_all_draft_expenses: es una escritura masiva
    # sobre el tenant pero no destructiva (crea Expense rows, no borra
    # nada) y además es idempotente — generate_recurring_expenses salta
    # las plantillas que ya generaron su gasto del mes actual.
    _wired(
        "trigger_recurring_expense_generation",
        "Generates this month's expense records from all active recurring "
        "expense templates. Idempotent — skips templates that already "
        "generated an expense for the current month. Only for OWNER and "
        "PLATFORM_OWNER roles. Use when the user (owner) wants to manually "
        "trigger generation of recurring/fixed monthly expenses instead of "
        "waiting for the scheduled job.",
        "medium",
        required_role=_OWNER_TIER,
    ),
    # Expansión Finanzas/Gastos, Ronda 2a-ii — catálogos de finanzas (4
    # pares create/update). Todas validan acceso real vía
    # require_finance_access dentro del dispatcher (branch_id=None,
    # tenant-wide), no vía required_role acá — mismo patrón que sus 4
    # hermanas de lectura de la Ronda 1.
    _wired(
        "create_expense_category",
        "Creates a new expense category for the tenant. Requires name and "
        "kind ('fijo' or 'variable'). Optional: icon. Use when the user "
        "wants to add a new category to classify expenses.",
        "medium",
    ),
    _wired(
        "update_expense_category",
        "Updates an existing expense category — partial update, only the "
        "fields provided are changed. Requires category_id. Editable "
        "fields: name, kind, icon, is_active. Use when the user wants to "
        "edit, rename, or activate/deactivate an expense category.",
        "medium",
    ),
    _wired(
        "create_recurring_expense",
        "Creates a new recurring (monthly) expense template. Requires "
        "amount (>0). Optional: category_id, day_of_month (1-28, default "
        "1), description. Use when the user wants to set up a fixed "
        "monthly charge, like rent or a subscription.",
        "medium",
    ),
    _wired(
        "update_recurring_expense",
        "Updates an existing recurring expense template — partial update, "
        "only the fields provided are changed. Requires recurring_id. "
        "Editable fields: category_id, amount, day_of_month (1-28), "
        "description, is_active. Use when the user wants to edit or "
        "deactivate a recurring/fixed monthly expense.",
        "medium",
    ),
    _wired(
        "create_expense_rule",
        "Creates a new automatic expense generation rule tied to deals. "
        "Requires name, rule_type ('percent_of_deal', 'fixed_per_deal', or "
        "'percent_of_cost'), and value (>0). Optional: category_id, "
        "deal_type_filter, auto_confirm (default false). Use when the user "
        "wants to set up automatic expense generation from won deals.",
        "medium",
    ),
    _wired(
        "update_expense_rule",
        "Updates an existing expense generation rule — partial update, only "
        "the fields provided are changed. Requires rule_id. Editable "
        "fields: category_id, name, rule_type, value, deal_type_filter, "
        "auto_confirm, is_active. Note: deal_type_filter can only be set, "
        "never cleared back to none, through this action. Use when the "
        "user wants to edit an existing expense rule.",
        "medium",
    ),
    _wired(
        "create_product_category",
        "Creates a new product category used to segment monthly goals by "
        "product line. Requires name (must be unique within the tenant). "
        "Optional: position (default 0). Use when the user wants to add a "
        "new product category.",
        "medium",
    ),
    _wired(
        "update_product_category",
        "Updates an existing product category — partial update, only the "
        "fields provided are changed. Requires category_id. Editable "
        "fields: name (must stay unique within the tenant), is_active, "
        "position. Use when the user wants to rename, reorder, or "
        "activate/deactivate a product category.",
        "medium",
    ),
]

# ── Acciones de alto riesgo (impacto en terceros, destructivas, o config) ─────

_HIGH_RISK: list[ActionDefinition] = [
    # Representativa, NO conectada al Copiloto — mapea a POST /leads/{id}/messages
    # (app/api/leads.py::send_message). Distinta de prepare_whatsapp_message: esta
    # SÍ entregaría el mensaje a un tercero real, sin intervención humana de por medio.
    _stub(
        "send_whatsapp_message",
        "Sends a WhatsApp message directly to a contact through the tenant's business number. "
        "Unlike prepare_whatsapp_message, this delivers the message immediately with no "
        "human review step. Use only after explicit user confirmation.",
        "high",
    ),
    # Representativa, NO conectada al Copiloto — mapea a DELETE /deals/{id}
    # (app/api/deals.py::delete_deal). NOTA: ese endpoint tampoco restringe por rol
    # hoy (mismo gap que assign_lead) — señalado en el reporte de esta fase, no
    # corregido acá (está fuera del alcance: esto es catálogo/schema, no un fix
    # de autorización en app/api/deals.py).
    _stub(
        "delete_deal",
        "Permanently deletes a deal from the CRM. This action cannot be undone. "
        "Use only when the user explicitly asks to delete a deal and confirms the deletion.",
        "high",
    ),
    # Representativa, NO conectada al Copiloto — mapea a POST /billing/cancel
    # (app/api/billing.py::cancel_subscription, ya gateado a OWNER/PLATFORM_OWNER
    # vía _require_owner — required_role acá refleja esa misma restricción real).
    _stub(
        "cancel_subscription",
        "Cancels the tenant's subscription at the end of the current billing period. "
        "Use only when the user explicitly asks to cancel their subscription and confirms.",
        "high",
        required_role=_OWNER_TIER,
    ),
    # Representativa, NO conectada al Copiloto — mapea a
    # POST /agents/suggestions/{id}/confirm (app/api/agents.py::confirm_suggestion).
    # No se conecta hasta que Fase 6 aplique requires_confirmation de verdad:
    # confirmar dispara execute_suggestion_task.delay() (ejecución real vía
    # Celery), que puede terminar enviando un WhatsApp real a un lead según
    # agent_type — mismo criterio de riesgo que send_whatsapp_message, arriba.
    _stub(
        "confirm_suggestion",
        "Confirms an active AI suggestion, queuing its real execution (may send a "
        "WhatsApp message to a lead, move a deal stage, or trigger other business "
        "actions depending on the suggestion's agent_type). Use only after explicit "
        "user confirmation.",
        "high",
    ),
]

ACTIONS_LIST: list[ActionDefinition] = [*_LOW_RISK, *_MEDIUM_RISK, *_HIGH_RISK]

ACTIONS: dict[str, ActionDefinition] = {a.name: a for a in ACTIONS_LIST}

assert len(ACTIONS) == len(ACTIONS_LIST), "Nombre de acción duplicado en el catálogo"


def get_action(name: str) -> ActionDefinition | None:
    return ACTIONS.get(name)
