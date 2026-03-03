"""Graph memory operations for Nexus SDK."""

from __future__ import annotations

from typing import Any

import httpx


class Graph:
    """Synchronous graph memory operations."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def create_relationship(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relationship_type: str,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a relationship between two nodes.

        Args:
            source_type: Type of source node (memory, agent, capability)
            source_id: ID of source node
            target_type: Type of target node
            target_id: ID of target node
            relationship_type: Type of relationship (references, derived_from, related_to, etc.)
            weight: Relationship weight (0.0 to 1.0)
            metadata: Additional metadata

        Returns:
            Created relationship
        """
        response = self._client.post(
            "/graph/relationships",
            json={
                "source_type": source_type,
                "source_id": str(source_id),
                "target_type": target_type,
                "target_id": str(target_id),
                "relationship_type": relationship_type,
                "weight": weight,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return response.json()

    def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship. Returns True if deleted."""
        response = self._client.delete(f"/graph/relationships/{relationship_id}")
        return response.status_code in [200, 204]

    def get_edges(
        self,
        node_type: str,
        node_id: str,
        relationship_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        """
        Get edges for a node.

        Args:
            node_type: Type of node (memory, agent, capability)
            node_id: ID of the node
            relationship_type: Filter by relationship type
            direction: Edge direction (outgoing, incoming, both)

        Returns:
            List of edges
        """
        params: dict[str, Any] = {"direction": direction}
        if relationship_type:
            params["relationship_type"] = relationship_type

        response = self._client.get(
            f"/graph/nodes/{node_type}/{node_id}/edges",
            params=params,
        )
        response.raise_for_status()
        return response.json()["edges"]

    def traverse(
        self,
        start_type: str,
        start_id: str,
        max_depth: int = 2,
        relationship_types: list[str] | None = None,
        target_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Traverse the graph from a starting node.

        Args:
            start_type: Type of starting node
            start_id: ID of starting node
            max_depth: Maximum traversal depth (1-5)
            relationship_types: Filter by relationship types
            target_types: Filter by target node types

        Returns:
            Traversal result with nodes and edges
        """
        response = self._client.post(
            "/graph/traverse",
            json={
                "start_type": start_type,
                "start_id": str(start_id),
                "max_depth": max_depth,
                "relationship_types": relationship_types,
                "target_types": target_types,
            },
        )
        response.raise_for_status()
        return response.json()

    def find_path(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """
        Find shortest path between two nodes.

        Args:
            from_type: Source node type
            from_id: Source node ID
            to_type: Target node type
            to_id: Target node ID
            max_depth: Maximum path length

        Returns:
            Path result with nodes and edges
        """
        response = self._client.post(
            "/graph/path",
            json={
                "from_type": from_type,
                "from_id": str(from_id),
                "to_type": to_type,
                "to_id": str(to_id),
                "max_depth": max_depth,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_related_memories(
        self,
        memory_id: str,
        relationship_types: list[str] | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """
        Get memories related to a given memory.

        Args:
            memory_id: Source memory ID
            relationship_types: Filter by relationship types
            max_depth: How many hops to traverse

        Returns:
            List of related memories with relationship info
        """
        params: dict[str, Any] = {"max_depth": max_depth}
        if relationship_types:
            params["relationship_types"] = relationship_types

        response = self._client.get(
            f"/graph/memories/{memory_id}/related",
            params=params,
        )
        response.raise_for_status()
        return response.json()["memories"]


class GraphAsync:
    """Asynchronous graph memory operations."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def create_relationship(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relationship_type: str,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a relationship between two nodes."""
        response = await self._client.post(
            "/graph/relationships",
            json={
                "source_type": source_type,
                "source_id": str(source_id),
                "target_type": target_type,
                "target_id": str(target_id),
                "relationship_type": relationship_type,
                "weight": weight,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return response.json()

    async def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship."""
        response = await self._client.delete(f"/graph/relationships/{relationship_id}")
        return response.status_code in [200, 204]

    async def get_edges(
        self,
        node_type: str,
        node_id: str,
        relationship_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        """Get edges for a node."""
        params: dict[str, Any] = {"direction": direction}
        if relationship_type:
            params["relationship_type"] = relationship_type

        response = await self._client.get(
            f"/graph/nodes/{node_type}/{node_id}/edges",
            params=params,
        )
        response.raise_for_status()
        return response.json()["edges"]

    async def traverse(
        self,
        start_type: str,
        start_id: str,
        max_depth: int = 2,
        relationship_types: list[str] | None = None,
        target_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Traverse the graph from a starting node."""
        response = await self._client.post(
            "/graph/traverse",
            json={
                "start_type": start_type,
                "start_id": str(start_id),
                "max_depth": max_depth,
                "relationship_types": relationship_types,
                "target_types": target_types,
            },
        )
        response.raise_for_status()
        return response.json()

    async def find_path(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Find shortest path between two nodes."""
        response = await self._client.post(
            "/graph/path",
            json={
                "from_type": from_type,
                "from_id": str(from_id),
                "to_type": to_type,
                "to_id": str(to_id),
                "max_depth": max_depth,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_related_memories(
        self,
        memory_id: str,
        relationship_types: list[str] | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Get memories related to a given memory."""
        params: dict[str, Any] = {"max_depth": max_depth}
        if relationship_types:
            params["relationship_types"] = relationship_types

        response = await self._client.get(
            f"/graph/memories/{memory_id}/related",
            params=params,
        )
        response.raise_for_status()
        return response.json()["memories"]
