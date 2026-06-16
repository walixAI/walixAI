"""Billing API — Stripe-backed subscription management for Walix tenants (Sprint 10).

Routes (prefix /api/v1/billing):
  GET  /plans                       — public, no auth
  POST /create-checkout-session     — auth required
  GET  /subscription                — auth required
  POST /cancel                      — auth required
  POST /reactivate                  — auth required
  POST /portal                      — auth required

All Stripe operations return 503 if STRIPE_SECRET_KEY is not configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.subscription import Subscription
from app.models.tenant import Tenant, TenantPlan
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/billing", tags=["billing"])

# ── Plan catalogue ────────────────────────────────────────────────────────────

PLAN_CATALOGUE = [
    {
        "key": "starter",
        "name": "Starter",
        "price_mxn": 699,
        "price_id_key": "STRIPE_PRICE_STARTER",
        "features": [
            "3 usuarios",
            "1 sucursal",
            "500 leads/mes",
            "Bot WhatsApp",
            "Pipeline Kanban",
        ],
        "highlighted": False,
    },
    {
        "key": "growth",
        "name": "Growth",
        "price_mxn": 1499,
        "price_id_key": "STRIPE_PRICE_GROWTH",
        "features": [
            "10 usuarios",
            "3 sucursales",
            "2,000 leads/mes",
            "Agentes IA",
            "Métricas avanzadas",
        ],
        "highlighted": True,
    },
    {
        "key": "business",
        "name": "Business",
        "price_mxn": 2999,
        "price_id_key": "STRIPE_PRICE_BUSINESS",
        "features": [
            "Usuarios ilimitados",
            "Sucursales ilimitadas",
            "Leads ilimitados",
            "API access",
            "Onboarding dedicado",
            "SLA 99.9%",
        ],
        "highlighted": False,
    },
]

PLAN_PRICE_MAP: dict[str, int] = {p["key"]: p["price_mxn"] for p in PLAN_CATALOGUE}

VALID_PLANS = {p["key"] for p in PLAN_CATALOGUE}


def _price_id(key: str) -> str | None:
    mapping = {
        "starter": settings.STRIPE_PRICE_STARTER,
        "growth":  settings.STRIPE_PRICE_GROWTH,
        "business": settings.STRIPE_PRICE_BUSINESS,
    }
    return mapping.get(key)


def _plan_from_price_id(price_id: str) -> str | None:
    """Reverse-map a Stripe price_id to a Walix plan key."""
    mapping = {
        settings.STRIPE_PRICE_STARTER: "starter",
        settings.STRIPE_PRICE_GROWTH:  "growth",
        settings.STRIPE_PRICE_BUSINESS: "business",
    }
    return mapping.get(price_id)


def _stripe_client() -> stripe.StripeClient:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe no está configurado en este entorno",
        )
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


async def _require_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.OWNER, UserRole.PLATFORM_OWNER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el owner puede gestionar billing")
    return current_user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/plans")
async def get_plans() -> list[dict]:
    """Return available plans with Stripe Price IDs. No auth required."""
    return [
        {
            "key": p["key"],
            "name": p["name"],
            "price_mxn": p["price_mxn"],
            "price_id": _price_id(p["key"]),
            "features": p["features"],
            "highlighted": p["highlighted"],
        }
        for p in PLAN_CATALOGUE
    ]


class CheckoutRequest(BaseModel):
    plan: str


@router.post("/create-checkout-session")
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: User = Depends(_require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a Stripe Checkout Session for the requested plan."""
    if body.plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"Plan inválido: {body.plan}")

    price_id = _price_id(body.plan)
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Stripe Price ID para '{body.plan}' no configurado")

    client = _stripe_client()
    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    # Ensure Stripe customer exists
    if not tenant.stripe_customer_id:
        customer = client.customers.create(params={
            "email": tenant.email,
            "name":  tenant.name,
            "metadata": {"tenant_id": str(tenant.id)},
        })
        tenant.stripe_customer_id = customer.id
        await db.commit()

    frontend = settings.FRONTEND_URL.rstrip("/")
    session = client.checkout.sessions.create(params={
        "customer":   tenant.stripe_customer_id,
        "line_items": [{"price": price_id, "quantity": 1}],
        "mode":       "subscription",
        "success_url": f"{frontend}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url":  f"{frontend}/billing",
        "metadata": {
            "tenant_id": str(tenant.id),
            "plan":      body.plan,
        },
    })
    return {"checkout_url": session.url}


