"""Gigs marketplace models - AI workers bidding on and completing work."""

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy import (
    String, Integer, DateTime, ForeignKey, Float, Enum, Text,
    Index, Boolean, Numeric, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base


class GigStatus(str, enum.Enum):
    """Status of a gig posting."""
    DRAFT = "draft"
    OPEN = "open"                    # Accepting bids
    IN_PROGRESS = "in_progress"      # Work underway
    REVIEW = "review"                # Deliverables under review
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class BidStatus(str, enum.Enum):
    """Status of a bid."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ContractStatus(str, enum.Enum):
    """Status of a work contract."""
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    DISPUTED = "disputed"


class DeliverableStatus(str, enum.Enum):
    """Status of a deliverable."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


class WorkerPoolStatus(str, enum.Enum):
    """Status of a worker pool."""
    PROVISIONING = "provisioning"
    READY = "ready"
    WORKING = "working"
    SCALING = "scaling"
    DRAINING = "draining"
    TERMINATED = "terminated"


class Gig(Base):
    """A work request that AI agents can bid on."""

    __tablename__ = "gigs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Who posted the gig
    poster_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Gig details
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Categorization
    category: Mapped[str] = mapped_column(String(50))  # code, data, content, research, etc.
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Work specification
    work_type: Mapped[str] = mapped_column(String(50))  # single, parallel, sequential
    is_parallelizable: Mapped[bool] = mapped_column(Boolean, default=False)

    # For parallelizable work
    total_units: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Total work units
    unit_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    max_workers: Mapped[int] = mapped_column(Integer, default=1)  # Max parallel workers

    # Budget
    budget_min: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    budget_max: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    price_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="credits")

    # Timeline
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Status
    status: Mapped[GigStatus] = mapped_column(Enum(GigStatus), default=GigStatus.DRAFT)

    # Requirements for workers
    min_reputation: Mapped[float] = mapped_column(Float, default=0.0)
    required_capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Stats
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    bid_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_gigs_status", "status"),
        Index("ix_gigs_category", "category"),
        Index("ix_gigs_poster", "poster_id"),
    )


class GigBid(Base):
    """A bid from an AI agent to work on a gig."""

    __tablename__ = "gig_bids"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    gig_id: Mapped[UUID] = mapped_column(ForeignKey("gigs.id", ondelete="CASCADE"))
    bidder_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Bid details
    proposed_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    proposed_timeline_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # For parallel work - how many units this worker can handle
    proposed_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workers_available: Mapped[int] = mapped_column(Integer, default=1)  # Number of parallel workers

    # Pitch
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevant_experience: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[BidStatus] = mapped_column(Enum(BidStatus), default=BidStatus.PENDING)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_gig_bids_gig", "gig_id"),
        Index("ix_gig_bids_bidder", "bidder_id"),
    )


class GigContract(Base):
    """A contract between gig poster and worker(s)."""

    __tablename__ = "gig_contracts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    gig_id: Mapped[UUID] = mapped_column(ForeignKey("gigs.id", ondelete="CASCADE"))
    bid_id: Mapped[UUID] = mapped_column(ForeignKey("gig_bids.id", ondelete="CASCADE"))
    worker_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Contract terms
    agreed_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    agreed_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # For parallel work
    unit_range_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_range_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[ContractStatus] = mapped_column(Enum(ContractStatus), default=ContractStatus.ACTIVE)

    # Progress
    units_completed: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)

    # Escrow
    escrow_amount: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    escrow_released: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_gig_contracts_gig", "gig_id"),
        Index("ix_gig_contracts_worker", "worker_id"),
    )


class GigDeliverable(Base):
    """A deliverable submitted for a gig."""

    __tablename__ = "gig_deliverables"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    contract_id: Mapped[UUID] = mapped_column(ForeignKey("gig_contracts.id", ondelete="CASCADE"))

    # What was delivered
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The actual output
    output_type: Mapped[str] = mapped_column(String(50))  # file, code, data, url, text
    output_data: Mapped[dict] = mapped_column(JSON)  # The deliverable content/reference

    # For parallel work - which units this covers
    units_covered: Mapped[list | None] = mapped_column(JSON, nullable=True)

    status: Mapped[DeliverableStatus] = mapped_column(
        Enum(DeliverableStatus), default=DeliverableStatus.PENDING
    )

    # Review
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, default=0)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_gig_deliverables_contract", "contract_id"),
    )


class WorkerPool(Base):
    """A pool of AI workers provisioned for a gig."""

    __tablename__ = "worker_pools"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    gig_id: Mapped[UUID] = mapped_column(ForeignKey("gigs.id", ondelete="CASCADE"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Pool configuration
    name: Mapped[str] = mapped_column(String(200))
    target_workers: Mapped[int] = mapped_column(Integer, default=1)
    active_workers: Mapped[int] = mapped_column(Integer, default=0)

    # Infrastructure
    infrastructure_type: Mapped[str] = mapped_column(String(50))  # droplet, kubernetes, lambda
    infrastructure_config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Resource specs per worker
    cpu_per_worker: Mapped[int] = mapped_column(Integer, default=2)  # vCPUs
    memory_per_worker: Mapped[int] = mapped_column(Integer, default=4096)  # MB
    gpu_per_worker: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking
    cost_per_hour: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)

    status: Mapped[WorkerPoolStatus] = mapped_column(
        Enum(WorkerPoolStatus), default=WorkerPoolStatus.PROVISIONING
    )

    # Connection info
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_worker_pools_gig", "gig_id"),
        Index("ix_worker_pools_status", "status"),
    )


class WorkerInstance(Base):
    """An individual worker instance in a pool."""

    __tablename__ = "worker_instances"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    pool_id: Mapped[UUID] = mapped_column(ForeignKey("worker_pools.id", ondelete="CASCADE"))

    # Infrastructure reference
    instance_id: Mapped[str] = mapped_column(String(200))  # Droplet ID, pod name, etc.
    instance_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="provisioning")

    # Work assignment
    assigned_units: Mapped[list | None] = mapped_column(JSON, nullable=True)
    completed_units: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Performance
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    avg_task_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    # Health
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_worker_instances_pool", "pool_id"),
        Index("ix_worker_instances_status", "status"),
    )


class GigDispute(Base):
    """A dispute raised on a gig contract."""

    __tablename__ = "gig_disputes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    contract_id: Mapped[UUID] = mapped_column(ForeignKey("gig_contracts.id", ondelete="CASCADE"))
    raised_by: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    reason: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="open")  # open, investigating, resolved
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_gig_disputes_contract", "contract_id"),
    )
