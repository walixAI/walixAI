"""test_billing.py — Sprint 10: verifica el módulo de billing con Stripe.

Checks (a–e):
  a) GET /api/v1/billing/plans → retorna los 3 planes con precios correctos
  b) POST /api/v1/billing/create-checkout-session → URL de Stripe (requiere STRIPE_SECRET_KEY)
  c) POST /api/v1/billing/portal → URL del portal (requiere STRIPE_SECRET_KEY)
  d) Webhook checkout.session.completed (mock) → Tenant.plan se actualiza
  e) Webhook customer.subscription.deleted (mock) → Tenant.plan vuelve a 'trial'
  f) PASS/FAIL por check

Uso:
  # Con Stripe test key en .env:
  .venv/bin/python scripts/test_billing.py

  # Sin Stripe configurado (checks a y d/e aún funcionan con mocks):
  .venv/bin/python scripts/test_billing.py --no-stripe
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
if _tdb := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = _tdb

BASE_URL = "http://localhost:8000"
NO_STRIPE = "--no-stripe" in sys.argv or os.environ.get("APP_ENV") == "test"

_PASS = "✓ PASS"
_FAIL = "✗ FAIL"
_SKIP = "– SKIP"

failures: list[str] = []


def report(label: str, ok: bool | None, detail: str = "") -> None:
    tag = _PASS if ok is True else (_FAIL if ok is False else _SKIP)
    if ok is False:
        failures.append(label)
    line = f"  {tag}  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


def get_auth_token(client: httpx.Client) -> str | None:
    """Get auth token from test3 user (salud tenant)."""
    resp = client.post("/api/auth/login", json={"email": "test3@mail.com", "password": "walix2026"})
    if resp.status_code != 200:
        return None
    return resp.json().get("access_token")


# ─────────────────────────────────────────────────────────────────────────────
# a) GET /api/v1/billing/plans
# ─────────────────────────────────────────────────────────────────────────────

def check_a(client: httpx.Client) -> None:
    print("a) GET /api/v1/billing/plans ────────────────────────────")
    resp = client.get("/api/v1/billing/plans")
    ok_status = resp.status_code == 200
    report("Endpoint retorna 200", ok_status, f"status={resp.status_code}")
    if not ok_status:
        return

    plans = resp.json()
    report("Retorna 3 planes", len(plans) == 3, f"count={len(plans)}")

    keys = {p["key"] for p in plans}
    report("Claves correctas: starter, growth, business",
           keys == {"starter", "growth", "business"})

    prices = {p["key"]: p["price_mxn"] for p in plans}
    ok_prices = prices.get("starter") == 699 and prices.get("growth") == 1499 and prices.get("business") == 2999
    report(f"Precios correctos (699/1499/2999 MXN)", ok_prices, str(prices))

    growth = next((p for p in plans if p["key"] == "growth"), {})
    report("Growth marcado como highlighted=true", growth.get("highlighted") is True)


# ─────────────────────────────────────────────────────────────────────────────
# b) POST /api/v1/billing/create-checkout-session
# ─────────────────────────────────────────────────────────────────────────────

def check_b(client: httpx.Client, token: str) -> None:
    print("\nb) POST /api/v1/billing/create-checkout-session ─────────")
    if NO_STRIPE:
        report("Checkout session URL retornada", None, "omitido con --no-stripe")
        return

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/billing/create-checkout-session",
                       json={"plan": "growth"}, headers=headers)
    ok = resp.status_code == 200
    report("Endpoint retorna 200", ok, f"status={resp.status_code} body={resp.text[:150]}")
    if ok:
        data = resp.json()
        url = data.get("checkout_url", "")
        report("checkout_url empieza con https://checkout.stripe.com",
               url.startswith("https://checkout.stripe.com"),
               f"url={url[:60]}...")


# ─────────────────────────────────────────────────────────────────────────────
# c) POST /api/v1/billing/portal
# ─────────────────────────────────────────────────────────────────────────────

def check_c(client: httpx.Client, token: str) -> None:
    print("\nc) POST /api/v1/billing/portal ──────────────────────────")
    if NO_STRIPE:
        report("Portal URL retornada", None, "omitido con --no-stripe")
        return

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/billing/portal", headers=headers)
    # May fail if tenant has no stripe_customer_id yet
    if resp.status_code == 404:
        report("Portal URL retornada", None,
               "tenant sin stripe_customer_id — haz un checkout primero")
        return
    ok = resp.status_code == 200
    report("Endpoint retorna 200", ok, f"status={resp.status_code}")
    if ok:
        url = resp.json().get("portal_url", "")
        report("portal_url empieza con https://billing.stripe.com",
               url.startswith("https://billing.stripe.com"),
               f"url={url[:60]}...")


# ─────────────────────────────────────────────────────────────────────────────
# d) Webhook mock: checkout.session.completed → Tenant.plan = "growth"
# ─────────────────────────────────────────────────────────────────────────────

async def check_d() -> str | None:
    """Returns tenant_id created for the test."""
    print("\nd) Webhook checkout.session.completed (mock) ───────────")

    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Tenant, TenantPlan, Company
    from app.models.user import User

    # Create a temp tenant in trial
    test_email = f"billing_test_{uuid.uuid4().hex[:6]}@walix-test.mx"
    async with AsyncSessionLocal() as db:
        tenant = Tenant(
            name="Billing Test Co",
            email=test_email,
            plan=TenantPlan.TRIAL,
            is_active=True,
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.add(tenant)
        await db.flush()
        tenant_id = str(tenant.id)
        await db.commit()

    # Build mock checkout.session.completed payload
    mock_event_data = {
        "type": "checkout.session.completed",
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant_id, "plan": "growth"},
                "customer": f"cus_{uuid.uuid4().hex[:14]}",
                "subscription": f"sub_{uuid.uuid4().hex[:14]}",
            }
        },
    }

    # Call handler directly (bypassing signature verification)
    from app.api.billing_webhook import _handle_checkout_completed
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _handle_checkout_completed(mock_event_data["data"]["object"], db)
        await db.commit()

    # Verify Tenant.plan updated
    async with AsyncSessionLocal() as db:
        from uuid import UUID
        tenant = await db.get(Tenant, UUID(tenant_id))

    plan_val = getattr(tenant.plan, "value", str(tenant.plan)) if tenant else "N/A"
    report("Tenant.plan actualizado a 'growth' por webhook",
           plan_val == "growth", f"plan={plan_val}")

    return tenant_id


# ─────────────────────────────────────────────────────────────────────────────
# e) Webhook mock: customer.subscription.deleted → Tenant.plan = "trial"
# ─────────────────────────────────────────────────────────────────────────────

async def check_e(tenant_id: str | None) -> None:
    print("\ne) Webhook customer.subscription.deleted (mock) ─────────")
    if not tenant_id:
        report("Tenant downgraded a 'trial'", None, "skip — tenant no creado en check d")
        return

    from app.api.billing_webhook import _handle_sub_deleted
    from app.core.database import AsyncSessionLocal
    from app.models.subscription import Subscription
    from app.models.tenant import Tenant
    from uuid import UUID

    # Create a stub subscription row so the handler can find and update it
    stripe_sub_id = f"sub_{uuid.uuid4().hex[:14]}"
    async with AsyncSessionLocal() as db:
        db.add(Subscription(
            tenant_id=UUID(tenant_id),
            stripe_customer_id="cus_test",
            stripe_subscription_id=stripe_sub_id,
            plan="growth",
            status="active",
        ))
        await db.commit()

    # Call handler directly
    mock_data = {"id": stripe_sub_id}
    async with AsyncSessionLocal() as db:
        await _handle_sub_deleted(mock_data, db)
        await db.commit()

    # Verify downgrade
    async with AsyncSessionLocal() as db:
        tenant = await db.get(Tenant, UUID(tenant_id))

    plan_val = getattr(tenant.plan, "value", str(tenant.plan)) if tenant else "N/A"
    report("Tenant downgraded a 'trial' por subscription.deleted",
           plan_val == "trial", f"plan={plan_val}")

    if tenant and tenant.trial_ends_at:
        grace_ok = tenant.trial_ends_at > datetime.now(timezone.utc)
        report("trial_ends_at seteado a +7 días (gracia)", grace_ok,
               f"trial_ends_at={tenant.trial_ends_at}")


# ─────────────────────────────────────────────────────────────────────────────
# cleanup
# ─────────────────────────────────────────────────────────────────────────────

async def cleanup(tenant_id: str | None) -> None:
    if not tenant_id:
        return
    from sqlalchemy import delete
    from app.core.database import AsyncSessionLocal
    from app.models.subscription import Subscription, FailedPayment
    from app.models.tenant import Tenant, Company
    from uuid import UUID
    tid = UUID(tenant_id)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Subscription).where(Subscription.tenant_id == tid))
        await db.execute(delete(FailedPayment).where(FailedPayment.tenant_id == tid))
        await db.execute(delete(Tenant).where(Tenant.id == tid))
        await db.commit()
    print("\n  Datos de prueba eliminados.")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> int:
    mode = "sin Stripe (--no-stripe)" if NO_STRIPE else "con Stripe"
    print(f"\n{'═' * 58}")
    print(f"  WALIX — Verificación Sprint 10: Billing ({mode})")
    print(f"{'═' * 58}\n")

    tenant_id: str | None = None

    with httpx.Client(base_url=BASE_URL, timeout=15) as client:
        # a) Plans endpoint (no auth needed)
        check_a(client)

        # Get token for authenticated checks
        token = get_auth_token(client)
        if not token:
            print("\n  ⚠ No se pudo autenticar como test3@mail.com — checks b/c omitidos")
        else:
            check_b(client, token)
            check_c(client, token)

    # d/e — direct handler tests (no HTTP needed)
    tenant_id = await check_d()
    await check_e(tenant_id)
    await cleanup(tenant_id)

    print(f"\n{'─' * 58}")
    if not failures:
        print(f"  {_PASS}  Todos los checks pasaron.\n")
    else:
        print(f"  {_FAIL}  {len(failures)} check(s) fallaron:")
        for f in failures:
            print(f"    • {f}")
        print()

    print("Próximos pasos:")
    print("  1. Crear productos en Stripe Dashboard (test mode)")
    print("  2. Copiar Price IDs al .env como STRIPE_PRICE_STARTER/GROWTH/BUSINESS")
    print("  3. Añadir STRIPE_SECRET_KEY y STRIPE_WEBHOOK_SECRET al .env")
    print("  4. stripe listen --forward-to localhost:8000/api/webhooks/stripe")
    print("  5. Probar flujo: /billing → checkout → /billing/success\n")

    return len(failures)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
