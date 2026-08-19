"""Copiloto — Fase 1: catálogo declarativo de acciones.

Este módulo NO reimplementa ejecución — el Copiloto conversacional
(app/ai/copilot_engine.py + app/ai/copilot_tools.py, ya en producción desde
C2/C3/C4) ya tiene 18 tools nativas de Claude con su propio dispatcher
(copilot_tools.execute_tool). Este catálogo formaliza esas 18 tools con la
metadata declarativa que hoy vive dispersa o no existe en absoluto:
risk_tier, requires_confirmation y required_role centralizados, en vez de
checks de rol sueltos dentro de execute_tool (ver el que reemplaza en
get_team_performance).

description de cada ActionDefinition = la misma string que ya se manda hoy
a Claude vía COPILOT_TOOLS (copilot_tools.py) — no se reescriben, son
literalmente lo que el modelo ya lee para decidir cuándo llamar cada tool.

handler:
  - Para las 18 acciones ya wireadas: copilot_tools.execute_tool — el
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
    # Representativa, NO conectada al Copiloto — mapea a POST /leads/{id}/assign
    # (app/api/leads.py::assign_lead), que hoy tampoco restringe por rol.
    _stub(
        "assign_lead",
        "Reassigns a contact (lead) to a different user on the team. "
        "Use when the user asks to hand off or reassign a contact to a colleague.",
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
]

ACTIONS_LIST: list[ActionDefinition] = [*_LOW_RISK, *_MEDIUM_RISK, *_HIGH_RISK]

ACTIONS: dict[str, ActionDefinition] = {a.name: a for a in ACTIONS_LIST}

assert len(ACTIONS) == len(ACTIONS_LIST), "Nombre de acción duplicado en el catálogo"


def get_action(name: str) -> ActionDefinition | None:
    return ACTIONS.get(name)
