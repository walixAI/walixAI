"""TenantContextMiddleware — JWT → request.state.tenant_id.

Runs on every request before FastAPI dependency injection. Decodes the
Authorization Bearer token and stores tenant_id in request.state so that
get_db can set the PostgreSQL session variable that activates RLS policies.

Token variants handled:
  · New tokens (post-deploy): include 'tenant_id' claim → used directly.
  · Legacy tokens (only 'sub'): look up tenant_id from users table using a
    raw admin connection (one extra query per request, short-lived).
  · No token / invalid: request.state.tenant_id = NULL_UUID (matches nothing).

Note: background tasks that use AsyncSessionLocal() directly bypass this
middleware. They run as the admin DB user which is a superuser and bypasses
RLS automatically.
"""
from __future__ import annotations

import logging
from uuid import UUID

from jose import JWTError
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import verify_token

logger = logging.getLogger(__name__)

# UUID that no real tenant owns — ensures RLS denies everything when no valid
# tenant context is established.
NULL_UUID = "00000000-0000-0000-0000-000000000000"


async def _resolve_tenant_from_sub(user_id: str) -> str:
    """Look up tenant_id for a user. Used only for legacy tokens without tenant_id claim."""
    from app.core.database import engine  # lazy import avoids circular deps

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT tenant_id FROM users"
                    " WHERE id = :uid AND is_active = TRUE"
                    " LIMIT 1"
                ),
                {"uid": user_id},
            )
            row = result.fetchone()
            if row:
                return str(row[0])
    except Exception:
        logger.debug("tenant_context: could not resolve tenant for sub=%s", user_id)
    return NULL_UUID


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extract tenant_id from JWT and store in request.state.tenant_id."""

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = NULL_UUID

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            try:
                payload = verify_token(token)

                tid = payload.get("tenant_id")
                if tid:
                    # Preferred path: tenant_id embedded in token.
                    tenant_id = str(UUID(tid))
                else:
                    sub = payload.get("sub")
                    if sub:
                        # Legacy path: only user_id in token, resolve tenant via DB.
                        tenant_id = await _resolve_tenant_from_sub(sub)

            except (JWTError, ValueError, TypeError):
                pass  # invalid JWT — NULL_UUID stays, RLS will block all rows

        request.state.tenant_id = tenant_id
        return await call_next(request)
