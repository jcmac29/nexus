"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from nexus.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    # Import all models to register them with Base.metadata
    from nexus.identity.models import Agent, APIKey  # noqa: F401
    from nexus.memory.models import Memory, MemoryShare  # noqa: F401
    from nexus.discovery.models import Capability  # noqa: F401

    async with engine.begin() as conn:
        # Create pgvector extension if it doesn't exist
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Create enum types first
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE agentstatus AS ENUM ('active', 'suspended', 'deleted');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE memoryscope AS ENUM ('agent', 'user', 'session', 'shared');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE capabilitystatus AS ENUM ('active', 'inactive', 'deprecated');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))

        await conn.run_sync(Base.metadata.create_all)
