"""Profile and personalization models."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base


class AgentProfile(Base):
    """Extended profile information for an agent."""

    __tablename__ = "agent_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), unique=True)

    # Display info
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    banner_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(500))

    # Contact
    contact_email: Mapped[str | None] = mapped_column(String(255))

    # Social links
    social_links: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"twitter": "...", "github": "..."}

    # Location/timezone
    timezone: Mapped[str | None] = mapped_column(String(50))
    locale: Mapped[str] = mapped_column(String(10), default="en-US")

    # Preferences
    theme: Mapped[str] = mapped_column(String(20), default="system")  # light/dark/system

    # Stats (public)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="profile")


class AgentSettings(Base):
    """Agent settings and preferences."""

    __tablename__ = "agent_settings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), unique=True)

    # Notification settings
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_invocation: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_message: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_team_activity: Mapped[bool] = mapped_column(Boolean, default=True)

    # Privacy settings
    show_online_status: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_discovery: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_invocations: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_messages: Mapped[bool] = mapped_column(Boolean, default=True)

    # Default behavior
    default_memory_scope: Mapped[str] = mapped_column(String(20), default="agent")
    default_invocation_timeout: Mapped[int] = mapped_column(Integer, default=300)  # seconds
    auto_complete_invocations: Mapped[bool] = mapped_column(Boolean, default=False)

    # Rate limit preferences
    max_concurrent_invocations: Mapped[int] = mapped_column(Integer, default=10)

    # AI behavior defaults
    default_temperature: Mapped[float | None] = mapped_column(default=None)
    default_max_tokens: Mapped[int | None] = mapped_column(Integer, default=None)

    # Custom data
    custom_settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="settings")


class PromptType(str, Enum):
    """Types of custom prompts."""
    SYSTEM = "system"           # Base system prompt
    PERSONA = "persona"         # Agent personality/character
    INSTRUCTION = "instruction"  # Task-specific instructions
    CONTEXT = "context"         # Background context
    TEMPLATE = "template"       # Reusable template


class CustomPrompt(Base):
    """Custom prompts for agent personalization."""

    __tablename__ = "custom_prompts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"))

    # Prompt info
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    prompt_type: Mapped[PromptType] = mapped_column(
        SQLEnum(PromptType), default=PromptType.INSTRUCTION
    )

    # The actual prompt content
    content: Mapped[str] = mapped_column(Text)

    # Variables that can be substituted (e.g., {{user_name}})
    variables: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Usage
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # Use by default
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)

    # Organization
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    category: Mapped[str | None] = mapped_column(String(100))

    # For specific capabilities (optional)
    capability_name: Mapped[str | None] = mapped_column(String(255))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="custom_prompts")


class AgentSubscription(Base):
    """Subscription/membership status for agents."""

    __tablename__ = "agent_subscriptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), unique=True)

    # Stripe info
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255))

    # Plan
    plan_name: Mapped[str] = mapped_column(String(50), default="free")  # free/pro/enterprise
    plan_status: Mapped[str] = mapped_column(String(50), default="active")  # active/canceled/past_due

    # Billing
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly/yearly
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Cancellation
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    # Usage limits based on plan
    max_agents: Mapped[int] = mapped_column(Integer, default=3)
    max_invocations_per_month: Mapped[int] = mapped_column(Integer, default=1000)
    max_memory_mb: Mapped[int] = mapped_column(Integer, default=100)
    max_team_members: Mapped[int] = mapped_column(Integer, default=1)

    # Current usage
    current_invocations: Mapped[int] = mapped_column(Integer, default=0)
    current_memory_mb: Mapped[int] = mapped_column(Integer, default=0)
    usage_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="subscription")
