"""
Regresión — Copiloto: dismiss_suggestion (wireada) + confirm_suggestion (stub).

Código auditado:
  - app/ai/copilot_tools.py::execute_tool, rama "dismiss_suggestion" — carga
    la sugerencia con ownership real (target_user_id == usuario, O
    target_user_id IS NULL Y target_role == rol del usuario), mismo patrón
    que app/api/agents.py::list_suggestions (líneas 82-86). A propósito NO
    reutiliza agents.py::_get_suggestion_for_user, que solo valida
    tenant_id — ver hallazgo #7 de docs/PERMISSIONS_DRIFT_BACKLOG.md.
  - app/copilot/actions_catalog.py — dismiss_suggestion wireada (low risk),
    confirm_suggestion agregada como stub (high risk, sin handler — Fase 6).

Estos tests llaman execute_tool() directo (no pasan por RLS/walix_app —
mismo patrón que los tests existentes de escritura del Copiloto no lo hacen
tampoco, ya que corren contra la sesión admin de la suite con tenant_id
filtrado a mano en cada query, igual que el código real).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot_tools import execute_tool
from app.models.agent import AgentSuggestion
from app.models.tenant import Branch, Tenant
from app.models.user import User, UserRole


def _make_suggestion(
    tenant: Tenant,
    *,
    target_user_id: uuid.UUID | None = None,
    target_role: str = "owner",
    status: str = "suggested",
) -> AgentSuggestion:
    return AgentSuggestion(
        tenant_id=tenant.id,
        agent_type="follow_up",
        trigger_description="Lead sin respuesta hace 3 días",
        suggestion_text="Enviar seguimiento a Juan Pérez",
        target_role=target_role,
        target_user_id=target_user_id,
        status=status,
    )


# ── Dismiss exitoso ──────────────────────────────────────────────────────────

async def test_dismiss_suggestion_success_direct_target(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    sug = _make_suggestion(tenant, target_user_id=owner_user.id, target_role="owner")
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, owner_user, tenant, db,
    )

    assert result["dismissed"] is True
    assert result["suggestion_id"] == str(sug.id)

    await db.refresh(sug)
    assert sug.status == "dismissed"
    assert sug.responded_at is not None
    assert sug.responded_at.tzinfo is not None or sug.responded_at <= datetime.now(timezone.utc)


async def test_dismiss_suggestion_success_with_reason(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    sug = _make_suggestion(tenant, target_user_id=owner_user.id, target_role="owner")
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion",
        {"suggestion_id": str(sug.id), "reason": "No aplica para este cliente"},
        owner_user, tenant, db,
    )

    assert result["dismissed"] is True
    assert result["reason"] == "No aplica para este cliente"

    await db.refresh(sug)
    assert sug.status == "dismissed"
    assert sug.execution_result == {"dismissed_reason": "No aplica para este cliente"}


async def test_dismiss_suggestion_success_by_role_broadcast(
    db: AsyncSession, tenant: Tenant, asesor_user: User,
) -> None:
    """target_user_id=NULL, target_role coincide con el rol del usuario — debe permitir."""
    sug = _make_suggestion(tenant, target_user_id=None, target_role=UserRole.ASESOR.value)
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, asesor_user, tenant, db,
    )

    assert result["dismissed"] is True
    await db.refresh(sug)
    assert sug.status == "dismissed"


async def test_dismiss_suggestion_success_accepted_status(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    """status='accepted' también es dismissable, igual que agents.py::dismiss_suggestion."""
    sug = _make_suggestion(
        tenant, target_user_id=owner_user.id, target_role="owner", status="accepted",
    )
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, owner_user, tenant, db,
    )
    assert result["dismissed"] is True


# ── Ownership — casos que deben ser rechazados ──────────────────────────────

async def test_dismiss_suggestion_denied_wrong_target_user(
    db: AsyncSession, tenant: Tenant, owner_user: User, asesor_user: User,
) -> None:
    """Dirigida a OTRO usuario específico (no None) — no debe poder dismissarla."""
    sug = _make_suggestion(tenant, target_user_id=asesor_user.id, target_role="asesor")
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, owner_user, tenant, db,
    )

    assert "error" in result
    await db.refresh(sug)
    assert sug.status == "suggested"  # sin cambios


async def test_dismiss_suggestion_denied_wrong_role_broadcast(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    """target_user_id=NULL pero target_role no coincide con el rol del usuario."""
    sug = _make_suggestion(tenant, target_user_id=None, target_role="asesor")
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, owner_user, tenant, db,
    )

    assert "error" in result
    await db.refresh(sug)
    assert sug.status == "suggested"


async def test_dismiss_suggestion_denied_cross_tenant(
    db: AsyncSession, tenant: Tenant, owner_user: User, other_tenant_ctx: dict,
) -> None:
    other_tenant = other_tenant_ctx["tenant"]
    sug = _make_suggestion(other_tenant, target_user_id=None, target_role="owner")
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, owner_user, tenant, db,
    )

    assert "error" in result


async def test_dismiss_suggestion_not_found(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(uuid.uuid4())}, owner_user, tenant, db,
    )
    assert "error" in result


async def test_dismiss_suggestion_invalid_uuid(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": "not-a-uuid"}, owner_user, tenant, db,
    )
    assert "error" in result


# ── Estado inválido para dismiss ────────────────────────────────────────────

async def test_dismiss_suggestion_already_dismissed(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    sug = _make_suggestion(
        tenant, target_user_id=owner_user.id, target_role="owner", status="dismissed",
    )
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, owner_user, tenant, db,
    )
    assert "error" in result


async def test_dismiss_suggestion_already_executed(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    sug = _make_suggestion(
        tenant, target_user_id=owner_user.id, target_role="owner", status="executed",
    )
    db.add(sug)
    await db.flush()

    result = await execute_tool(
        "dismiss_suggestion", {"suggestion_id": str(sug.id)}, owner_user, tenant, db,
    )
    assert "error" in result
    await db.refresh(sug)
    assert sug.status == "executed"  # sin cambios — no se pisa una ejecución real
