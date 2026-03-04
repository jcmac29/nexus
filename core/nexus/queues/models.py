"""Queue models for priority task handling."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class QueueStatus(str, enum.Enum):
    """Status of a queue."""
    ACTIVE = "active"
    PAUSED = "paused"
    DRAINING = "draining"  # Processing remaining, no new items


class ItemStatus(str, enum.Enum):
    """Status of a queue item."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"  # Moved to dead letter queue


class Priority(int, enum.Enum):
    """Priority levels."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class Queue(Base):
    """A message/task queue."""

    __tablename__ = "queues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="system")

    status = Column(Enum(QueueStatus), default=QueueStatus.ACTIVE)

    # Configuration
    max_size = Column(Integer, nullable=True)  # Max items in queue
    max_retries = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=60)
    visibility_timeout_seconds = Column(Integer, default=300)  # How long item is hidden after dequeue
    message_ttl_seconds = Column(Integer, nullable=True)  # Auto-expire messages

    # Concurrency control
    max_concurrent_processors = Column(Integer, default=10)
    current_processors = Column(Integer, default=0)

    # Conflict resolution
    deduplication_enabled = Column(Boolean, default=False)
    deduplication_window_seconds = Column(Integer, default=300)

    # Stats
    total_enqueued = Column(Integer, default=0)
    total_processed = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("QueueItem", back_populates="queue", cascade="all, delete-orphan")


class QueueItem(Base):
    """An item in a queue."""

    __tablename__ = "queue_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    queue_id = Column(UUID(as_uuid=True), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False)

    # Priority (lower = higher priority)
    priority = Column(Integer, default=Priority.NORMAL.value)

    status = Column(Enum(ItemStatus), default=ItemStatus.PENDING)

    # Message content
    payload = Column(JSON, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)

    # Deduplication
    dedup_key = Column(String(255), nullable=True, index=True)

    # Processing
    processor_id = Column(UUID(as_uuid=True), nullable=True)  # Who's processing
    processor_type = Column(String(50), nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, nullable=True)  # Override queue default
    last_error = Column(Text, nullable=True)

    # Timing
    enqueued_at = Column(DateTime, default=datetime.utcnow)
    visible_at = Column(DateTime, default=datetime.utcnow)  # When item becomes visible
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Result
    result = Column(JSON, nullable=True)

    # Locking for conflict resolution
    lock_token = Column(String(64), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    lock_expires_at = Column(DateTime, nullable=True)

    queue = relationship("Queue", back_populates="items")

    __table_args__ = (
        Index("ix_queue_items_priority_visible", "queue_id", "priority", "visible_at"),
        Index("ix_queue_items_status", "queue_id", "status"),
    )


class DeadLetter(Base):
    """Dead letter queue for failed messages."""

    __tablename__ = "dead_letters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_queue_id = Column(UUID(as_uuid=True), nullable=False)
    original_item_id = Column(UUID(as_uuid=True), nullable=False)

    payload = Column(JSON, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)

    # Failure info
    failure_reason = Column(Text, nullable=True)
    attempts = Column(Integer, default=0)
    errors = Column(JSON, default=list)  # List of errors from each attempt

    # Tracking
    moved_at = Column(DateTime, default=datetime.utcnow)
    requeued_at = Column(DateTime, nullable=True)
    requeue_count = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_dead_letters_queue", "original_queue_id"),
    )
