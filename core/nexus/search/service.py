"""Search service for full-text and semantic search."""

from __future__ import annotations

import time
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.search.models import SearchIndex, SearchQuery, SearchSynonym, IndexedContentType


class SearchService:
    """Service for search operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._embedding_client = None
        self._embedding_model = "text-embedding-3-small"

    def configure_openai(self, api_key: str, model: str = "text-embedding-3-small"):
        """Configure OpenAI for embeddings."""
        import openai
        self._embedding_client = openai.AsyncOpenAI(api_key=api_key)
        self._embedding_model = model

    async def generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for text."""
        if not self._embedding_client:
            return None

        try:
            response = await self._embedding_client.embeddings.create(
                model=self._embedding_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception:
            return None

    async def index_content(
        self,
        content_type: IndexedContentType,
        content_id: UUID,
        owner_id: UUID,
        title: str | None = None,
        content: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        categories: list[str] | None = None,
        is_public: bool = False,
        boost: float = 1.0,
        generate_embedding: bool = True,
    ) -> SearchIndex:
        """Index content for search."""
        # Check for existing index entry
        result = await self.db.execute(
            select(SearchIndex).where(
                and_(
                    SearchIndex.content_type == content_type,
                    SearchIndex.content_id == content_id,
                )
            )
        )
        index_entry = result.scalar_one_or_none()

        # Combine text for embedding
        text_for_embedding = " ".join(filter(None, [title, summary, content]))[:8000]

        # Generate embedding
        embedding = None
        if generate_embedding and text_for_embedding:
            embedding = await self.generate_embedding(text_for_embedding)

        if index_entry:
            # Update existing
            if title is not None:
                index_entry.title = title
            if content is not None:
                index_entry.content = content
            if summary is not None:
                index_entry.summary = summary
            if tags is not None:
                index_entry.tags = tags
            if metadata is not None:
                index_entry.metadata = metadata
            if categories is not None:
                index_entry.categories = categories
            if embedding:
                index_entry.embedding = embedding
                index_entry.embedding_model = self._embedding_model
            index_entry.is_public = is_public
            index_entry.boost = boost
            index_entry.content_updated_at = datetime.utcnow()
            index_entry.indexed_at = datetime.utcnow()
        else:
            index_entry = SearchIndex(
                content_type=content_type,
                content_id=content_id,
                owner_id=owner_id,
                title=title,
                content=content,
                summary=summary,
                tags=tags or [],
                metadata=metadata or {},
                categories=categories or [],
                embedding=embedding,
                embedding_model=self._embedding_model if embedding else None,
                is_public=is_public,
                boost=boost,
                content_created_at=datetime.utcnow(),
                indexed_at=datetime.utcnow(),
            )
            self.db.add(index_entry)

        # Update full-text search vector (PostgreSQL specific)
        if title or content or summary:
            text_concat = " ".join(filter(None, [title or "", summary or "", content or ""]))
            # This would use PostgreSQL's to_tsvector in a real implementation
            # For now, we'll handle it in the search query

        await self.db.commit()
        await self.db.refresh(index_entry)
        return index_entry

    async def remove_from_index(self, content_type: IndexedContentType, content_id: UUID):
        """Remove content from search index."""
        result = await self.db.execute(
            select(SearchIndex).where(
                and_(
                    SearchIndex.content_type == content_type,
                    SearchIndex.content_id == content_id,
                )
            )
        )
        index_entry = result.scalar_one_or_none()
        if index_entry:
            await self.db.delete(index_entry)
            await self.db.commit()

    async def search(
        self,
        query: str,
        owner_id: UUID | None = None,
        content_types: list[IndexedContentType] | None = None,
        tags: list[str] | None = None,
        categories: list[str] | None = None,
        include_public: bool = True,
        limit: int = 20,
        offset: int = 0,
        search_type: str = "hybrid",  # text, semantic, hybrid
        user_id: UUID | None = None,
    ) -> list[dict]:
        """
        Search indexed content.

        search_type:
        - text: Full-text search only
        - semantic: Vector similarity search only
        - hybrid: Combination of both
        """
        start_time = time.time()

        # Build base query
        conditions = [SearchIndex.is_active == True]

        # Owner filter
        if owner_id:
            if include_public:
                conditions.append(
                    or_(
                        SearchIndex.owner_id == owner_id,
                        SearchIndex.is_public == True,
                    )
                )
            else:
                conditions.append(SearchIndex.owner_id == owner_id)
        elif not include_public:
            return []

        # Content type filter
        if content_types:
            conditions.append(SearchIndex.content_type.in_(content_types))

        # Tag filter
        if tags:
            # Check if any tag matches
            for tag in tags:
                conditions.append(func.jsonb_exists(SearchIndex.tags, tag))

        # Category filter
        if categories:
            for cat in categories:
                conditions.append(func.jsonb_exists(SearchIndex.categories, cat))

        results = []

        if search_type in ("text", "hybrid"):
            # Full-text search using ILIKE (simplified)
            # In production, use PostgreSQL's full-text search with tsvector
            text_conditions = conditions.copy()
            search_pattern = f"%{query}%"
            text_conditions.append(
                or_(
                    SearchIndex.title.ilike(search_pattern),
                    SearchIndex.content.ilike(search_pattern),
                    SearchIndex.summary.ilike(search_pattern),
                )
            )

            text_query = (
                select(SearchIndex)
                .where(and_(*text_conditions))
                .order_by(SearchIndex.boost.desc(), SearchIndex.indexed_at.desc())
                .limit(limit)
                .offset(offset)
            )

            text_result = await self.db.execute(text_query)
            text_matches = list(text_result.scalars().all())

            for match in text_matches:
                results.append({
                    "id": str(match.content_id),
                    "type": match.content_type.value,
                    "title": match.title,
                    "summary": match.summary,
                    "score": match.boost,
                    "source": "text",
                    "tags": match.tags,
                    "categories": match.categories,
                    "indexed_at": match.indexed_at.isoformat() if match.indexed_at else None,
                })

        if search_type in ("semantic", "hybrid") and self._embedding_client:
            # Semantic search using vector similarity
            query_embedding = await self.generate_embedding(query)
            if query_embedding:
                # In production, use pgvector's <-> operator for cosine distance
                # This is a simplified version
                semantic_query = (
                    select(SearchIndex)
                    .where(
                        and_(
                            *conditions,
                            SearchIndex.embedding.isnot(None),
                        )
                    )
                    .limit(limit * 2)  # Get more for re-ranking
                )

                semantic_result = await self.db.execute(semantic_query)
                semantic_matches = list(semantic_result.scalars().all())

                # Calculate cosine similarity manually
                import math

                def cosine_similarity(a: list[float], b: list[float]) -> float:
                    dot_product = sum(x * y for x, y in zip(a, b))
                    norm_a = math.sqrt(sum(x * x for x in a))
                    norm_b = math.sqrt(sum(y * y for y in b))
                    if norm_a == 0 or norm_b == 0:
                        return 0
                    return dot_product / (norm_a * norm_b)

                scored_matches = []
                for match in semantic_matches:
                    if match.embedding:
                        similarity = cosine_similarity(query_embedding, match.embedding)
                        scored_matches.append((match, similarity))

                # Sort by similarity
                scored_matches.sort(key=lambda x: x[1], reverse=True)

                for match, similarity in scored_matches[:limit]:
                    # Check if already in results
                    existing = next(
                        (r for r in results if r["id"] == str(match.content_id)),
                        None
                    )
                    if existing:
                        # Boost score for hybrid match
                        existing["score"] = (existing["score"] + similarity * match.boost) / 2
                        existing["source"] = "hybrid"
                    else:
                        results.append({
                            "id": str(match.content_id),
                            "type": match.content_type.value,
                            "title": match.title,
                            "summary": match.summary,
                            "score": similarity * match.boost,
                            "source": "semantic",
                            "tags": match.tags,
                            "categories": match.categories,
                            "indexed_at": match.indexed_at.isoformat() if match.indexed_at else None,
                        })

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:limit]

        # Log query
        duration_ms = int((time.time() - start_time) * 1000)
        search_log = SearchQuery(
            query_text=query,
            query_type=search_type,
            filters={
                "content_types": [ct.value for ct in content_types] if content_types else None,
                "tags": tags,
                "categories": categories,
            },
            result_count=len(results),
            top_result_id=UUID(results[0]["id"]) if results else None,
            user_id=user_id,
            duration_ms=duration_ms,
        )
        self.db.add(search_log)
        await self.db.commit()

        return results

    async def suggest(
        self,
        prefix: str,
        owner_id: UUID | None = None,
        content_types: list[IndexedContentType] | None = None,
        limit: int = 10,
    ) -> list[str]:
        """Get search suggestions based on prefix."""
        conditions = [
            SearchIndex.is_active == True,
            SearchIndex.title.ilike(f"{prefix}%"),
        ]

        if owner_id:
            conditions.append(
                or_(
                    SearchIndex.owner_id == owner_id,
                    SearchIndex.is_public == True,
                )
            )

        if content_types:
            conditions.append(SearchIndex.content_type.in_(content_types))

        query = (
            select(SearchIndex.title)
            .where(and_(*conditions))
            .distinct()
            .limit(limit)
        )

        result = await self.db.execute(query)
        return [row[0] for row in result.fetchall() if row[0]]

    async def reindex_all(self, content_type: IndexedContentType | None = None):
        """Reindex all content (regenerate embeddings)."""
        conditions = [SearchIndex.is_active == True]
        if content_type:
            conditions.append(SearchIndex.content_type == content_type)

        result = await self.db.execute(
            select(SearchIndex).where(and_(*conditions))
        )
        entries = result.scalars().all()

        for entry in entries:
            text_for_embedding = " ".join(filter(None, [
                entry.title, entry.summary, entry.content
            ]))[:8000]

            if text_for_embedding:
                embedding = await self.generate_embedding(text_for_embedding)
                if embedding:
                    entry.embedding = embedding
                    entry.embedding_model = self._embedding_model
                    entry.indexed_at = datetime.utcnow()

        await self.db.commit()

    async def get_similar(
        self,
        content_id: UUID,
        limit: int = 10,
    ) -> list[dict]:
        """Find similar content based on embeddings."""
        # Get the source content
        result = await self.db.execute(
            select(SearchIndex).where(SearchIndex.content_id == content_id)
        )
        source = result.scalar_one_or_none()
        if not source or not source.embedding:
            return []

        # Find similar by embedding similarity
        result = await self.db.execute(
            select(SearchIndex).where(
                and_(
                    SearchIndex.is_active == True,
                    SearchIndex.content_id != content_id,
                    SearchIndex.embedding.isnot(None),
                    SearchIndex.content_type == source.content_type,
                )
            )
        )
        candidates = result.scalars().all()

        import math

        def cosine_similarity(a: list[float], b: list[float]) -> float:
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            if norm_a == 0 or norm_b == 0:
                return 0
            return dot_product / (norm_a * norm_b)

        scored = []
        for candidate in candidates:
            if candidate.embedding:
                similarity = cosine_similarity(source.embedding, candidate.embedding)
                scored.append((candidate, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            {
                "id": str(match.content_id),
                "type": match.content_type.value,
                "title": match.title,
                "summary": match.summary,
                "similarity": score,
            }
            for match, score in scored[:limit]
        ]
