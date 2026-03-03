"""Background job models."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID

from nexus.database import Base


class JobStatus(str, enum.Enum):
    """Status of a background job."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class JobPriority(str, enum.Enum):
    """Job priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class BackgroundJob(Base):
    """A background job record."""

    __tablename__ = "background_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Job identification
    job_id = Column(String(255), unique=True, index=True)  # External job ID
    name = Column(String(255), nullable=False, index=True)
    queue = Column(String(100), default="default", index=True)

    # Task details
    task_name = Column(String(255), nullable=False)
    args = Column(JSON, default=list)
    kwargs = Column(JSON, default=dict)

    # Status
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, index=True)
    priority = Column(Enum(JobPriority), default=JobPriority.NORMAL)

    # Result
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)

    # Retry configuration
    max_retries = Column(Integer, default=3)
    retry_count = Column(Integer, default=0)
    retry_delay = Column(Integer, default=60)  # Seconds

    # Timing
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    timeout_seconds = Column(Integer, default=300)

    # Worker info
    worker_id = Column(String(255), nullable=True)
    worker_hostname = Column(String(255), nullable=True)

    # Progress
    progress = Column(Integer, default=0)  # 0-100
    progress_message = Column(String(500), nullable=True)

    # Metadata
    metadata = Column(JSON, default=dict)
    tags = Column(JSON, default=list)

    # Ownership
    owner_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecurringJob(Base):
    """A recurring/scheduled job definition."""

    __tablename__ = "recurring_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Task
    task_name = Column(String(255), nullable=False)
    args = Column(JSON, default=list)
    kwargs = Column(JSON, default=dict)
    queue = Column(String(100), default="default")

    # Schedule
    cron_expression = Column(String(100), nullable=True)  # Cron format
    interval_seconds = Column(Integer, nullable=True)  # Or fixed interval
    timezone = Column(String(100), default="UTC")

    # Status
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)

    # Ownership
    owner_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
