"""
Regresión — Grupo D (RLS Parte 2): endpoints de API con AsyncSessionLocal propio.

Código auditado:
  - app/api/webhooks.py — _send_meta_lead_welcome, y el lookup pre-tenant de
    MetaLeadConfig por page_id vía fn_lookup_meta_lead_configs_by_page_id
    (SECURITY DEFINER, migración o0p1q2r3s4t5).
  - app/api/internal_wa.py — handle_internal_command resuelve el tenant por
    wa_phone del User vía fn_lookup_tenant_by_user_wa_phone (mismo patrón
    "pre-tenant" que login/webhook — ver test_pretenant_lookups.py) ANTES de
    conocer el tenant.
  - app/agents/executor.py — execute_suggestion(suggestion_id, tenant_id, db)
    ahora llama set_tenant_context() antes del primer db.get(), usado por
    automations.py (re-execute), agents.py (confirm) y
    app/tasks/agent_tasks.py::execute_suggestion_task (Celery).
  - app/api/contacts.py — _process_csv_import ya recibe tenant_id como
    parámetro; se le agregó set_tenant_context() al abrir su propia sesión.
    No se prueba acá directamente (ver limitación de aislamiento de sesión
    documentada abajo) — cubierto por auditoría de código + los tests de
    contacts.py existentes que sí corren bajo el rol admin.

Limitación de aislamiento de sesión (misma que test_agents_rls.py /
test_alerts_rls.py): funciones que abren su PROPIA AsyncSessionLocal()
(handle_internal_command, _send_meta_lead_welcome, _process_csv_import) usan
una conexión del pool DISTINTA de la de la fixture `db` — no ven los datos
sin commit de la fixture ni heredan el SET LOCAL ROLE de la impersonación.
Por eso acá se prueba:
  (a) las funciones SQL SECURITY DEFINER directamente, vía la sesión
      impersonada de la fixture, y
  (b) las funciones internas que SÍ reciben `db` como parámetro
      (execute_suggestion, _cmd_mis_leads/_cmd_leads_en_riesgo de
      internal_wa.py) con la sesión impersonada + ya escopeada.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal_wa import _cmd_leads_en_riesgo, _cmd_mis_leads, _resolve_tenant_by_wa_phone
from app.core.database import set_tenant_context
from app.models.agent import AgentSuggestion
from app.models.lead import Lead, LeadStatus
from app.models.meta_ads import MetaLeadConfig
from app.models.pipeline import PipelineStage
from app.models.tenant import Branch, Tenant
from app.models.user import User
from tests.regression.conftest import impersonate_walix_app_or_skip


# ── Permisos de las funciones SECURITY DEFINER nuevas ─────────────────────────

async def test_grupo_d_pretenant_functions_have_no_public_grant(db: AsyncSession) -> None:
    rows = (
        await db.execute(
            text(
                "SELECT routine_name, grantee FROM information_schema.routine_privileges "
                "WHERE routine_name IN "
                "('fn_lookup_meta_lead_configs_by_page_id', 'fn_lookup_tenant_by_user_wa_phone')"
            )
        )
    ).fetchall()
    grantees = {(row[0], row[1]) for row in rows}

    assert not any(grantee == "PUBLIC" for _name, grantee in grantees), (
        f"PUBLIC no debería tener EXECUTE sobre estas funciones — grants actuales: {grantees}"
    )
    assert ("fn_lookup_meta_lead_configs_by_page_id", "walix_app") in grantees
    assert ("fn_lookup_tenant_by_user_wa_phone", "walix_app") in grantees


# ── Meta Lead Ads: lookup de config por page_id ────────────────────────────────

async def test_fn_lookup_meta_lead_configs_by_page_id_resolves_under_rls(
    db: AsyncSession, tenant: Tenant, branch: Branch,
) -> None:
    config = MetaLeadConfig(
        branch_id=branch.id,
        tenant_id=tenant.id,
        page_id="PRETENANT_TEST_PAGE_ID",
        form_ids=["form-123"],
        page_access_token="fake-token-encrypted",
        field_mapping={},
        is_active=True,
    )
    db.add(config)
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    rows = (
        await db.execute(
            text("SELECT * FROM fn_lookup_meta_lead_configs_by_page_id(:pid)"),
            {"pid": "PRETENANT_TEST_PAGE_ID"},
        )
    ).fetchall()
    assert len(rows) == 1
    assert rows[0].tenant_id == tenant.id
    assert rows[0].branch_id == branch.id


async def test_fn_lookup_meta_lead_configs_returns_empty_for_unknown_page_id(
    db: AsyncSession,
) -> None:
    await impersonate_walix_app_or_skip(db)

    rows = (
        await db.execute(
            text("SELECT * FROM fn_lookup_meta_lead_configs_by_page_id(:pid)"),
            {"pid": "NUNCA_EXISTE_ESTE_PAGE_ID"},
        )
    ).fetchall()
    assert rows == []


# ── Internal WA: lookup de tenant por wa_phone del User ────────────────────────

async def test_fn_lookup_tenant_by_user_wa_phone_resolves_under_rls(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    owner_user.wa_phone = "+5215500000199"
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    tenant_id = (
        await db.execute(
            text("SELECT fn_lookup_tenant_by_user_wa_phone(:phone)"),
            {"phone": "+5215500000199"},
        )
    ).scalar_one_or_none()
    assert tenant_id == tenant.id


async def test_fn_lookup_tenant_by_user_wa_phone_raises_on_ambiguous_wa_phone(
    db: AsyncSession, owner_user: User, other_tenant_ctx: dict,
) -> None:
    """users.wa_phone NO tiene ningún constraint de unicidad (verificado
    contra app/models/user.py y pg_constraint/pg_indexes reales — ver
    docstring de la migración o0p1q2r3s4t5). DECISIÓN CONFIRMADA: si dos
    Users activos de CUALQUIER tenant llegaran a compartir el mismo
    wa_phone, eso es siempre un error de datos — la función debe fallar
    explícito (RAISE EXCEPTION, SQLSTATE 23505 → IntegrityError en
    SQLAlchemy) en vez de resolver un tenant arbitrario con LIMIT 1."""
    shared_phone = "+5215500000321"
    owner_user.wa_phone = shared_phone
    other_tenant_ctx["user"].wa_phone = shared_phone
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    with pytest.raises(IntegrityError):
        await db.execute(
            text("SELECT fn_lookup_tenant_by_user_wa_phone(:phone)"),
            {"phone": shared_phone},
        )


async def test_fn_lookup_tenant_by_user_wa_phone_returns_null_for_no_match(
    db: AsyncSession,
) -> None:
    """0 coincidencias debe seguir devolviendo NULL, sin excepción — el
    conteo agregado (count(*), max(tenant_id)) siempre produce una fila
    incluso sin matches, así que este caso no cambió con el fix de
    ambigüedad."""
    await impersonate_walix_app_or_skip(db)

    tenant_id = (
        await db.execute(
            text("SELECT fn_lookup_tenant_by_user_wa_phone(:phone)"),
            {"phone": "+5215500000000_NUNCA_EXISTE"},
        )
    ).scalar_one_or_none()
    assert tenant_id is None


async def test_resolve_tenant_by_wa_phone_helper_returns_none_on_ambiguous_phone(
    db: AsyncSession, owner_user: User, other_tenant_ctx: dict,
) -> None:
    """Prueba el helper _resolve_tenant_by_wa_phone (el mismo que usa
    handle_internal_command) directamente con la sesión impersonada — cubre
    el camino completo: SQL lanza IntegrityError → el helper lo captura,
    hace rollback, loguea, y devuelve None. Nunca debe propagar la
    excepción ni resolver un tenant arbitrario."""
    shared_phone = "+5215500000322"
    owner_user.wa_phone = shared_phone
    other_tenant_ctx["user"].wa_phone = shared_phone
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    result = await _resolve_tenant_by_wa_phone(db, shared_phone)
    assert result is None


async def test_resolve_tenant_by_wa_phone_helper_resolves_single_match(
    db: AsyncSession, tenant: Tenant, owner_user: User,
) -> None:
    """Caso normal (un solo User activo con ese wa_phone) sigue funcionando
    exactamente igual que antes del fix de ambigüedad."""
    owner_user.wa_phone = "+5215500000323"
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    result = await _resolve_tenant_by_wa_phone(db, "+5215500000323")
    assert result == tenant.id


async def test_internal_wa_commands_work_once_tenant_context_is_set(
    db: AsyncSession, tenant: Tenant, branch: Branch, owner_user: User,
) -> None:
    """Simula el segundo `async with AsyncSessionLocal()` de
    handle_internal_command: una vez resuelto el tenant (arriba) y fijado el
    contexto, _cmd_mis_leads / _cmd_leads_en_riesgo (que reciben `db` como
    parámetro) deben funcionar bajo RLS real sin necesitar bypass."""
    lead = Lead(
        branch_id=branch.id,
        tenant_id=tenant.id,
        wa_phone="+5215500000200",
        name="Lead Riesgo Interno",
        status=LeadStatus.NUEVO,
        assigned_to=owner_user.id,
        risk_score=0.9,
    )
    db.add(lead)
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await set_tenant_context(db, tenant.id)

    mis_leads = await _cmd_mis_leads(owner_user, db)
    assert "Lead Riesgo Interno" in mis_leads

    en_riesgo = await _cmd_leads_en_riesgo(owner_user, db)
    assert "Lead Riesgo Interno" in en_riesgo


# ── execute_suggestion bajo RLS real ───────────────────────────────────────────

async def test_execute_suggestion_config_deactivate_stage_under_real_rls(
    db: AsyncSession, tenant: Tenant, branch: Branch, stages: list[PipelineStage],
) -> None:
    from app.agents.executor import execute_suggestion

    stage = stages[0]
    suggestion = AgentSuggestion(
        tenant_id=tenant.id,
        branch_id=branch.id,
        agent_type="config",
        trigger_description="test",
        suggestion_text="Desactivar etapa de prueba",
        action_payload={"action": "deactivate_stage", "stage_id": str(stage.id)},
        target_role="gerente",
        status="confirmed",
    )
    db.add(suggestion)
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    result = await execute_suggestion(suggestion.id, tenant.id, db)
    assert result["applied"] is True

    await db.refresh(suggestion)
    assert suggestion.status == "executed"


async def test_execute_suggestion_not_found_under_wrong_tenant_context(
    db: AsyncSession, tenant: Tenant, branch: Branch, other_tenant_ctx: dict,
) -> None:
    """La suggestion pertenece al tenant A; se llama execute_suggestion con
    tenant_id de A (correcto), pero antes de eso el contexto de la sesión
    quedó fijado a B por una operación previa — set_tenant_context() dentro
    de execute_suggestion debe corregirlo al tenant correcto de todos modos,
    ya que siempre fija su PROPIO tenant_id como primer paso."""
    from app.agents.executor import execute_suggestion

    suggestion = AgentSuggestion(
        tenant_id=tenant.id,
        branch_id=branch.id,
        agent_type="config",
        trigger_description="test",
        suggestion_text="No ejecutable",
        action_payload={"action": "no_action"},
        target_role="gerente",
        status="confirmed",
    )
    db.add(suggestion)
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await set_tenant_context(db, other_tenant_ctx["tenant"].id)

    result = await execute_suggestion(suggestion.id, tenant.id, db)
    assert result == {"action": "no_action", "applied": False}
