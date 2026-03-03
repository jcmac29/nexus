"""Scheduling models for cron-like jobs."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class JobType(str, enum.Enum):
    """Type of scheduled job."""
    AGENT_INVOKE = "agent_invoke"    # Invoke an agent capability
    TOOL_EXECUTE = "tool_execute"    # Execute a tool
    WORKFLOW_RUN = "workflow_run"    # Run a workflow
    WEBHOOK_CALL = "webhook_call"    # Call a webhook
    EVENT_PUBLISH = "event_publish"  # Publish an event
    CUSTOM = "custom"


class JobStatus(str, enum.Enum):
    """Status of a scheduled job."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"  # One-time job that finished
    DISABLED = "disabled"


class ExecutionStatus(str, enum.Enum):
    """Status of a job execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScheduledJob(Base):
    """A scheduled/recurring job."""

    __tablename__ = "scheduled_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # Job type and configuration
    job_type = Column(Enum(JobType), nullable=False)
    config = Column(JSON, default=dict)
    # For agent_invoke: {"agent_id": "...", "capability": "...", "input": {...}}
    # For tool_execute: {"tool_id": "...", "input": {...}}
    # For workflow_run: {"workflow_id": "...", "input": {...}}
    # For webhook_call: {"url": "...", "method": "POST", "body": {...}}
    # For event_publish: {"event_type": "...", "topic": "...", "payload": {...}}

    # Schedule (cron expression or interval)
    cron_expression = Column(String(100), nullable=True)  # Standard cron format
    interval_seconds = Column(Integer, nullable=True)  # Alternative: run every N seconds
    run_at = Column(DateTime, nullable=True)  # One-time: run at specific time

    # Timezone
    timezone = Column(String(50), default="UTC")

    # Status
    status = Column(Enum(JobStatus), default=JobStatus.ACTIVE)

    # Execution tracking
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    # Limits
    max_runs = Column(Integer, nullable=True)  # Stop after N runs
    end_date = Column(DateTime, nullable=True)  # Stop after this date

    # Retry configuration
    retry_on_failure = Column(Boolean, default=True)
    max_retries = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=60)

    # Concurrency
    allow_concurrent = Column(Boolean, default=False)
    timeout_seconds = Column(Integer, default=300)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    executions = relationship("JobExecution", back_populates="job", cascade="all, delete-orphan")


class JobExecution(Base):
    """Record of a job execution."""

    __tablename__ = "job_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING)
    attempt = Column(Integer, default=1)

    # Scheduled vs actual
    scheduled_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Results
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    # Duration
    duration_ms = Column(Integer, nullable=True)

    job = relationship("ScheduledJob", back_populates="executions")