class SubscriptionOut(BaseModel):
    plan: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    days_until_renewal: int


@router.get("/subscription", response_model=SubscriptionOut)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    """Return current subscription status for the tenant."""
    tenant = await db.get(Tenant, current_user.tenant_id)
    plan_value = getattr(tenant.plan, "value", str(tenant.plan)) if tenant else "trial"

    sub_result = await db.execute(
        select(Subscription)
        .where(
            Subscription.tenant_id == current_user.tenant_id,
            Subscription.status.in_(["active", "past_due", "trialing"]),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = sub_result.scalar_one_or_none()

    days_until_renewal = 0
    if sub and sub.current_period_end:
        ends = sub.current_period_end
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        days_until_renewal = max(0, (ends - datetime.now(timezone.utc)).days)

    return SubscriptionOut(
        plan=plan_value,
        status=sub.status if sub else "trialing",
        current_period_end=sub.current_period_end if sub else None,
        cancel_at_period_end=sub.cancel_at_period_end if sub else False,
        days_until_renewal=days_until_renewal,
    )


@router.post("/cancel")
async def cancel_subscription(
    current_user: User = Depends(_require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set cancel_at_period_end = True. Access continues until period end."""
    sub_result = await db.execute(
        select(Subscription).where(
            Subscription.tenant_id == current_user.tenant_id,
            Subscription.status == "active",
        ).order_by(Subscription.created_at.desc()).limit(1)
    )
    sub = sub_result.scalar_one_or_none()
    if sub is None or not sub.stripe_subscription_id:
        raise HTTPException(status_code=404, detail="No hay suscripción activa")

    client = _stripe_client()
    client.subscriptions.update(
        sub.stripe_subscription_id,
        params={"cancel_at_period_end": True},
    )
    sub.cancel_at_period_end = True
    await db.commit()

    period_end = sub.current_period_end
    date_str = period_end.date().isoformat() if period_end else "fin del período"
    return {"message": f"Suscripción cancelada. Acceso hasta {date_str}."}


@router.post("/reactivate")
async def reactivate_subscription(
    current_user: User = Depends(_require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove cancel_at_period_end flag to reactivate a pending cancellation."""
    sub_result = await db.execute(
        select(Subscription).where(
            Subscription.tenant_id == current_user.tenant_id,
            Subscription.status == "active",
            Subscription.cancel_at_period_end.is_(True),
        ).order_by(Subscription.created_at.desc()).limit(1)
    )
    sub = sub_result.scalar_one_or_none()
    if sub is None or not sub.stripe_subscription_id:
        raise HTTPException(status_code=404, detail="No hay suscripción pendiente de cancelación")

    client = _stripe_client()
    client.subscriptions.update(
        sub.stripe_subscription_id,
        params={"cancel_at_period_end": False},
    )
    sub.cancel_at_period_end = False
    await db.commit()
    return {"message": "Suscripción reactivada."}


@router.post("/portal")
async def customer_portal(
    current_user: User = Depends(_require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a Stripe Customer Portal session for billing self-service."""
    tenant = await db.get(Tenant, current_user.tenant_id)
    if tenant is None or not tenant.stripe_customer_id:
        raise HTTPException(status_code=404, detail="No hay customer de Stripe configurado")

    client = _stripe_client()
    frontend = settings.FRONTEND_URL.rstrip("/")
    session = client.billing_portal.sessions.create(params={
        "customer":   tenant.stripe_customer_id,
        "return_url": f"{frontend}/billing",
    })
    return {"portal_url": session.url}
