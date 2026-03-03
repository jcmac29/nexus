"""Tracing models for distributed observability."""

from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Integer, Float, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class Trace(Base):
    """A distributed trace across multiple agents/services."""

    __tablename__ = "traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(String(64), nullable=False, unique=True, index=True)  # External trace ID
    name = Column(String(255), nullable=False)

    # Origin
    root_agent_id = Column(UUID(as_uuid=True), nullable=True)
    root_service = Column(String(255), nullable=True)

    # Context
    context = Column(JSON, default=dict)
    tags = Column(JSON, default=dict)

    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    # Status
    status = Column(String(50), default="active")  # active, completed, failed
    error = Column(Text, nullable=True)

    # Stats
    span_count = Column(Integer, default=0)

    spans = relationship("Span", back_populates="trace", cascade="all, delete-orphan")


class Span(Base):
    """A single operation within a trace."""

    __tablename__ = "spans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    span_id = Column(String(64), nullable=False, index=True)
    trace_id = Column(UUID(as_uuid=True), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False)
    parent_span_id = Column(String(64), nullable=True, index=True)

    name = Column(String(255), nullable=False)
    kind = Column(String(50), default="internal")  # internal, client, server, producer, consumer

    # Service/Agent info
    service_name = Column(String(255), nullable=True)
    agent_id = Column(UUID(as_uuid=True), nullable=True)

    # Operation details
    operation = Column(String(255), nullable=True)
    resource = Column(String(255), nullable=True)

    # Attributes
    attributes = Column(JSON, default=dict)
    events = Column(JSON, default=list)  # List of {name, timestamp, attributes}
    links = Column(JSON, default=list)  # Links to other spans

    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    # Status
    status = Column(String(50), default="ok")  # ok, error
    error_message = Column(Text, nullable=True)
    error_type = Column(String(255), nullable=True)

    trace = relationship("Trace", back_populates="spans")

    __table_args__ = (
        Index("ix_spans_trace_parent", "trace_id", "parent_span_id"),
    )
