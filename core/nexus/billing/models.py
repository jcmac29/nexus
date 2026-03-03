"""Database models for billing."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.billing.plans import PlanType
from nexus.database import Base


class SubscriptionStatus(str, enum.Enum):
    """Subscription status."""
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    PAUSED = "paused"


class Account(Base):
    """
    Account for billing purposes.

    An account can have multiple agents and team members.
    This is the billing entity.
    """
    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Stripe integration
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Current plan
    plan_type: Mapped[PlanType] = mapped_column(
        Enum(PlanType, values_callable=lambda x: [e.value for e in x]),
        default=PlanType.FREE,
        server_default="free",
    )

    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription",
        back_populates="account",
        cascade="all, delete-orphan",
    )
    usage_records: Mapped[list["Usage"]] = relationship(
        "Usage",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Account {self.email}>"


class Subscription(Base):
    """Stripe subscription record."""
    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Stripe data
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    stripe_price_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Plan info
    plan_type: Mapped[PlanType] = mapped_column(
        Enum(PlanType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Status
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, values_callable=lambda x: [e.value for e in x]),
        default=SubscriptionStatus.ACTIVE,
    )

    # Billing period
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Billing type
    is_annual: Mapped[bool] = mapped_column(Boolean, default=False)

    # Cancellation
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription {self.stripe_subscription_id}>"


class UsageType(str, enum.Enum):
    """Types of billable usage."""
    MEMORY_STORE = "memory_store"
    MEMORY_GET = "memory_get"
    MEMORY_SEARCH = "memory_search"
    MEMORY_DELETE = "memory_delete"
    DISCOVERY_QUERY = "discovery_query"
    API_REQUEST = "api_request"


class Usage(Base):
    """
    Usage tracking for billing.

    Aggregated daily per account per usage type.
    """
    __tablename__ = "usage"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Usage data
    usage_type: Mapped[UsageType] = mapped_column(
        Enum(UsageType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    count: Mapped[int] = mapped_column(BigInteger, default=0)

    # Time period (daily aggregation)
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Billing period reference
    billing_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="usage_records")

    def __repr__(self) -> str:
        return f"<Usage {self.usage_type} {self.count}>"


class UsageSummary(Base):
    """
    Monthly usage summary for billing.

    Aggregated at end of billing period.
    """
    __tablename__ = "usage_summaries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Billing period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Usage totals
    memory_ops: Mapped[int] = mapped_column(BigInteger, default=0)
    discovery_queries: Mapped[int] = mapped_column(BigInteger, default=0)
    api_requests: Mapped[int] = mapped_column(BigInteger, default=0)
    stored_memories_peak: Mapped[int] = mapped_column(BigInteger, default=0)

    # Limits at time of billing
    plan_type: Mapped[PlanType] = mapped_column(
        Enum(PlanType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Overage
    memory_ops_overage: Mapped[int] = mapped_column(BigInteger, default=0)
    discovery_overage: Mapped[int] = mapped_column(BigInteger, default=0)
    api_requests_overage: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_overage: Mapped[int] = mapped_column(BigInteger, default=0)

    # Billing
    overage_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    billed: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<UsageSummary {self.period_start} - {self.period_end}>"
