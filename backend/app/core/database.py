from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_NULL_UUID = "00000000-0000-0000-0000-000000000000"


# DATABASE_URL in .env uses the sync scheme (postgresql://). SQLAlchemy's async
# engine needs the asyncpg driver — rewrite the scheme so Alembic can keep
# using the sync URL as-is if needed later.
def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


engine = create_async_engine(
    _async_url(settings.effective_database_url),
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        tenant_id = getattr(request.state, "tenant_id", _NULL_UUID)
        # is_local=FALSE so the setting survives commit() calls within the
        # same request (e.g. register: commit() then refresh()). The middleware
        # sets a fresh value on the next request, and connections returned to
        # the pool will be overwritten before use.
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, FALSE)"),
            {"tid": str(tenant_id)},
        )
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: object) -> None:
    """Sets app.current_tenant_id on an already-open session, mid-request.

    For "pre-tenant" flows that resolve the tenant themselves instead of via
    TenantContextMiddleware + get_db (which needs a JWT that doesn't exist
    yet): login/register/check-email resolve it by email via
    fn_lookup_tenant_by_email, and the WhatsApp webhook resolves it by
    wa_phone_number_id via fn_lookup_tenant_by_wa_phone_id — both SECURITY
    DEFINER functions from migration l7m8n9o0p1q2 that run outside RLS on
    purpose, scoped to return only a tenant_id. Call this right after
    resolving tenant_id and BEFORE any further query against an
    RLS-protected table in the same session.
    """
    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, FALSE)"),
        {"tid": str(tenant_id)},
    )
