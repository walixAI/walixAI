"""TrialGuardMiddleware — blocks expired trial tenants (Sprint 9).

Runs AFTER TenantContextMiddleware (which sets request.state.tenant_id).

Rules:
  - If tenant.plan == "trial" AND trial_ends_at < now → 402 Payment Required
  - Any other plan → always allowed
  - Whitelisted paths always pass regardless of trial status

Whitelist (never blocked):
  /health
  /api/auth/*       (login, register, check-email, me)
  /api/tenant/trial-status
  /api/v1/billing/*
  /api/v2/auth/*
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_WHITELIST_PREFIXES = (
    "/health",
    "/api/auth/",
    "/api/v2/auth/",
    "/api/tenant/trial-status",
    "/api/v1/billing/",
    "/api/webhooks/stripe",   # Stripe sends no JWT — no tenant context
    "/",                      # root probe
)


def _is_whitelisted(path: str) -> bool:
    for prefix in _WHITELIST_PREFIXES:
        if path == prefix or path.startswith(prefix):
            return True
    return False


class TrialGuardMiddleware(BaseHTTPMiddleware):
    """Return 402 for requests from tenants with an expired trial."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_whitelisted(request.url.path):
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id or tenant_id == "00000000-0000-0000-0000-000000000000":
            return await call_next(request)

        # Lazy DB import to avoid circular deps at module load time
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.tenant import Tenant, TenantPlan

            async with AsyncSessionLocal() as db:
                from uuid import UUID
                tenant = await db.get(Tenant, UUID(tenant_id))

            if tenant is None:
                return await call_next(request)

            plan_value = getattr(tenant.plan, "value", str(tenant.plan))
            if plan_value != TenantPlan.TRIAL.value:
                return await call_next(request)

            if tenant.trial_ends_at is None:
                return await call_next(request)

            ends = tenant.trial_ends_at
            if ends.tzinfo is None:
                ends = ends.replace(tzinfo=timezone.utc)

            if ends > datetime.now(timezone.utc):
                return await call_next(request)

            # Trial has expired — block
            logger.info("trial_guard: blocked expired trial tenant=%s", tenant_id)
            body = json.dumps({
                "detail": "trial_expired",
                "trial_ends_at": ends.isoformat(),
            })
            return Response(
                content=body,
                status_code=402,
                media_type="application/json",
            )

        except Exception:
            logger.exception("trial_guard: error checking trial for tenant=%s", tenant_id)
            return await call_next(request)
