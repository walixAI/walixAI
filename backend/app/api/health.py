"""Enhanced health check — verifies PostgreSQL and Redis connectivity."""
import time
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class ComponentStatus(BaseModel):
    ok: bool
    response_ms: float
    error: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "error"
    response_ms: float
    components: dict[str, ComponentStatus]


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    start = time.monotonic()
    components: dict[str, ComponentStatus] = {}

    # PostgreSQL check
    pg_start = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        components["postgres"] = ComponentStatus(
            ok=True,
            response_ms=round((time.monotonic() - pg_start) * 1000, 2),
        )
    except Exception as exc:
        logger.warning("health: postgres check failed: %s", exc)
        components["postgres"] = ComponentStatus(
            ok=False,
            response_ms=round((time.monotonic() - pg_start) * 1000, 2),
            error=str(exc),
        )

    # Redis check
    redis_start = time.monotonic()
    try:
        await redis_client.ping()
        components["redis"] = ComponentStatus(
            ok=True,
            response_ms=round((time.monotonic() - redis_start) * 1000, 2),
        )
    except Exception as exc:
        logger.warning("health: redis check failed: %s", exc)
        components["redis"] = ComponentStatus(
            ok=False,
            response_ms=round((time.monotonic() - redis_start) * 1000, 2),
            error=str(exc),
        )

    all_ok = all(c.ok for c in components.values())
    status = "ok" if all_ok else "degraded"

    return HealthResponse(
        status=status,
        response_ms=round((time.monotonic() - start) * 1000, 2),
        components=components,
    )
