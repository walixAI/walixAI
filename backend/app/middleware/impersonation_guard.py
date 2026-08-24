"""ImpersonationReadOnlyMiddleware — blocks writes during platform_owner
impersonation (hallazgo #9, docs/PERMISSIONS_DRIFT_BACKLOG.md).

An impersonation token (see app/api/platform.py::impersonate_tenant) carries
read_only_impersonation=True. That claim was previously emitted but never
validated anywhere — this middleware is the guardrail: any non-safe HTTP
method (anything other than GET/HEAD/OPTIONS) on an impersonation token is
rejected with 403 before it reaches routing/get_current_user.

Follows the same JWT-decoding pattern as TenantContextMiddleware: decodes
the Bearer token itself (no dependency on get_current_user having run yet),
and treats an unparseable/missing token as "not blocking" — that case is
already handled downstream by get_current_user's own 401.
"""
from __future__ import annotations

import json
import logging

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import verify_token

logger = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class ImpersonationReadOnlyMiddleware(BaseHTTPMiddleware):
    """Return 403 for non-safe methods on a read-only impersonation token."""

    async def dispatch(self, request: Request, call_next) -> Response:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and request.method not in _SAFE_METHODS:
            token = auth[7:]
            try:
                payload = verify_token(token)
            except (JWTError, ValueError, TypeError):
                # Unparseable token — not this middleware's job; get_current_user
                # will 401 further down the chain.
                return await call_next(request)

            if payload.get("read_only_impersonation") is True:
                logger.info(
                    "impersonation_guard: blocked %s %s during read-only impersonation",
                    request.method, request.url.path,
                )
                body = json.dumps({"detail": "Esta sesión de impersonación es de solo lectura."})
                return Response(
                    content=body,
                    status_code=403,
                    media_type="application/json",
                )

        return await call_next(request)
