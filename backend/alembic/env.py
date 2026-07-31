import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.models.base import Base

# Import every model module so its tables register on Base.metadata
# before Alembic introspects it for autogenerate.
from app.models import conversation, knowledge, lead, tenant, user  # noqa: F401
from app.models import activity, meta_ads  # noqa: F401  # Sprint 3
from app.models import pipeline, onboarding  # noqa: F401  # Sprint 4
from app.models import alert, ai_log, support  # noqa: F401  # Sprint 5
from app.models import agent, scoring, metrics  # noqa: F401  # Sprint 6
from app.models import tag, failed_task  # noqa: F401  # Sprint 7 + Celery DLQ
from app.models import saved_view  # noqa: F401  # Sprint 8A
from app.models import deal, deal_stage_history, pipeline_group, subscription  # noqa: F401
from app.models import contact_activity  # noqa: F401
from app.models import ai_memory  # noqa: F401  # Etapa 6: AI entity memory
from app.models import finance  # noqa: F401  # Metas/Finanzas
from app.models import goals  # noqa: F401  # Metas Gen2

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


config.set_main_option("sqlalchemy.url", _async_url(settings.effective_database_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
