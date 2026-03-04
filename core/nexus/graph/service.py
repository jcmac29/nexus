"""Graph service for relationship management and traversal."""

from uuid import UUID

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.graph.models import MemoryRelationship, NodeType, RelationshipType


class GraphService:
    """Service for managing graph relationships and traversals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_relationship(
        self,
        source_type: NodeType,
        source_id: UUID,
        target_type: NodeType,
        target_id: UUID,
        relationship_type: RelationshipType,
        weight: float = 1.0,
        metadata: dict | None = None,
        created_by_agent_id: UUID | None = None,
    ) -> MemoryRelationship:
        """
        Create a relationship between two nodes.

        Uses upsert semantics - updates weight/metadata if relationship exists.
        """
        # Check if relationship already exists
        stmt = select(MemoryRelationship).where(
            and_(
                MemoryRelationship.source_type == source_type,
                MemoryRelationship.source_id == source_id,
                MemoryRelationship.target_type == target_type,
                MemoryRelationship.target_id == target_id,
                MemoryRelationship.relationship_type == relationship_type,
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing relationship
            existing.weight = weight
            if metadata:
                existing.metadata_ = {**existing.metadata_, **metadata}
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        # Create new relationship
        relationship = MemoryRelationship(
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relationship_type=relationship_type,
            weight=weight,
            metadata_=metadata or {},
            created_by_agent_id=created_by_agent_id,
        )
        self.db.add(relationship)
        await self.db.commit()
        await self.db.refresh(relationship)
        return relationship

    async def get_relationship(self, relationship_id: UUID) -> MemoryRelationship | None:
        """Get a relationship by ID."""
        stmt = select(MemoryRelationship).where(MemoryRelationship.id == relationship_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_relationship(
        self,
        relationship_id: UUID,
        agent_id: UUID | None = None,
    ) -> bool:
        """
        Delete a relationship by ID.

        If agent_id is provided, only delete if created by that agent.
        """
        conditions = [MemoryRelationship.id == relationship_id]
        if agent_id:
            conditions.append(MemoryRelationship.created_by_agent_id == agent_id)

        stmt = delete(MemoryRelationship).where(and_(*conditions))
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def get_edges(
        self,
        node_type: NodeType,
        node_id: UUID,
        direction: str = "both",
        relationship_types: list[RelationshipType] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[tuple[MemoryRelationship, str]], int]:
        """
        Get all edges connected to a node.

        Returns tuples of (relationship, direction) where direction is 'outgoing' or 'incoming'.
        """
        edges = []

        # Build base conditions
        type_filter = []
        if relationship_types:
            type_filter = [MemoryRelationship.relationship_type.in_(relationship_types)]

        # Outgoing edges
        if direction in ("outgoing", "both"):
            stmt = select(MemoryRelationship).where(
                and_(
                    MemoryRelationship.source_type == node_type,
                    MemoryRelationship.source_id == node_id,
                    *type_filter,
                )
            )
            result = await self.db.execute(stmt)
            for rel in result.scalars().all():
                edges.append((rel, "outgoing"))

        # Incoming edges
        if direction in ("incoming", "both"):
            stmt = select(MemoryRelationship).where(
                and_(
                    MemoryRelationship.target_type == node_type,
                    MemoryRelationship.target_id == node_id,
                    *type_filter,
                )
            )
            result = await self.db.execute(stmt)
            for rel in result.scalars().all():
                edges.append((rel, "incoming"))

        total = len(edges)
        return edges[offset : offset + limit], total

    async def traverse(
        self,
        start_type: NodeType,
        start_id: UUID,
        max_depth: int = 2,
        relationship_types: list[RelationshipType] | None = None,
        direction: str = "outgoing",
    ) -> tuple[list[dict], list[MemoryRelationship]]:
        """
        Traverse the graph from a starting node using recursive CTE.

        Returns (nodes, relationships) where nodes include depth and path info.
        """
        # Build relationship type filter
        type_filter = ""
        params = {
            "start_type": start_type.value,
            "start_id": str(start_id),
            "max_depth": max_depth,
        }

        if relationship_types:
            type_values = [rt.value for rt in relationship_types]
            type_filter = "AND mr.relationship_type = ANY(:rel_types)"
            params["rel_types"] = type_values

        # Build direction filter (cast enum to text for comparison with varchar)
        if direction == "outgoing":
            join_condition = "mr.source_id = gt.node_id AND mr.source_type::text = gt.node_type"
            next_node = "mr.target_id, mr.target_type::text"
        elif direction == "incoming":
            join_condition = "mr.target_id = gt.node_id AND mr.target_type::text = gt.node_type"
            next_node = "mr.source_id, mr.source_type::text"
        else:  # both
            join_condition = "(mr.source_id = gt.node_id AND mr.source_type::text = gt.node_type) OR (mr.target_id = gt.node_id AND mr.target_type::text = gt.node_type)"
            next_node = "CASE WHEN mr.source_id = gt.node_id THEN mr.target_id ELSE mr.source_id END, CASE WHEN mr.source_type::text = gt.node_type THEN mr.target_type::text ELSE mr.source_type::text END"

        query = text(f"""
            WITH RECURSIVE graph_traversal AS (
                -- Base case: starting node
                SELECT
                    CAST(:start_id AS uuid) AS node_id,
                    CAST(:start_type AS varchar) AS node_type,
                    0 AS depth,
                    ARRAY[]::uuid[] AS path,
                    ARRAY[]::uuid[] AS visited

                UNION ALL

                -- Recursive case: follow edges
                SELECT
                    {next_node},
                    gt.depth + 1,
                    gt.path || mr.id,
                    gt.visited || gt.node_id
                FROM memory_relationships mr
                JOIN graph_traversal gt ON {join_condition}
                WHERE gt.depth < :max_depth
                    AND NOT (mr.target_id = ANY(gt.visited) AND mr.source_id = ANY(gt.visited))
                    {type_filter}
            )
            SELECT DISTINCT node_id, node_type, depth, path
            FROM graph_traversal
            WHERE depth > 0
            ORDER BY depth, node_id
        """)

        result = await self.db.execute(query, params)
        rows = result.fetchall()

        nodes = []
        relationship_ids = set()
        for row in rows:
            nodes.append({
                "node_type": NodeType(row.node_type),
                "node_id": row.node_id,
                "depth": row.depth,
                "path": list(row.path),
            })
            relationship_ids.update(row.path)

        # Fetch relationships
        relationships = []
        if relationship_ids:
            stmt = select(MemoryRelationship).where(
                MemoryRelationship.id.in_(relationship_ids)
            )
            result = await self.db.execute(stmt)
            relationships = list(result.scalars().all())

        return nodes, relationships

    async def find_path(
        self,
        source_type: NodeType,
        source_id: UUID,
        target_type: NodeType,
        target_id: UUID,
        max_depth: int = 5,
    ) -> list[MemoryRelationship] | None:
        """
        Find the shortest path between two nodes using BFS via recursive CTE.

        Returns list of relationships in path order, or None if no path exists.
        """
        query = text("""
            WITH RECURSIVE path_search AS (
                -- Base case: edges from source
                SELECT
                    mr.id AS rel_id,
                    mr.target_id AS current_id,
                    mr.target_type AS current_type,
                    ARRAY[mr.id] AS path,
                    1 AS depth
                FROM memory_relationships mr
                WHERE mr.source_id = :source_id
                    AND mr.source_type = :source_type

                UNION ALL

                -- Recursive case: follow edges
                SELECT
                    mr.id,
                    mr.target_id,
                    mr.target_type,
                    ps.path || mr.id,
                    ps.depth + 1
                FROM memory_relationships mr
                JOIN path_search ps ON mr.source_id = ps.current_id
                    AND mr.source_type = ps.current_type
                WHERE ps.depth < :max_depth
                    AND NOT (mr.id = ANY(ps.path))
            )
            SELECT path
            FROM path_search
            WHERE current_id = :target_id
                AND current_type = :target_type
            ORDER BY depth
            LIMIT 1
        """)

        result = await self.db.execute(
            query,
            {
                "source_type": source_type.value,
                "source_id": str(source_id),
                "target_type": target_type.value,
                "target_id": str(target_id),
                "max_depth": max_depth,
            },
        )
        row = result.fetchone()

        if not row:
            return None

        # Fetch relationships in path
        stmt = select(MemoryRelationship).where(
            MemoryRelationship.id.in_(row.path)
        )
        result = await self.db.execute(stmt)
        relationships = {r.id: r for r in result.scalars().all()}

        # Return in path order
        return [relationships[rel_id] for rel_id in row.path]

    async def get_related_memories(
        self,
        memory_id: UUID,
        relationship_types: list[RelationshipType] | None = None,
        max_depth: int = 1,
        limit: int = 50,
    ) -> list[dict]:
        """
        Get memories related to a given memory.

        Returns list of dicts with memory_id, relationship_type, depth, and weight.
        """
        nodes, relationships = await self.traverse(
            start_type=NodeType.MEMORY,
            start_id=memory_id,
            max_depth=max_depth,
            relationship_types=relationship_types,
            direction="both",
        )

        # Filter to only memory nodes
        related = []
        rel_map = {r.id: r for r in relationships}

        for node in nodes:
            if node["node_type"] == NodeType.MEMORY:
                # Get the relationship info
                rel_info = None
                if node["path"]:
                    last_rel_id = node["path"][-1]
                    if last_rel_id in rel_map:
                        rel = rel_map[last_rel_id]
                        rel_info = {
                            "relationship_type": rel.relationship_type.value,
                            "weight": rel.weight,
                        }

                related.append({
                    "memory_id": node["node_id"],
                    "depth": node["depth"],
                    "path": node["path"],
                    **(rel_info or {}),
                })

        return related[:limit]

    async def create_similarity_edges(
        self,
        memory_id: UUID,
        similar_memory_ids: list[tuple[UUID, float]],
        agent_id: UUID,
        threshold: float = 0.8,
    ) -> list[MemoryRelationship]:
        """
        Create SIMILAR_TO edges between a memory and similar memories.

        similar_memory_ids is a list of (memory_id, similarity_score) tuples.
        Only creates edges for scores >= threshold.
        """
        created = []
        for similar_id, score in similar_memory_ids:
            if score >= threshold and similar_id != memory_id:
                rel = await self.create_relationship(
                    source_type=NodeType.MEMORY,
                    source_id=memory_id,
                    target_type=NodeType.MEMORY,
                    target_id=similar_id,
                    relationship_type=RelationshipType.SIMILAR_TO,
                    weight=score,
                    created_by_agent_id=agent_id,
                )
                created.append(rel)
        return created

    async def delete_node_relationships(
        self,
        node_type: NodeType,
        node_id: UUID,
    ) -> int:
        """Delete all relationships involving a node (when node is deleted)."""
        stmt = delete(MemoryRelationship).where(
            or_(
                and_(
                    MemoryRelationship.source_type == node_type,
                    MemoryRelationship.source_id == node_id,
                ),
                and_(
                    MemoryRelationship.target_type == node_type,
                    MemoryRelationship.target_id == node_id,
                ),
            )
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount
