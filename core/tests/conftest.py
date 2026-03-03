"""Pytest configuration and fixtures for Nexus tests."""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from nexus.database import Base, get_async_session
from nexus.config import get_settings
from nexus.main import app


# Test database URL
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_test"
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    """Create an authenticated test client."""
    from nexus.identity.service import IdentityService

    # Create a test agent
    service = IdentityService(db_session)
    agent = await service.register_agent(
        name="test-agent",
        version="1.0.0",
        description="Test agent for automated tests",
        capabilities=["test"],
    )
    await db_session.commit()

    # Add auth header
    client.headers["Authorization"] = f"Bearer {agent.api_key}"
    client.headers["X-Agent-ID"] = str(agent.id)

    return client


@pytest.fixture
def settings():
    """Get test settings."""
    return get_settings()


# --- Helper fixtures ---

@pytest_asyncio.fixture
async def test_agent(db_session: AsyncSession):
    """Create a test agent."""
    from nexus.identity.service import IdentityService

    service = IdentityService(db_session)
    agent = await service.register_agent(
        name="test-agent",
        version="1.0.0",
        description="Test agent",
        capabilities=["general"],
    )
    await db_session.commit()
    return agent


@pytest_asyncio.fixture
async def test_memory(db_session: AsyncSession, test_agent):
    """Create test memory for an agent."""
    from nexus.memory.models import Memory

    memory = Memory(
        agent_id=test_agent.id,
        key="test-key",
        value={"data": "test value"},
        memory_type="test",
    )
    db_session.add(memory)
    await db_session.commit()
    return memory


@pytest_asyncio.fixture
async def test_webhook(db_session: AsyncSession, test_agent):
    """Create a test webhook endpoint."""
    from nexus.webhooks.models import WebhookEndpoint
    import secrets

    webhook = WebhookEndpoint(
        agent_id=test_agent.id,
        name="Test Webhook",
        url="https://httpbin.org/post",
        secret=secrets.token_urlsafe(32),
        event_types=["memory.*", "agent.*"],
    )
    db_session.add(webhook)
    await db_session.commit()
    return webhook


@pytest_asyncio.fixture
async def test_relationship(db_session: AsyncSession, test_agent, test_memory):
    """Create a test graph relationship."""
    from nexus.graph.models import MemoryRelationship, NodeType, RelationshipType
    from uuid import uuid4

    relationship = MemoryRelationship(
        source_type=NodeType.MEMORY,
        source_id=test_memory.id,
        target_type=NodeType.MEMORY,
        target_id=uuid4(),
        relationship_type=RelationshipType.REFERENCES,
        created_by_agent_id=test_agent.id,
    )
    db_session.add(relationship)
    await db_session.commit()
    return relationship
