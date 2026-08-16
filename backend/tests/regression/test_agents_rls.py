"""
Regresión — Grupo A/B de RLS Parte 2: enumeración cross-tenant + agentes.

Código auditado:
  - app/tasks/_helpers.py::get_active_branch_tenant_pairs() usa
    fn_list_active_branch_tenant_pairs() (SECURITY DEFINER, migración
    m8n9o0p1q2r3) — NO es un caso "pre-tenant" (Parte 1): es enumeración
    cross-tenant PERMANENTE (Celery beat necesita ver TODOS los tenants a la
    vez), que ningún set_tenant_context() de un solo tenant puede resolver.
  - app/agents/{closing,config,follow_up,pipeline}_agent.py — cada uno abre
    su propia AsyncSessionLocal() y ahora recibe tenant_id explícito
    (closing_agent ya lo recibía; los otros tres lo obtienen de
    get_active_branch_tenant_pairs() vía app/tasks/agent_tasks.py) +
    set_tenant_context() antes de la primera query.

Estos tests NO invocan a Claude (evitan costo/latencia real, siguiendo la
convención ya establecida en esta suite) — prueban específicamente las
queries RLS-protegidas de la porción previa a la llamada a Claude, con datos
armados a propósito para que el early-return natural de cada función
(sin etapas inactivas / sin leads candidatos / sin conversaciones stale)
se dispare ANTES de necesitar un mock de Anthropic.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config_agent import _run_config
from app.agents.follow_up_agent import _run_follow_up
from app.agents.pipeline_agent import _run_pipeline
from app.core.database import set_tenant_context
from app.models.tenant import Branch
from tests.regression.conftest import impersonate_walix_app_or_skip


async def test_fn_list_active_branch_tenant_pairs_sees_all_tenants_under_real_rls(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    """fn_list_active_branch_tenant_pairs() debe ver el branch recién creado
    por el fixture incluso bajo walix_app, SIN que ningún
    set_tenant_context() apunte a `tenant` — es enumeración cross-tenant a
    propósito, no un lookup de un tenant específico.

    Se llama la función SQL directamente en esta misma sesión impersonada,
    NO a través de app.tasks._helpers.get_active_branch_tenant_pairs() — ese
    wrapper abre su PROPIA AsyncSessionLocal() (otra conexión real, para que
    sirva como entrypoint de una Celery task), así que no heredaría ni la
    impersonación de este test ni vería los datos del fixture (todavía sin
    commit en la transacción de este test — conexión distinta, snapshot
    distinto). Probar el wrapper de punta a punta requiere un servidor real
    con DATABASE_URL apuntando a walix_app — cubierto en la verificación
    manual de Paso 3, no en esta suite.
    """
    await impersonate_walix_app_or_skip(db)

    rows = (
        await db.execute(text("SELECT branch_id, tenant_id FROM fn_list_active_branch_tenant_pairs()"))
    ).fetchall()
    pairs = {(row.branch_id, row.tenant_id) for row in rows}
    assert (branch.id, tenant.id) in pairs


async def test_config_agent_query_phase_succeeds_under_real_rls(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    """_run_config sin pipeline_stages para esta branch → early return False
    ANTES de llamar a Claude — prueba solo la query RLS-protegida inicial
    (db.get(Branch, ...))."""
    await impersonate_walix_app_or_skip(db)
    await set_tenant_context(db, tenant.id)

    result = await _run_config(branch.id, db)
    assert result is False  # sin pipeline_stages activas → no hay nada que sugerir


async def test_pipeline_agent_query_phase_succeeds_under_real_rls(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    """_run_pipeline sin Pipeline default para esta branch → early return
    False antes de Claude — prueba db.get(Branch, ...) + el SELECT de
    Pipeline bajo RLS real."""
    await impersonate_walix_app_or_skip(db)
    await set_tenant_context(db, tenant.id)

    result = await _run_pipeline(branch.id, db)
    assert result is False  # sin Pipeline default → no hay nada que analizar


async def test_follow_up_agent_query_phase_succeeds_under_real_rls(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    """_run_follow_up: branch sin wa_phone_number_id/wa_token → early return
    0 antes de cualquier query de Conversation/Lead — prueba db.get(Branch, ...)."""
    await impersonate_walix_app_or_skip(db)
    await set_tenant_context(db, tenant.id)

    result = await _run_follow_up(branch.id, db)
    assert result == 0  # sin credenciales WA → no hay nada que procesar
