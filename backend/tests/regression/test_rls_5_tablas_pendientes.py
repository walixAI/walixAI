"""
Regresión — RLS en las 5 tablas pendientes del cutover original (832e6af):
ai_memory_events, ai_entity_context, expenses, subscriptions, failed_payments.

Código auditado (migración p1q2r3s4t5u6):
  - ALTER TABLE ... ENABLE/FORCE ROW LEVEL SECURITY + 4 policies en las 5
    tablas, mismo patrón que el resto de la serie.
  - app/tasks/ai_memory_tasks.py::update_entity_context_task — caso
    pre-tenant nuevo (fn_lookup_ai_memory_event_tenant).
  - app/services/expense_generation.py::generate_recurring_expenses —
    barrido cross-tenant, ahora agrupa por tenant_id y llama
    set_tenant_context() una vez por grupo antes de tocar `expenses`.
  - app/api/billing_webhook.py — los 4 handlers de Stripe ahora resuelven
    tenant_id (de metadata o de Tenant.stripe_customer_id, que no tiene
    RLS) y llaman set_tenant_context() antes de tocar
    subscriptions/failed_payments.
  - app/api/platform.py — hallazgo fuera del alcance original: el
    dashboard de Platform Owner hacía agregaciones cross-tenant sobre
    leads/messages/conversations/ai_command_logs (ya con RLS del cutover
    original) sin set_tenant_context en ningún lado — estaba
    silenciosamente roto. Ahora usa 5 funciones SECURITY DEFINER de
    agregación nuevas (primera vez en la serie que se necesita este tipo,
    no lookup puntual ni enumeración de existencia).

Mismo patrón de test que test_alerts_rls.py / test_agents_rls.py: se llama
la función SQL directamente en la sesión impersonada (SET LOCAL ROLE
walix_app vía impersonate_walix_app_or_skip), nunca el wrapper Python (que
abre su propia AsyncSessionLocal() real — no heredaría la impersonación de
este test). Esos flujos completos quedan cubiertos por la verificación
manual de Paso 4 contra un servidor real con DATABASE_URL apuntando a
walix_app.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_memory import AIEntityContext, AIMemoryEvent
from app.models.finance import Expense
from app.models.subscription import FailedPayment, Subscription
from app.models.tenant import Branch, Tenant
from tests.regression.conftest import impersonate_walix_app_or_skip


# ── RLS directa en las 5 tablas ────────────────────────────────────────────────

async def test_ai_memory_event_isolated_by_rls(
    db: AsyncSession, tenant: Tenant, other_tenant_ctx: dict,
) -> None:
    own = AIMemoryEvent(
        tenant_id=tenant.id, entity_type="contact", entity_id=uuid.uuid4(),
        event_type="message_received", event_data={},
    )
    other = AIMemoryEvent(
        tenant_id=other_tenant_ctx["tenant"].id, entity_type="contact", entity_id=uuid.uuid4(),
        event_type="message_received", event_data={},
    )
    db.add_all([own, other])
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": str(tenant.id)})

    ids = {r[0] for r in (await db.execute(text("SELECT id FROM ai_memory_events"))).fetchall()}
    assert own.id in ids
    assert other.id not in ids


async def test_ai_entity_context_isolated_by_rls(
    db: AsyncSession, tenant: Tenant, other_tenant_ctx: dict,
) -> None:
    own = AIEntityContext(tenant_id=tenant.id, entity_type="contact", entity_id=uuid.uuid4())
    other = AIEntityContext(tenant_id=other_tenant_ctx["tenant"].id, entity_type="contact", entity_id=uuid.uuid4())
    db.add_all([own, other])
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": str(tenant.id)})

    ids = {r[0] for r in (await db.execute(text("SELECT id FROM ai_entity_context"))).fetchall()}
    assert own.id in ids
    assert other.id not in ids


async def test_expenses_isolated_by_rls(
    db: AsyncSession, tenant: Tenant, other_tenant_ctx: dict,
) -> None:
    own = Expense(tenant_id=tenant.id, amount=100, kind="variable")
    other = Expense(tenant_id=other_tenant_ctx["tenant"].id, amount=200, kind="variable")
    db.add_all([own, other])
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": str(tenant.id)})

    ids = {r[0] for r in (await db.execute(text("SELECT id FROM expenses"))).fetchall()}
    assert own.id in ids
    assert other.id not in ids


async def test_subscriptions_isolated_by_rls(
    db: AsyncSession, tenant: Tenant, other_tenant_ctx: dict,
) -> None:
    own = Subscription(tenant_id=tenant.id, stripe_customer_id=f"cus_{uuid.uuid4().hex[:14]}")
    other = Subscription(tenant_id=other_tenant_ctx["tenant"].id, stripe_customer_id=f"cus_{uuid.uuid4().hex[:14]}")
    db.add_all([own, other])
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": str(tenant.id)})

    ids = {r[0] for r in (await db.execute(text("SELECT id FROM subscriptions"))).fetchall()}
    assert own.id in ids
    assert other.id not in ids


async def test_failed_payments_isolated_by_rls(
    db: AsyncSession, tenant: Tenant, other_tenant_ctx: dict,
) -> None:
    own = FailedPayment(tenant_id=tenant.id, stripe_invoice_id=f"in_{uuid.uuid4().hex[:14]}")
    other = FailedPayment(tenant_id=other_tenant_ctx["tenant"].id, stripe_invoice_id=f"in_{uuid.uuid4().hex[:14]}")
    db.add_all([own, other])
    await db.flush()

    await impersonate_walix_app_or_skip(db)
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"), {"tid": str(tenant.id)})

    ids = {r[0] for r in (await db.execute(text("SELECT id FROM failed_payments"))).fetchall()}
    assert own.id in ids
    assert other.id not in ids


# ── Caso pre-tenant: fn_lookup_ai_memory_event_tenant ──────────────────────────

async def test_fn_lookup_ai_memory_event_tenant_resolves_under_real_rls(
    db: AsyncSession, tenant: Tenant,
) -> None:
    event = AIMemoryEvent(
        tenant_id=tenant.id, entity_type="deal", entity_id=uuid.uuid4(),
        event_type="stage_changed", event_data={"from": "nuevo", "to": "ganado"},
    )
    db.add(event)
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    resolved = (
        await db.execute(text("SELECT fn_lookup_ai_memory_event_tenant(:id)"), {"id": event.id})
    ).scalar_one_or_none()
    assert resolved == tenant.id


async def test_fn_lookup_ai_memory_event_tenant_returns_null_for_unknown_id(
    db: AsyncSession,
) -> None:
    await impersonate_walix_app_or_skip(db)
    resolved = (
        await db.execute(text("SELECT fn_lookup_ai_memory_event_tenant(:id)"), {"id": uuid.uuid4()})
    ).scalar_one_or_none()
    assert resolved is None


# ── Funciones de agregación cross-tenant para app/api/platform.py ─────────────

async def test_fn_platform_lead_counts_by_tenant_sees_all_tenants_under_real_rls(
    db: AsyncSession, tenant: Tenant, contact, other_tenant_ctx: dict,
) -> None:
    from app.models.lead import Lead, LeadSentiment, LeadSource, LeadStatus

    other_lead = Lead(
        branch_id=other_tenant_ctx["branch"].id, tenant_id=other_tenant_ctx["tenant"].id,
        wa_phone=f"+521{uuid.uuid4().hex[:10]}", name="Lead tenant B",
        status=LeadStatus.NUEVO, source=LeadSource.MANUAL, sentiment=LeadSentiment.NEUTRAL,
    )
    db.add(other_lead)
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    rows = {
        r.tenant_id: r.lead_count
        for r in (await db.execute(text("SELECT * FROM fn_platform_lead_counts_by_tenant()"))).fetchall()
    }
    assert rows.get(tenant.id, 0) >= 1  # `contact` fixture
    assert rows.get(other_tenant_ctx["tenant"].id, 0) >= 1


async def test_fn_platform_message_and_command_tokens_by_tenant_under_real_rls(
    db: AsyncSession, tenant: Tenant, branch: Branch, contact, owner_user,
) -> None:
    from app.models.ai_log import AICommandLog
    from app.models.conversation import Conversation, ConversationHandler, ConversationStatus, Message, MessageRole

    conv = Conversation(
        lead_id=contact.id, branch_id=branch.id,
        status=ConversationStatus.ACTIVE, current_handler=ConversationHandler.BOT,
    )
    db.add(conv)
    await db.flush()
    msg = Message(
        conversation_id=conv.id, role=MessageRole.ASSISTANT, content="hola",
        tokens_used=123,
    )
    log = AICommandLog(
        tenant_id=tenant.id, user_id=owner_user.id, message="prueba",
        intent_type="query", actions_taken={}, tokens_used=77,
    )
    db.add_all([msg, log])
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(hours=1)
    to_dt = now + timedelta(hours=1)

    msg_rows = {
        r.tenant_id: r.tokens
        for r in (await db.execute(
            text("SELECT * FROM fn_platform_message_tokens_by_tenant(:f, :t)"), {"f": from_dt, "t": to_dt}
        )).fetchall()
    }
    assert msg_rows.get(tenant.id, 0) >= 123

    cmd_rows = {
        r.tenant_id: r.tokens
        for r in (await db.execute(
            text("SELECT * FROM fn_platform_command_tokens_by_tenant(:f, :t)"), {"f": from_dt, "t": to_dt}
        )).fetchall()
    }
    assert cmd_rows.get(tenant.id, 0) >= 77


async def test_fn_platform_subscription_and_failed_payment_aggregates_under_real_rls(
    db: AsyncSession, tenant: Tenant,
) -> None:
    sub = Subscription(
        tenant_id=tenant.id, stripe_customer_id=f"cus_{uuid.uuid4().hex[:14]}",
        plan="growth", status="active",
    )
    fp = FailedPayment(tenant_id=tenant.id, stripe_invoice_id=f"in_{uuid.uuid4().hex[:14]}")
    db.add_all([sub, fp])
    await db.flush()

    await impersonate_walix_app_or_skip(db)

    plans = [
        r[0] for r in (await db.execute(text("SELECT * FROM fn_platform_list_active_subscription_plans()"))).fetchall()
    ]
    assert "growth" in plans

    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = (
        await db.execute(text("SELECT fn_platform_count_failed_payments_since(:since)"), {"since": since})
    ).scalar_one()
    assert count >= 1
