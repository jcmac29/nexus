"""Alembic environment configuration."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models so they're registered with Base
from nexus.database import Base
from nexus.config import get_settings

# Import all model modules to register them
from nexus.identity import models as identity_models  # noqa: F401
from nexus.memory import models as memory_models  # noqa: F401
from nexus.discovery import models as discovery_models  # noqa: F401
from nexus.billing import models as billing_models  # noqa: F401
from nexus.messaging import models as messaging_models  # noqa: F401
from nexus.webhooks import models as webhook_models  # noqa: F401
from nexus.workflows import models as workflow_models  # noqa: F401
from nexus.analytics import models as analytics_models  # noqa: F401
from nexus.ratelimit import models as ratelimit_models  # noqa: F401
from nexus.health import models as health_models  # noqa: F401
from nexus.marketplace import models as marketplace_models  # noqa: F401
from nexus.teams import models as teams_models  # noqa: F401
from nexus.media import models as media_models  # noqa: F401
from nexus.federation import models as federation_models  # noqa: F401
from nexus.public import models as public_models  # noqa: F401
from nexus.profiles import models as profile_models  # noqa: F401
from nexus.oauth import models as oauth_models  # noqa: F401
from nexus.audit import models as audit_models  # noqa: F401
from nexus.conversations import models as conversation_models  # noqa: F401
from nexus.tools import models as tools_models  # noqa: F401
from nexus.events import models as events_models  # noqa: F401
from nexus.orchestration import models as orchestration_models  # noqa: F401
from nexus.scheduling import models as scheduling_models  # noqa: F401
from nexus.queues import models as queues_models  # noqa: F401
from nexus.connectors import models as connectors_models  # noqa: F401
from nexus.tracing import models as tracing_models  # noqa: F401
from nexus.phone import models as phone_models  # noqa: F401
from nexus.sms import models as sms_models  # noqa: F401
from nexus.email import models as email_models  # noqa: F401
from nexus.video import models as video_models  # noqa: F401
from nexus.notifications import models as notification_models  # noqa: F401
from nexus.chat import models as chat_models  # noqa: F401
from nexus.calendar import models as calendar_models  # noqa: F401
from nexus.documents import models as document_models  # noqa: F401
from nexus.devices import models as device_models  # noqa: F401
from nexus.jobs import models as job_models  # noqa: F401
from nexus.search import models as search_models  # noqa: F401
from nexus.graph import models as graph_models  # noqa: F401
from nexus.tenants import models as tenant_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for 'autogenerate' support
target_metadata = Base.metadata

# Get database URL from settings
settings = get_settings()


def get_url() -> str:
    """Get database URL from settings."""
    return settings.database_url.replace("+asyncpg", "+psycopg2")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
