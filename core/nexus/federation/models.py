"""Federation models - Peer connections between Nexus instances."""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base


class PeerStatus(str, Enum):
    """Status of a federated peer connection."""
    PENDING = "pending"          # Invitation sent, awaiting acceptance
    ACTIVE = "active"            # Connected and communicating
    SUSPENDED = "suspended"      # Temporarily disabled
    REVOKED = "revoked"          # Permanently disconnected


class TrustLevel(str, Enum):
    """Trust level for federated peers."""
    MINIMAL = "minimal"          # Only see public capabilities
    STANDARD = "standard"        # Can invoke capabilities
    ELEVATED = "elevated"        # Can access shared memories
    FULL = "full"                # Full bidirectional access


class FederatedPeer(Base):
    """A connected Nexus instance (peer)."""

    __tablename__ = "federated_peers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Peer identification
    name: Mapped[str] = mapped_column(String(255))
    endpoint_url: Mapped[str] = mapped_column(String(500))  # Their Nexus URL
    public_key: Mapped[str] = mapped_column(Text)           # For verifying requests

    # Our credentials for them
    our_peer_id: Mapped[str] = mapped_column(String(255))   # ID they assigned us
    our_secret: Mapped[str] = mapped_column(Text)           # Secret for auth

    # Connection status
    status: Mapped[PeerStatus] = mapped_column(
        SQLEnum(PeerStatus), default=PeerStatus.PENDING
    )
    trust_level: Mapped[TrustLevel] = mapped_column(
        SQLEnum(TrustLevel), default=TrustLevel.MINIMAL
    )

    # Who initiated
    initiated_by_us: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"))

    # Stats
    requests_sent: Mapped[int] = mapped_column(Integer, default=0)
    requests_received: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner = relationship("Agent", backref="federated_peers")


class FederationRequest(Base):
    """Log of cross-instance requests for audit."""

    __tablename__ = "federation_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Which peer
    peer_id: Mapped[UUID] = mapped_column(ForeignKey("federated_peers.id"))

    # Direction
    direction: Mapped[str] = mapped_column(String(20))  # "inbound" or "outbound"

    # Request details
    request_type: Mapped[str] = mapped_column(String(50))  # "invoke", "discover", etc.
    capability_name: Mapped[str | None] = mapped_column(String(255))
    target_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))

    # Sanitized input/output (no sensitive data)
    request_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    response_summary: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Status
    status: Mapped[str] = mapped_column(String(50))  # "pending", "approved", "completed", "rejected"
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    peer = relationship("FederatedPeer", backref="requests")
