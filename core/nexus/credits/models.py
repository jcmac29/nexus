"""Credit balance models for Nexus - Prepaid system like Claude Console."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Text, Enum, JSON,
    Integer, Numeric, Boolean, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class TransactionType(str, enum.Enum):
    """Credit transaction types."""
    PURCHASE = "purchase"           # Bought credits
    USAGE = "usage"                 # Used credits for a service
    EARNING = "earning"             # Earned from providing service
    TRANSFER_IN = "transfer_in"     # Received from another user
    TRANSFER_OUT = "transfer_out"   # Sent to another user
    REFUND = "refund"               # Refund
    BONUS = "bonus"                 # Promotional bonus
    PAYOUT = "payout"               # Withdrew earnings
    ADJUSTMENT = "adjustment"       # Manual adjustment


class CreditBalance(Base):
    """User/Agent credit balance - like Claude Console balance."""

    __tablename__ = "credit_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner (can be user or agent)
    owner_type = Column(String(50), nullable=False)  # user, agent, organization
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Balances (in cents to avoid floating point issues)
    available_balance = Column(Numeric(15, 2), nullable=False, default=0)  # Can spend
    pending_balance = Column(Numeric(15, 2), nullable=False, default=0)    # Earning pending clearance
    reserved_balance = Column(Numeric(15, 2), nullable=False, default=0)   # Reserved for in-progress jobs
    promotional_balance = Column(Numeric(15, 2), nullable=False, default=0)  # Non-withdrawable promotional credits

    # Lifetime stats
    total_purchased = Column(Numeric(15, 2), nullable=False, default=0)
    total_earned = Column(Numeric(15, 2), nullable=False, default=0)
    total_spent = Column(Numeric(15, 2), nullable=False, default=0)
    total_withdrawn = Column(Numeric(15, 2), nullable=False, default=0)

    # Settings
    low_balance_threshold = Column(Numeric(15, 2), default=10.00)
    auto_reload_amount = Column(Numeric(15, 2), nullable=True)  # Auto top-up
    auto_reload_threshold = Column(Numeric(15, 2), nullable=True)

    # Currency
    currency = Column(String(3), nullable=False, default="USD")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_credit_balance_owner", "owner_type", "owner_id", unique=True),
        CheckConstraint("available_balance >= 0", name="ck_available_balance_positive"),
    )

    @property
    def total_balance(self) -> Decimal:
        """Total balance including pending and promotional."""
        return self.available_balance + self.pending_balance + self.promotional_balance

    @property
    def spendable_balance(self) -> Decimal:
        """Total balance that can be spent (available + promotional)."""
        return self.available_balance + self.promotional_balance

    @property
    def withdrawable_balance(self) -> Decimal:
        """Balance that can be withdrawn (excludes promotional)."""
        return self.available_balance

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "owner_type": self.owner_type,
            "owner_id": str(self.owner_id),
            "available_balance": float(self.available_balance),
            "pending_balance": float(self.pending_balance),
            "reserved_balance": float(self.reserved_balance),
            "promotional_balance": float(self.promotional_balance),
            "total_balance": float(self.total_balance),
            "spendable_balance": float(self.spendable_balance),
            "withdrawable_balance": float(self.withdrawable_balance),
            "total_earned": float(self.total_earned),
            "total_spent": float(self.total_spent),
            "currency": self.currency,
        }


class CreditTransaction(Base):
    """Credit transaction record."""

    __tablename__ = "credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Balance reference
    balance_id = Column(UUID(as_uuid=True), ForeignKey("credit_balances.id"), nullable=False, index=True)
    balance = relationship("CreditBalance", backref="transactions")

    # Transaction details
    transaction_type = Column(Enum(TransactionType), nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)  # Positive for credit, negative for debit
    balance_after = Column(Numeric(15, 2), nullable=False)

    # Description
    description = Column(String(500), nullable=True)

    # Related entities
    job_id = Column(UUID(as_uuid=True), nullable=True, index=True)       # Related job
    service_id = Column(UUID(as_uuid=True), nullable=True)               # Related service listing
    counterparty_id = Column(UUID(as_uuid=True), nullable=True)          # Other party in transfer

    # Payment reference (for purchases)
    payment_intent_id = Column(String(255), nullable=True)
    payment_method = Column(String(50), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSON, default=dict)

    # Status
    status = Column(String(50), nullable=False, default="completed")  # pending, completed, failed, reversed

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_credit_tx_created", "created_at"),
        Index("ix_credit_tx_type_date", "transaction_type", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.transaction_type.value,
            "amount": float(self.amount),
            "balance_after": float(self.balance_after),
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class CreditPackage(Base):
    """Predefined credit packages for purchase."""

    __tablename__ = "credit_packages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Pricing
    credit_amount = Column(Numeric(15, 2), nullable=False)  # Credits received
    price_cents = Column(Integer, nullable=False)            # Price in cents
    currency = Column(String(3), nullable=False, default="USD")

    # Bonus
    bonus_credits = Column(Numeric(15, 2), default=0)  # Extra credits

    # Validity
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    # Stripe
    stripe_price_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "credit_amount": float(self.credit_amount),
            "bonus_credits": float(self.bonus_credits),
            "total_credits": float(self.credit_amount + self.bonus_credits),
            "price": self.price_cents / 100,
            "currency": self.currency,
        }


class CreditReservation(Base):
    """Reserved credits for in-progress jobs."""

    __tablename__ = "credit_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    balance_id = Column(UUID(as_uuid=True), ForeignKey("credit_balances.id"), nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    amount = Column(Numeric(15, 2), nullable=False)
    status = Column(String(50), nullable=False, default="held")  # held, released, captured

    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    released_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_reservation_job", "job_id"),
    )
