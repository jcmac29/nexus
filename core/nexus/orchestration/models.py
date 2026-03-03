"""Orchestration models for multi-agent coordination."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class WorkflowStatus(str, enum.Enum):
    """Status of a workflow."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ExecutionStatus(str, enum.Enum):
    """Status of an execution."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"  # Waiting for external input
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepType(str, enum.Enum):
    """Type of workflow step."""
    AGENT_CALL = "agent_call"      # Invoke an agent's capability
    TOOL_CALL = "tool_call"        # Execute a tool
    PARALLEL = "parallel"          # Run multiple steps in parallel
    CONDITIONAL = "conditional"     # Branch based on condition
    LOOP = "loop"                  # Repeat steps
    WAIT = "wait"                  # Wait for event/time
    HUMAN_INPUT = "human_input"    # Wait for human input
    AGGREGATE = "aggregate"        # Combine results from parallel steps
    TRANSFORM = "transform"        # Transform data


class Workflow(Base):
    """A workflow definition for orchestrating agents."""

    __tablename__ = "orchestration_workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    status = Column(Enum(WorkflowStatus), default=WorkflowStatus.DRAFT)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # Workflow definition
    input_schema = Column(JSON, default=dict)
    output_schema = Column(JSON, default=dict)

    # Configuration
    config = Column(JSON, default=dict)
    max_concurrent_executions = Column(Integer, default=10)
    default_timeout = Column(Integer, default=3600)  # Seconds

    # Version control
    version = Column(String(50), default="1.0.0")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.order")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowStep(Base):
    """A step in a workflow."""

    __tablename__ = "orchestration_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("orchestration_workflows.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    step_type = Column(Enum(StepType), nullable=False)
    order = Column(Integer, default=0)

    # Step configuration
    config = Column(JSON, default=dict)
    # For agent/tool calls
    target_id = Column(UUID(as_uuid=True), nullable=True)
    target_type = Column(String(50), nullable=True)  # agent, tool
    capability = Column(String(255), nullable=True)

    # Input mapping - how to build input from workflow state
    input_mapping = Column(JSON, default=dict)
    # Output mapping - where to store results
    output_mapping = Column(JSON, default=dict)

    # For conditionals
    condition = Column(Text, nullable=True)  # Expression to evaluate

    # For parallel steps
    parallel_steps = Column(JSON, default=list)  # List of step IDs to run in parallel

    # Error handling
    on_error = Column(String(50), default="fail")  # fail, continue, retry
    retry_count = Column(Integer, default=0)
    retry_delay = Column(Integer, default=5)  # Seconds

    # Timeout
    timeout = Column(Integer, nullable=True)

    workflow = relationship("Workflow", back_populates="steps")


class WorkflowExecution(Base):
    """An execution instance of a workflow."""

    __tablename__ = "orchestration_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("orchestration_workflows.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING)

    # Who triggered
    triggered_by = Column(UUID(as_uuid=True), nullable=False)
    triggered_by_type = Column(String(50), default="agent")

    # Execution state
    input_data = Column(JSON, default=dict)
    state = Column(JSON, default=dict)  # Current workflow state/context
    output_data = Column(JSON, nullable=True)

    # Progress tracking
    current_step_id = Column(UUID(as_uuid=True), nullable=True)
    completed_steps = Column(JSON, default=list)
    step_results = Column(JSON, default=dict)  # step_id -> result

    # Error info
    error = Column(Text, nullable=True)
    error_step_id = Column(UUID(as_uuid=True), nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    timeout_at = Column(DateTime, nullable=True)

    # For human input steps
    waiting_for_input = Column(Boolean, default=False)
    input_prompt = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="executions")
    step_executions = relationship("StepExecution", back_populates="workflow_execution", cascade="all, delete-orphan")


class StepExecution(Base):
    """Execution record for a single step."""

    __tablename__ = "orchestration_step_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_execution_id = Column(UUID(as_uuid=True), ForeignKey("orchestration_executions.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(UUID(as_uuid=True), ForeignKey("orchestration_steps.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING)
    attempt = Column(Integer, default=1)

    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    workflow_execution = relationship("WorkflowExecution", back_populates="step_executions")
