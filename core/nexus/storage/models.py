"""File storage models."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, BigInteger
from sqlalchemy.dialects.postgresql import UUID

from nexus.database import Base


class StorageProvider(str, enum.Enum):
    """Supported storage providers."""
    S3 = "s3"
    GCS = "gcs"
    AZURE = "azure"
    MINIO = "minio"
    LOCAL = "local"


class FileStatus(str, enum.Enum):
    """File status."""
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class StoredFile(Base):
    """A stored file."""

    __tablename__ = "stored_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # File identification
    key = Column(String(1024), nullable=False, index=True)  # S3 key / path
    bucket = Column(String(255), nullable=False)
    original_filename = Column(String(500), nullable=True)

    # Provider
    provider = Column(Enum(StorageProvider), default=StorageProvider.S3)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    owner_type = Column(String(50), default="agent")

    # File info
    content_type = Column(String(255), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    checksum = Column(String(64), nullable=True)  # SHA-256

    # Status
    status = Column(Enum(FileStatus), default=FileStatus.UPLOADING)

    # URLs
    url = Column(String(2048), nullable=True)  # Public URL if applicable
    cdn_url = Column(String(2048), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSON, default=dict)
    tags = Column(JSON, default=list)

    # Access control
    is_public = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=True)

    # Related entity
    entity_type = Column(String(100), nullable=True)  # message, document, recording
    entity_id = Column(UUID(as_uuid=True), nullable=True)

    # Processing
    processing_status = Column(String(50), nullable=True)
    processing_result = Column(JSON, nullable=True)

    # Versions
    version = Column(String(50), nullable=True)
    is_latest = Column(Boolean, default=True)
    parent_id = Column(UUID(as_uuid=True), nullable=True)  # Previous version

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)


class StorageBucket(Base):
    """A storage bucket/container."""

    __tablename__ = "storage_buckets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True)
    provider = Column(Enum(StorageProvider), default=StorageProvider.S3)

    # Configuration
    region = Column(String(50), nullable=True)
    endpoint = Column(String(1024), nullable=True)

    # Access
    is_public = Column(Boolean, default=False)
    cors_origins = Column(JSON, default=list)

    # Lifecycle
    retention_days = Column(BigInteger, nullable=True)
    versioning_enabled = Column(Boolean, default=False)

    # Stats
    file_count = Column(BigInteger, default=0)
    total_size_bytes = Column(BigInteger, default=0)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
