"""Budgets database models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base

if TYPE_CHECKING:
    from nexus.identity.models import Agent


class BudgetType(str, enum.Enum):
    """Type of budget."""

    API_CALLS = "api_calls"
    TOKENS = "tokens"
    CREDITS = "credits"
    COMPUTE_SECONDS = "compute_seconds"
    STORAGE_BYTES = "storage_bytes"
    BANDWIDTH_BYTES = "bandwidth_bytes"
    CUSTOM = "custom"
    # Additional types for backward compatibility with tests
    MEMORY = "memory"
    STORAGE = "storage"
    COMPUTE = "compute"


class Budget(Base):
    """A budget allocation for an agent."""

    __tablename__ = "budgets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Budget type
    budget_type: Mapped[BudgetType] = mapped_column(Enum(BudgetType))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    # Limits
    total_limit: Mapped[int] = mapped_column(BigInteger)
    used_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_amount: Mapped[int] = mapped_column(BigInteger, default=0)

    # Computed
    @property
    def available_amount(self) -> int:
        return self.total_limit - self.used_amount - self.reserved_amount

    @property
    def usage_percent(self) -> float:
        if self.total_limit == 0:
            return 0.0
        return (self.used_amount / self.total_limit) * 100

    # Period
    period_type: Mapped[str] = mapped_column(String(20), default="monthly")
    # hourly, daily, weekly, monthly, yearly, lifetime
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Alerts
    alert_threshold: Mapped[float] = mapped_column(Float, default=0.8)  # 80%
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_exceeded: Mapped[bool] = mapped_column(Boolean, default=False)

    # Config
    config: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")
    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation", back_populates="budget", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("agent_id", "budget_type", "name", name="uq_budget_agent_type_name"),
        Index("ix_budgets_agent_type", "agent_id", "budget_type"),
    )


class ReservationStatus(str, enum.Enum):
    """Status of a budget reservation."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CONSUMED = "consumed"
    RELEASED = "released"
    EXPIRED = "expired"


class Reservation(Base):
    """A reservation of budget for a specific task."""

    __tablename__ = "budget_reservations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    budget_id: Mapped[UUID] = mapped_column(ForeignKey("budgets.id"), index=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Reservation details
    amount: Mapped[int] = mapped_column(BigInteger)
    purpose: Mapped[str | None] = mapped_column(Text)

    # Status
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus), default=ReservationStatus.PENDING
    )

    # Actual usage
    actual_amount: Mapped[int | None] = mapped_column(BigInteger)

    # Timing
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Related
    task_id: Mapped[UUID | None] = mapped_column()
    goal_id: Mapped[UUID | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    budget: Mapped["Budget"] = relationship("Budget", back_populates="reservations")
    agent: Mapped["Agent"] = relationship("Agent")

    __table_args__ = (
        Index("ix_reservations_budget_status", "budget_id", "status"),
    )


class UsageRecord(Base):
    """A record of budget usage."""

    __tablename__ = "budget_usage_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    budget_id: Mapped[UUID] = mapped_column(ForeignKey("budgets.id"), index=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    reservation_id: Mapped[UUID | None] = mapped_column(ForeignKey("budget_reservations.id"))

    # Usage
    amount: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    # Context
    metadata_: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    budget: Mapped["Budget"] = relationship("Budget")
    agent: Mapped["Agent"] = relationship("Agent")

    __table_args__ = (
        Index("ix_usage_records_budget_created", "budget_id", "created_at"),
    )
