"""Tests for graph memory module."""

import pytest
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.graph.models import MemoryRelationship, NodeType, RelationshipType


@pytest.mark.asyncio
async def test_create_relationship(authenticated_client: AsyncClient, test_memory):
    """Test creating a relationship between two memories."""
    # Create a second memory first
    response = await authenticated_client.post(
        "/api/v1/memory",
        json={
            "key": "related-memory",
            "value": {"data": "related data"},
        },
    )
    assert response.status_code == 200
    target_memory_id = response.json()["id"]

    # Create relationship
    response = await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "memory",
            "target_id": target_memory_id,
            "relationship_type": "references",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["source_type"] == "memory"
    assert data["target_type"] == "memory"
    assert data["relationship_type"] == "references"


@pytest.mark.asyncio
async def test_create_relationship_with_weight(authenticated_client: AsyncClient, test_memory):
    """Test creating a relationship with custom weight."""
    target_id = str(uuid4())

    response = await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "capability",
            "target_id": target_id,
            "relationship_type": "depends_on",
            "weight": 0.75,
        },
    )
    assert response.status_code == 200
    assert response.json()["weight"] == 0.75


@pytest.mark.asyncio
async def test_delete_relationship(authenticated_client: AsyncClient, db_session: AsyncSession, test_memory):
    """Test deleting a relationship."""
    # Create relationship first
    target_id = str(uuid4())
    response = await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "memory",
            "target_id": target_id,
            "relationship_type": "related_to",
        },
    )
    relationship_id = response.json()["id"]

    # Delete it
    response = await authenticated_client.delete(f"/api/v1/graph/relationships/{relationship_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_node_edges(authenticated_client: AsyncClient, test_memory):
    """Test retrieving edges for a node."""
    # Create a relationship
    target_id = str(uuid4())
    await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "memory",
            "target_id": target_id,
            "relationship_type": "references",
        },
    )

    # Get edges
    response = await authenticated_client.get(
        f"/api/v1/graph/nodes/memory/{test_memory.id}/edges"
    )
    assert response.status_code == 200

    data = response.json()
    assert "edges" in data
    assert len(data["edges"]) >= 1


@pytest.mark.asyncio
async def test_traverse_graph(authenticated_client: AsyncClient, test_memory):
    """Test graph traversal."""
    # Create a chain of relationships
    memory_ids = [str(test_memory.id)]
    for i in range(2):
        # Create memory
        response = await authenticated_client.post(
            "/api/v1/memory",
            json={"key": f"traverse-test-{i}", "value": {"step": i}},
        )
        memory_id = response.json()["id"]
        memory_ids.append(memory_id)

        # Create relationship
        await authenticated_client.post(
            "/api/v1/graph/relationships",
            json={
                "source_type": "memory",
                "source_id": memory_ids[-2],
                "target_type": "memory",
                "target_id": memory_id,
                "relationship_type": "derived_from",
            },
        )

    # Traverse
    response = await authenticated_client.post(
        "/api/v1/graph/traverse",
        json={
            "start_type": "memory",
            "start_id": str(test_memory.id),
            "max_depth": 3,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "nodes" in data


@pytest.mark.asyncio
async def test_get_related_memories(authenticated_client: AsyncClient, test_memory):
    """Test getting related memories."""
    # Create related memory
    response = await authenticated_client.post(
        "/api/v1/memory",
        json={"key": "related-test", "value": {"related": True}},
    )
    related_id = response.json()["id"]

    # Create relationship
    await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "memory",
            "target_id": related_id,
            "relationship_type": "related_to",
        },
    )

    # Get related
    response = await authenticated_client.get(
        f"/api/v1/graph/memories/{test_memory.id}/related"
    )
    assert response.status_code == 200

    data = response.json()
    assert "memories" in data


@pytest.mark.asyncio
async def test_find_shortest_path(authenticated_client: AsyncClient, test_memory):
    """Test finding shortest path between nodes."""
    # Create target memory
    response = await authenticated_client.post(
        "/api/v1/memory",
        json={"key": "path-target", "value": {"target": True}},
    )
    target_id = response.json()["id"]

    # Create relationship
    await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "memory",
            "target_id": target_id,
            "relationship_type": "references",
        },
    )

    # Find path
    response = await authenticated_client.post(
        "/api/v1/graph/path",
        json={
            "from_type": "memory",
            "from_id": str(test_memory.id),
            "to_type": "memory",
            "to_id": target_id,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "path" in data


@pytest.mark.asyncio
async def test_duplicate_relationship_upsert(authenticated_client: AsyncClient, test_memory):
    """Test that creating duplicate relationship updates weight."""
    target_id = str(uuid4())

    # Create first time
    response = await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "memory",
            "target_id": target_id,
            "relationship_type": "similar_to",
            "weight": 0.5,
        },
    )
    assert response.status_code == 200

    # Create again with different weight (should update)
    response = await authenticated_client.post(
        "/api/v1/graph/relationships",
        json={
            "source_type": "memory",
            "source_id": str(test_memory.id),
            "target_type": "memory",
            "target_id": target_id,
            "relationship_type": "similar_to",
            "weight": 0.9,
        },
    )
    assert response.status_code == 200
    assert response.json()["weight"] == 0.9
