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
