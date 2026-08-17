"""Stripe webhook handler — /api/webhooks/stripe (Sprint 10).

No JWT auth — Stripe signs requests with STRIPE_WEBHOOK_SECRET.
Idempotent: uses stripe_subscription_id as unique key to avoid double-processing.

Events handled:
  checkout.session.completed        → create Subscription, update Tenant.plan
  customer.subscription.updated     → sync Subscription fields + Tenant.plan
  customer.subscription.deleted     → cancel + downgrade Tenant to trial
  invoice.payment_failed            → log to failed_payments
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, set_tenant_context
from app.models.subscription import FailedPayment, Subscription
from app.models.tenant import Tenant, TenantPlan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks-stripe"])

# ── Plan key from price_id ────────────────────────────────────────────────────

def _plan_from_price(price_id: str | None) -> str | None:
    if not price_id:
        return None
    mapping = {
        settings.STRIPE_PRICE_STARTER:  "starter",
        settings.STRIPE_PRICE_GROWTH:   "growth",
        settings.STRIPE_PRICE_BUSINESS: "business",
    }
    return mapping.get(price_id)


def _utc_from_ts(ts: int | None) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/stripe")
async def stripe_webhook(request: Request) -> dict:
    """Receive and process Stripe webhook events."""
    if not settings.STRIPE_WEBHOOK_SECRET or not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning("stripe_webhook: invalid signature — %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    event_type = event["type"]
    event_data = event["data"]["object"]

    logger.info("stripe_webhook: received event=%s id=%s", event_type, event["id"])

    async with AsyncSessionLocal() as db:
        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(event_data, db)
        elif event_type == "customer.subscription.updated":
            await _handle_sub_updated(event_data, db)
        elif event_type == "customer.subscription.deleted":
            await _handle_sub_deleted(event_data, db)
        elif event_type == "invoice.payment_failed":
            await _handle_payment_failed(event_data, db)
        else:
            logger.debug("stripe_webhook: unhandled event type=%s", event_type)

        await db.commit()

    return {"received": True}


# ── Event handlers ────────────────────────────────────────────────────────────

async def _handle_checkout_completed(data: dict, db: AsyncSession) -> None:
    """checkout.session.completed: create or upsert Subscription, upgrade Tenant.plan."""
    metadata = data.get("metadata") or {}
    tenant_id_raw = metadata.get("tenant_id")
    plan = metadata.get("plan")
    stripe_customer_id = data.get("customer")
    stripe_sub_id = data.get("subscription")

    if not tenant_id_raw or not plan:
        logger.error("checkout.session.completed: missing tenant_id or plan in metadata")
        return

    try:
        tenant_id = uuid.UUID(tenant_id_raw)
    except ValueError:
        logger.error("checkout.session.completed: invalid tenant_id=%s", tenant_id_raw)
        return

    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        logger.error("checkout.session.completed: tenant %s not found", tenant_id)
        return

    # subscriptions tiene RLS (migración p1q2r3s4t5u6) — tenants no, así que
    # el db.get() de arriba no depende de esto, pero todo lo que sigue sí.
    await set_tenant_context(db, tenant_id)

    # Update Tenant
    if stripe_customer_id and not tenant.stripe_customer_id:
        tenant.stripe_customer_id = stripe_customer_id
    try:
        tenant.plan = TenantPlan(plan)
    except ValueError:
        logger.error("checkout.session.completed: unknown plan=%s", plan)

    # Upsert Subscription (idempotent on stripe_subscription_id)
    if stripe_sub_id:
        existing = (await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )).scalar_one_or_none()

        if existing is None:
            db.add(Subscription(
                tenant_id=tenant_id,
                stripe_customer_id=stripe_customer_id or "",
                stripe_subscription_id=stripe_sub_id,
                plan=plan,
                status="active",
            ))
        else:
            existing.plan = plan
            existing.status = "active"

    logger.info("checkout.session.completed: tenant=%s upgraded to plan=%s", tenant_id, plan)


async def _handle_sub_updated(data: dict, db: AsyncSession) -> None:
    """customer.subscription.updated: sync Subscription fields + Tenant.plan."""
    stripe_sub_id = data.get("id")
    if not stripe_sub_id:
        return

    # Resuelve el tenant PRIMERO vía Tenant.stripe_customer_id (tenants no
    # tiene RLS, siempre disponible en el payload de un subscription) —
    # subscriptions sí tiene RLS (migración p1q2r3s4t5u6), así que no se
    # puede buscar por stripe_subscription_id antes de saber el tenant.
    customer_id = data.get("customer", "")
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.stripe_customer_id == customer_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        logger.warning("sub.updated: no tenant for customer=%s", customer_id)
        return
    await set_tenant_context(db, tenant.id)

    sub = (await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )).scalar_one_or_none()

    if sub is None:
        # Sub created externally (e.g. Stripe CLI test) — create a stub
        sub = Subscription(
            tenant_id=tenant.id,
            stripe_customer_id=customer_id,
            stripe_subscription_id=stripe_sub_id,
        )
        db.add(sub)

    # Sync fields from Stripe payload
    price_id = (data.get("items", {}).get("data") or [{}])[0].get("price", {}).get("id")
    plan = _plan_from_price(price_id)

    sub.status = data.get("status", sub.status)
    sub.cancel_at_period_end = data.get("cancel_at_period_end", sub.cancel_at_period_end)
    sub.current_period_start = _utc_from_ts(data.get("current_period_start"))
    sub.current_period_end   = _utc_from_ts(data.get("current_period_end"))
    if data.get("canceled_at"):
        sub.canceled_at = _utc_from_ts(data["canceled_at"])
    if price_id:
        sub.stripe_price_id = price_id
    if plan:
        sub.plan = plan

    # Upgrade tenant plan if subscription is active
    if sub.status == "active" and plan:
        tenant = await db.get(Tenant, sub.tenant_id)
        if tenant:
            try:
                tenant.plan = TenantPlan(plan)
            except ValueError:
                pass

    logger.info("sub.updated: sub=%s status=%s plan=%s", stripe_sub_id, sub.status, plan)


async def _handle_sub_deleted(data: dict, db: AsyncSession) -> None:
    """customer.subscription.deleted: mark canceled, downgrade tenant to trial + 7d grace."""
    stripe_sub_id = data.get("id")
    if not stripe_sub_id:
        return

    # A diferencia de _handle_sub_updated (que puede necesitar crear un stub
    # y por eso sí depende de customer_id), una suscripción a BORRAR siempre
    # existe ya en `subscriptions`, con su propio tenant_id — no hace falta
    # (ni conviene) depender de que el payload de Stripe traiga `customer`.
    # fn_lookup_tenant_by_stripe_subscription_id resuelve el tenant SIN pasar
    # por RLS (todavía no lo conocemos).
    tenant_id = (await db.execute(
        text("SELECT fn_lookup_tenant_by_stripe_subscription_id(:sub_id)"),
        {"sub_id": stripe_sub_id},
    )).scalar_one_or_none()
    if tenant_id is None:
        logger.warning("sub.deleted: no subscription found for stripe_sub_id=%s", stripe_sub_id)
        return
    await set_tenant_context(db, tenant_id)

    sub = (await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )).scalar_one_or_none()

    if sub:
        sub.status = "canceled"
        sub.canceled_at = datetime.now(timezone.utc)

        tenant = await db.get(Tenant, sub.tenant_id)
        if tenant:
            tenant.plan = TenantPlan.TRIAL
            # 7-day grace period so the owner can renew without losing access immediately
            tenant.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=7)
            logger.info("sub.deleted: tenant=%s downgraded to trial (7d grace)", sub.tenant_id)


async def _handle_payment_failed(data: dict, db: AsyncSession) -> None:
    """invoice.payment_failed: log to failed_payments. Do NOT block access."""
    stripe_invoice_id = data.get("id", "")
    customer_id = data.get("customer", "")
    amount_due = data.get("amount_due", 0)  # in smallest currency unit (centavos)
    last_error = (data.get("last_payment_error") or {}).get("message", "")

    # Resolve tenant from stripe_customer_id
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.stripe_customer_id == customer_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    tenant_id = tenant.id if tenant else uuid.UUID(int=0)

    # failed_payments tiene RLS (migración p1q2r3s4t5u6).
    await set_tenant_context(db, tenant_id)

    db.add(FailedPayment(
        tenant_id=tenant_id,
        stripe_invoice_id=stripe_invoice_id,
        amount_mxn=amount_due // 100,  # convert centavos → MXN
        error=last_error or "Unknown error",
    ))
    logger.warning(
        "payment_failed: invoice=%s customer=%s amount_mxn=%s",
        stripe_invoice_id, customer_id, amount_due // 100,
    )
