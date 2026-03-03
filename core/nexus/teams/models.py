"""Team collaboration models."""

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, ForeignKey, Enum, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class TeamRole(str, enum.Enum):
    """Team member roles."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Team(Base):
    """Team for collaborative agent management."""

    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Owner (creator)
    owner_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TeamMember(Base):
    """Team membership."""

    __tablename__ = "team_members"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    role: Mapped[TeamRole] = mapped_column(Enum(TeamRole), default=TeamRole.MEMBER)

    invited_by: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("team_id", "agent_id", name="uq_team_member"),
        Index("ix_team_members_agent", "agent_id"),
    )


class TeamInvite(Base):
    """Pending team invitation."""

    __tablename__ = "team_invites"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    invitee_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    role: Mapped[TeamRole] = mapped_column(Enum(TeamRole), default=TeamRole.MEMBER)

    # Invite token for email/link invites
    token: Mapped[str] = mapped_column(String(64), unique=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_team_invites_token", "token"),
    )


class TeamAgent(Base):
    """Agent shared with a team."""

    __tablename__ = "team_agents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Permissions for team members
    can_invoke: Mapped[bool] = mapped_column(default=True)
    can_edit: Mapped[bool] = mapped_column(default=False)
    can_manage_keys: Mapped[bool] = mapped_column(default=False)

    shared_by: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("team_id", "agent_id", name="uq_team_agent"),
    )
