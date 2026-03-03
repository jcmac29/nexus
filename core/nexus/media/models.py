"""Media storage models."""

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import String, Integer, DateTime, ForeignKey, BigInteger, Enum, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class MediaType(str, enum.Enum):
    """Type of media file."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    OTHER = "other"


class MediaStatus(str, enum.Enum):
    """Media file status."""
    UPLOADING = "uploading"
    READY = "ready"
    PROCESSING = "processing"
    FAILED = "failed"
    DELETED = "deleted"


class MediaFile(Base):
    """Stored media file."""

    __tablename__ = "media_files"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Owner
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # File info
    filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))  # MIME type
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType))
    size_bytes: Mapped[int] = mapped_column(BigInteger)

    # Storage location
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)  # S3/MinIO key
    storage_bucket: Mapped[str] = mapped_column(String(100), default="nexus-media")

    # Status
    status: Mapped[MediaStatus] = mapped_column(Enum(MediaStatus), default=MediaStatus.UPLOADING)

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)  # JSON string

    # Access control
    is_public: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_media_files_agent", "agent_id"),
        Index("ix_media_files_status", "status"),
    )


class MediaShare(Base):
    """Share media with another agent."""

    __tablename__ = "media_shares"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    media_id: Mapped[UUID] = mapped_column(ForeignKey("media_files.id", ondelete="CASCADE"))
    shared_with_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    shared_by_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Permissions
    can_download: Mapped[bool] = mapped_column(default=True)
    can_reshare: Mapped[bool] = mapped_column(default=False)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_media_shares_media", "media_id"),
        Index("ix_media_shares_agent", "shared_with_agent_id"),
    )
