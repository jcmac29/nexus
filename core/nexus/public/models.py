"""Public marketplace models - Safe capability publishing with sandboxing."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base


class PublishStatus(str, Enum):
    """Status of a published capability."""
    DRAFT = "draft"              # Being configured, not visible
    PENDING_REVIEW = "pending"   # Submitted for safety review
    PUBLISHED = "published"      # Live and discoverable
    SUSPENDED = "suspended"      # Temporarily disabled
    REVOKED = "revoked"          # Permanently removed


class ApprovalPolicy(str, Enum):
    """How requests are approved."""
    MANUAL = "manual"            # Human approves each request
    AUTO_TRUSTED = "auto_trusted"  # Auto-approve from trusted requesters
    AUTO_ALL = "auto_all"        # Auto-approve all (use with caution)


class RequestStatus(str, Enum):
    """Status of a public request."""
    PENDING = "pending"          # Awaiting approval
    APPROVED = "approved"        # Approved, executing
    EXECUTING = "executing"      # Currently running
    COMPLETED = "completed"      # Successfully finished
    REJECTED = "rejected"        # Denied by owner
    FAILED = "failed"            # Execution failed
    EXPIRED = "expired"          # Timed out


class PublishedCapability(Base):
    """
    A capability published to the public marketplace.

    SAFETY: This is sandboxed - it can ONLY access what's explicitly allowed.
    """

    __tablename__ = "published_capabilities"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Owner
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"))
    capability_id: Mapped[UUID] = mapped_column(ForeignKey("capabilities.id"))

    # Public-facing info
    public_name: Mapped[str] = mapped_column(String(255))
    public_description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Status
    status: Mapped[PublishStatus] = mapped_column(
        SQLEnum(PublishStatus), default=PublishStatus.DRAFT
    )

    # SAFETY: Sandbox configuration
    # What data this capability can access
    allowed_memory_namespaces: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list
    )  # Empty = no memory access
    allowed_memory_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list
    )
    can_access_private_memory: Mapped[bool] = mapped_column(Boolean, default=False)

    # Input/output restrictions
    max_input_size_bytes: Mapped[int] = mapped_column(Integer, default=10000)
    max_output_size_bytes: Mapped[int] = mapped_column(Integer, default=50000)
    allowed_input_fields: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list
    )  # Empty = any fields allowed

    # Approval settings
    approval_policy: Mapped[ApprovalPolicy] = mapped_column(
        SQLEnum(ApprovalPolicy), default=ApprovalPolicy.MANUAL
    )
    trusted_requester_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list
    )  # Agent IDs that bypass approval

    # Rate limiting
    max_requests_per_hour: Mapped[int] = mapped_column(Integer, default=10)
    max_requests_per_day: Mapped[int] = mapped_column(Integer, default=100)
    current_hour_requests: Mapped[int] = mapped_column(Integer, default=0)
    current_day_requests: Mapped[int] = mapped_column(Integer, default=0)
    rate_limit_reset_hour: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limit_reset_day: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Pricing (optional)
    price_per_request: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    require_payment: Mapped[bool] = mapped_column(Boolean, default=False)

    # Stats
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    successful_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    average_response_time_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="published_capabilities")
    capability = relationship("Capability", backref="publications")


class PublicRequest(Base):
    """
    A request from the public to use a published capability.

    Full audit trail for transparency and safety.
    """

    __tablename__ = "public_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # What's being requested
    published_capability_id: Mapped[UUID] = mapped_column(
        ForeignKey("published_capabilities.id")
    )

    # Who's requesting (if authenticated)
    requester_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    requester_ip: Mapped[str | None] = mapped_column(String(45))  # IPv6 max length
    requester_user_agent: Mapped[str | None] = mapped_column(String(500))

    # Request details (sanitized - no sensitive data)
    input_hash: Mapped[str] = mapped_column(String(64))  # SHA256 of input
    input_size_bytes: Mapped[int] = mapped_column(Integer)
    input_preview: Mapped[str | None] = mapped_column(String(200))  # First 200 chars

    # Status
    status: Mapped[RequestStatus] = mapped_column(
        SQLEnum(RequestStatus), default=RequestStatus.PENDING
    )

    # Approval tracking
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    # Execution details
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Output (sanitized)
    output_size_bytes: Mapped[int | None] = mapped_column(Integer)
    output_preview: Mapped[str | None] = mapped_column(String(200))
    success: Mapped[bool | None] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Payment (if required)
    payment_required: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    payment_status: Mapped[str | None] = mapped_column(String(50))
    payment_id: Mapped[str | None] = mapped_column(String(255))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    published_capability = relationship("PublishedCapability", backref="requests")
    requester = relationship(
        "Agent", foreign_keys=[requester_agent_id], backref="public_requests_made"
    )
    approver = relationship(
        "Agent", foreign_keys=[approved_by], backref="public_requests_approved"
    )


class AgentReputation(Base):
    """
    Reputation scores for agents in the public marketplace.

    Tracks trustworthiness based on behavior.
    """

    __tablename__ = "agent_reputations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), unique=True)

    # Reputation scores (0-100)
    overall_score: Mapped[int] = mapped_column(Integer, default=50)
    reliability_score: Mapped[int] = mapped_column(Integer, default=50)  # Uptime, response rate
    quality_score: Mapped[int] = mapped_column(Integer, default=50)      # Success rate
    safety_score: Mapped[int] = mapped_column(Integer, default=50)       # No violations

    # Activity stats
    total_requests_served: Mapped[int] = mapped_column(Integer, default=0)
    successful_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_requests_made: Mapped[int] = mapped_column(Integer, default=0)

    # Trust indicators
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    violations_count: Mapped[int] = mapped_column(Integer, default=0)
    last_violation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="reputation")


class BlockedRequester(Base):
    """Blocked requesters - agents/IPs that are not allowed."""

    __tablename__ = "blocked_requesters"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Who blocked
    owner_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"))

    # Who's blocked
    blocked_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    blocked_ip: Mapped[str | None] = mapped_column(String(45))

    # Details
    reason: Mapped[str] = mapped_column(Text)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    owner = relationship(
        "Agent", foreign_keys=[owner_agent_id], backref="blocked_requesters"
    )
    blocked_agent = relationship(
        "Agent", foreign_keys=[blocked_agent_id], backref="blocked_by"
    )
