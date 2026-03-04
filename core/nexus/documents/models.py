"""Documents models for collaborative document editing."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class DocumentType(str, enum.Enum):
    """Types of documents."""
    TEXT = "text"
    MARKDOWN = "markdown"
    CODE = "code"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    FORM = "form"
    WHITEBOARD = "whiteboard"
    DIAGRAM = "diagram"


class PermissionLevel(str, enum.Enum):
    """Document permission levels."""
    OWNER = "owner"
    EDITOR = "editor"
    COMMENTER = "commenter"
    VIEWER = "viewer"


class DocumentFolder(Base):
    """A folder for organizing documents."""

    __tablename__ = "document_folders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("document_folders.id"), nullable=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # Metadata
    color = Column(String(20), nullable=True)
    icon = Column(String(50), nullable=True)

    is_starred = Column(Boolean, default=False)
    is_trashed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship("Document", back_populates="folder", cascade="all, delete-orphan")


class Document(Base):
    """A collaborative document."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Document info
    title = Column(String(500), nullable=False)
    document_type = Column(Enum(DocumentType), default=DocumentType.TEXT)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("document_folders.id"), nullable=True)

    # Content
    content = Column(Text, nullable=True)  # Main content (text, markdown, JSON for complex types)
    content_format = Column(String(50), default="text")  # text, json, binary_ref

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # Sharing
    is_public = Column(Boolean, default=False)
    public_link_id = Column(String(50), nullable=True, unique=True)
    default_permission = Column(Enum(PermissionLevel), default=PermissionLevel.VIEWER)

    # AI features
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)  # AI assistant for this doc
    ai_generated = Column(Boolean, default=False)
    ai_summary = Column(Text, nullable=True)
    embeddings = Column(JSON, nullable=True)  # Vector embeddings for semantic search

    # Collaboration
    allow_comments = Column(Boolean, default=True)
    allow_suggestions = Column(Boolean, default=True)

    # Versioning
    version = Column(Integer, default=1)
    last_editor_id = Column(UUID(as_uuid=True), nullable=True)

    # Metadata
    tags = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    word_count = Column(Integer, default=0)
    character_count = Column(Integer, default=0)

    # Status
    is_template = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    is_trashed = Column(Boolean, default=False)
    trashed_at = Column(DateTime, nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_viewed_at = Column(DateTime, nullable=True)

    folder = relationship("DocumentFolder", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    permissions = relationship("DocumentPermission", back_populates="document", cascade="all, delete-orphan")
    comments = relationship("DocumentComment", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    """A version of a document."""

    __tablename__ = "document_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    version_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)

    # Editor
    editor_id = Column(UUID(as_uuid=True), nullable=True)
    editor_type = Column(String(50), nullable=True)  # agent, human, ai

    # Change info
    change_summary = Column(Text, nullable=True)
    changes = Column(JSON, default=list)  # Diff operations

    # Size
    size_bytes = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="versions")


class DocumentPermission(Base):
    """Permission for a document."""

    __tablename__ = "document_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Grantee
    grantee_id = Column(UUID(as_uuid=True), nullable=True)
    grantee_email = Column(String(255), nullable=True)
    grantee_type = Column(String(50), default="agent")  # agent, email, link

    # Permission
    permission = Column(Enum(PermissionLevel), nullable=False)

    # Invite
    invited_by_id = Column(UUID(as_uuid=True), nullable=True)
    invited_at = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)

    # Expiry
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="permissions")


class DocumentComment(Base):
    """A comment on a document."""

    __tablename__ = "document_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Author
    author_id = Column(UUID(as_uuid=True), nullable=False)
    author_type = Column(String(50), default="agent")

    # Content
    content = Column(Text, nullable=False)

    # Position (for inline comments)
    anchor_type = Column(String(50), nullable=True)  # text_selection, cell, element
    anchor_data = Column(JSON, nullable=True)  # Position info

    # Thread
    parent_id = Column(UUID(as_uuid=True), ForeignKey("document_comments.id"), nullable=True)
    is_resolved = Column(Boolean, default=False)
    resolved_by_id = Column(UUID(as_uuid=True), nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # Suggestion (for suggesting edits)
    is_suggestion = Column(Boolean, default=False)
    suggested_content = Column(Text, nullable=True)
    suggestion_accepted = Column(Boolean, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="comments")


class DocumentActivity(Base):
    """Activity log for a document."""

    __tablename__ = "document_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Actor
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    actor_type = Column(String(50), nullable=True)

    # Action
    action = Column(String(100), nullable=False)  # created, edited, viewed, shared, commented, etc.
    details = Column(JSON, default=dict)

    # IP/session info
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(512), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
