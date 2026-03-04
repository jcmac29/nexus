"""Search models for full-text and semantic search."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY, TSVECTOR

from nexus.database import Base


class IndexedContentType(str, enum.Enum):
    """Types of indexed content."""
    AGENT = "agent"
    MEMORY = "memory"
    MESSAGE = "message"
    DOCUMENT = "document"
    CONVERSATION = "conversation"
    TOOL = "tool"
    CAPABILITY = "capability"
    EVENT = "event"
    FILE = "file"
    DEVICE = "device"


class SearchIndex(Base):
    """A search index entry for full-text and semantic search."""

    __tablename__ = "search_index"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Content identification
    content_type = Column(Enum(IndexedContentType), nullable=False, index=True)
    content_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Searchable text
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    # Full-text search vector (PostgreSQL tsvector)
    search_vector = Column(TSVECTOR, nullable=True)

    # Semantic search embedding
    embedding = Column(ARRAY(Float), nullable=True)  # Vector embedding
    embedding_model = Column(String(100), nullable=True)

    # Metadata for filtering
    tags = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    categories = Column(JSON, default=list)

    # Relevance hints
    boost = Column(Float, default=1.0)  # Ranking boost factor
    popularity_score = Column(Float, default=0.0)

    # Access control
    is_public = Column(Boolean, default=False)
    allowed_agents = Column(JSON, default=list)  # Agent IDs that can see this

    # Timestamps
    content_created_at = Column(DateTime, nullable=True)
    content_updated_at = Column(DateTime, nullable=True)
    indexed_at = Column(DateTime, default=datetime.utcnow)

    # Status
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("ix_search_content", "content_type", "content_id", unique=True),
        Index("ix_search_vector", "search_vector", postgresql_using="gin"),
    )


class SearchQuery(Base):
    """Log of search queries for analytics."""

    __tablename__ = "search_queries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Query details
    query_text = Column(Text, nullable=False)
    query_type = Column(String(50), default="hybrid")  # text, semantic, hybrid
    filters = Column(JSON, default=dict)

    # Results
    result_count = Column(Integer, default=0)
    top_result_id = Column(UUID(as_uuid=True), nullable=True)

    # User
    user_id = Column(UUID(as_uuid=True), nullable=True)
    session_id = Column(String(255), nullable=True)

    # Timing
    duration_ms = Column(Integer, nullable=True)

    # Feedback
    clicked_result_id = Column(UUID(as_uuid=True), nullable=True)
    clicked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class SearchSynonym(Base):
    """Search synonyms for query expansion."""

    __tablename__ = "search_synonyms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    term = Column(String(255), nullable=False, index=True)
    synonyms = Column(JSON, default=list)  # List of synonym terms

    # Scope
    content_types = Column(JSON, default=list)  # Empty = all types
    owner_id = Column(UUID(as_uuid=True), nullable=True)  # None = global

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
