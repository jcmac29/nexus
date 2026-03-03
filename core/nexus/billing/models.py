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


# --- Marketplace Billing ---


class MarketplaceTransactionType(str, enum.Enum):
    """Types of marketplace transactions."""
    SUBSCRIPTION = "subscription"
    ONE_TIME = "one_time"
    USAGE = "usage"
    TIP = "tip"


class MarketplaceTransactionStatus(str, enum.Enum):
    """Status of a marketplace transaction."""
    PENDING = "pending"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    FAILED = "failed"
    DISPUTED = "disputed"


class PayoutStatus(str, enum.Enum):
    """Status of a payout to a seller."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MarketplaceTransaction(Base):
    """
    Transaction for marketplace purchases.

    Tracks AI agent subscriptions, one-time purchases, and usage fees
    with platform fee calculation.
    """
    __tablename__ = "marketplace_transactions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # Buyer
    buyer_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer_agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    # Seller
    seller_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seller_agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    # Marketplace listing reference
    listing_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    # Transaction details
    transaction_type: Mapped[MarketplaceTransactionType] = mapped_column(
        Enum(MarketplaceTransactionType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[MarketplaceTransactionStatus] = mapped_column(
        Enum(MarketplaceTransactionStatus, values_callable=lambda x: [e.value for e in x]),
        default=MarketplaceTransactionStatus.PENDING,
    )

    # Amounts (all in cents)
    gross_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Total charged to buyer
    platform_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Nexus platform cut
    seller_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Amount to seller

    # Fee configuration at time of transaction
    platform_fee_percent: Mapped[int] = mapped_column(Integer, default=10)  # e.g., 10 = 10%

    # Currency
    currency: Mapped[str] = mapped_column(String(3), default="usd")

    # Stripe references
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_transfer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default="{}")

    # Subscription period (if applicable)
    subscription_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Payout tracking
    payout_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("marketplace_payouts.id", ondelete="SET NULL"),
        nullable=True,
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

    def __repr__(self) -> str:
        return f"<MarketplaceTransaction {self.id} ${self.gross_amount_cents/100}>"


class MarketplacePayout(Base):
    """
    Payout to marketplace sellers.

    Aggregates transactions and tracks disbursement.
    """
    __tablename__ = "marketplace_payouts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # Seller
    seller_account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Payout details
    status: Mapped[PayoutStatus] = mapped_column(
        Enum(PayoutStatus, values_callable=lambda x: [e.value for e in x]),
        default=PayoutStatus.PENDING,
    )

    # Amounts (in cents)
    gross_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Before fees
    platform_fees_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Total fees deducted
    net_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Amount paid to seller

    currency: Mapped[str] = mapped_column(String(3), default="usd")

    # Transaction count
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)

    # Period covered
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Stripe payout
    stripe_payout_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_transfer_group: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Bank account (last 4)
    destination_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # Timing
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<MarketplacePayout {self.id} ${self.net_amount_cents/100}>"


class PlatformFeeConfig(Base):
    """
    Platform fee configuration.

    Allows different fee tiers for different seller levels or categories.
    """
    __tablename__ = "platform_fee_configs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fee percentages (stored as basis points, e.g., 1000 = 10%)
    subscription_fee_bps: Mapped[int] = mapped_column(Integer, default=1000)  # 10% default
    one_time_fee_bps: Mapped[int] = mapped_column(Integer, default=1500)  # 15% default
    usage_fee_bps: Mapped[int] = mapped_column(Integer, default=1000)  # 10% default

    # Minimum transaction fee (in cents)
    min_fee_cents: Mapped[int] = mapped_column(Integer, default=50)  # $0.50 minimum

    # Volume discounts
    volume_discount_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    volume_thresholds: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # e.g., {"10000": 900, "50000": 800, "100000": 700} = fee in bps at volume thresholds

    # Applicable categories (empty = all)
    applicable_categories: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<PlatformFeeConfig {self.name}>"


class SellerAccount(Base):
    """
    Seller account for marketplace.

    Links to Stripe Connect for payouts.
    """
    __tablename__ = "seller_accounts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Stripe Connect
    stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    stripe_account_type: Mapped[str] = mapped_column(String(50), default="express")  # express, standard, custom
    stripe_onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_charges_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_payouts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Fee tier
    fee_config_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_fee_configs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Payout settings
    payout_schedule: Mapped[str] = mapped_column(String(50), default="weekly")  # daily, weekly, monthly
    minimum_payout_cents: Mapped[int] = mapped_column(Integer, default=1000)  # $10 minimum

    # Stats
    total_sales_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    total_fees_paid_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    total_payouts_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    pending_balance_cents: Mapped[int] = mapped_column(BigInteger, default=0)

    # Verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<SellerAccount {self.account_id}>"
