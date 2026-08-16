"""
Regresión — process_message() de app/ai/bot_engine.py bajo RLS real.

Código auditado: app/ai/bot_engine.py::_process_message_inner abre su propia
AsyncSessionLocal() (no pasa por get_db()/el middleware HTTP) y, antes de
este fix, nunca llamaba set_tenant_context — aunque tenant_id ya le llega
como parámetro (branch.tenant_id, columna NOT NULL; único caller:
app/api/webhooks.py). Bajo el rol admin (bypass de RLS) esto no importaba;
bajo walix_app real causaba una excepción real y reproducible:

    sqlalchemy.exc.DBAPIError: invalid input syntax for type uuid: ""
    [SQL: SELECT branches... WHERE branches.id = $1::UUID]

capturada en vivo en el paso 14 (envío de la respuesta por WhatsApp), pero
que en realidad bloqueaba el flujo desde el paso 1 (config_loader.
get_branch_config → db.get(Branch, ...), la PRIMERA query de la función).

Este módulo NO invoca process_message() completo (llamaría a Claude, Redis y
WhatsApp de verdad — caro y lento para un test de regresión). En su lugar,
prueba directamente la secuencia de queries de los pasos 1-3 de
_process_message_inner (config de branch, lead, conversación) — exactamente
la porción que antes crasheaba — con el mismo mecanismo que el fix aplica:
impersonar walix_app + set_tenant_context ANTES de esas queries.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import config_loader
from app.ai.bot_engine import _get_or_create_active_conversation, _get_or_create_lead
from app.core.database import set_tenant_context
from app.models.tenant import Branch
from tests.regression.conftest import impersonate_walix_app_or_skip


async def test_process_message_pretenant_steps_succeed_under_real_rls(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    """Reproduce el caso exacto que crasheaba: branch config + lead +
    conversación, bajo walix_app real, con el fix aplicado (set_tenant_context
    ANTES de la primera query, igual que ahora hace _process_message_inner)."""
    await impersonate_walix_app_or_skip(db)
    await set_tenant_context(db, tenant.id)

    # Paso 1 — exactamente la query que crasheaba antes del fix (db.get(Branch, ...)).
    cfg = await config_loader.get_branch_config(branch.id, db)
    assert cfg is not None

    # Paso 2 — lead nuevo para este número.
    lead = await _get_or_create_lead(db, "+5215500099887", branch.id, tenant.id)
    assert lead.tenant_id == tenant.id
    assert lead.branch_id == branch.id

    # Paso 3 — conversación activa para ese lead.
    conversation = await _get_or_create_active_conversation(db, lead, branch.id)
    assert conversation.lead_id == lead.id


async def test_process_message_pretenant_steps_fail_without_context(
    db: AsyncSession, tenant, branch: Branch,
) -> None:
    """Control negativo: reproduce el crash original tal cual se capturó en
    producción. SIN set_tenant_context, la misma query
    (config_loader.get_branch_config → db.get(Branch, ...)) revienta con la
    excepción exacta del incidente — confirma que el test de arriba prueba
    algo real, no un no-op, y deja el caso reportado como regresión cubierta.
    """
    from sqlalchemy.exc import DBAPIError

    branch_id = branch.id
    # session.get() consulta primero el identity map: como `branch` ya está
    # cargado en esta sesión (lo trajo el fixture), un get() posterior
    # devolvería el objeto en memoria SIN pasar por la base — nunca le daría
    # a RLS la oportunidad de intervenir. expire() fuerza una relectura real.
    db.expire(branch)

    await impersonate_walix_app_or_skip(db)
    # A propósito: NO se llama set_tenant_context acá.

    with pytest.raises(DBAPIError, match='invalid input syntax for type uuid'):
        await config_loader.get_branch_config(branch_id, db)
