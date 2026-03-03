"""Email models for email communication."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class EmailProvider(str, enum.Enum):
    """Supported email providers."""
    SENDGRID = "sendgrid"
    MAILGUN = "mailgun"
    SES = "ses"
    POSTMARK = "postmark"
    SMTP = "smtp"
    RESEND = "resend"


class EmailStatus(str, enum.Enum):
    """Status of an email."""
    DRAFT = "draft"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"
    SPAM = "spam"


class EmailDirection(str, enum.Enum):
    """Direction of email."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EmailPriority(str, enum.Enum):
    """Email priority level."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class EmailAccount(Base):
    """An email account for sending/receiving."""

    __tablename__ = "email_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Account info
    email_address = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)

    # Provider config
    provider = Column(Enum(EmailProvider), nullable=False)
    provider_config = Column(JSON, default=dict)  # API keys, SMTP settings

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # AI agent for auto-responses
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    auto_reply_enabled = Column(Boolean, default=False)
    auto_reply_prompt = Column(Text, nullable=True)

    # Signature
    signature_html = Column(Text, nullable=True)
    signature_text = Column(Text, nullable=True)

    # Sync settings
    imap_enabled = Column(Boolean, default=False)
    last_sync_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    emails = relationship("Email", back_populates="account", cascade="all, delete-orphan")


class EmailThread(Base):
    """An email conversation thread."""

    __tablename__ = "email_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Thread identification
    thread_id = Column(String(255), nullable=True, index=True)  # Provider's thread ID
    subject = Column(String(1024), nullable=True)

    # Participants
    participants = Column(JSON, default=list)  # List of email addresses

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("email_accounts.id"), nullable=True)

    # AI handling
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    ai_context = Column(JSON, default=dict)

    # Status
    message_count = Column(Integer, default=0)
    unread_count = Column(Integer, default=0)
    last_message_at = Column(DateTime, nullable=True)

    # Labels/folders
    labels = Column(JSON, default=list)
    is_starred = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    emails = relationship("Email", back_populates="thread", cascade="all, delete-orphan")


class Email(Base):
    """An email message."""

    __tablename__ = "emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(String(255), unique=True, nullable=True, index=True)  # RFC 2822 Message-ID

    account_id = Column(UUID(as_uuid=True), ForeignKey("email_accounts.id"), nullable=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("email_threads.id"), nullable=True)

    # Email details
    direction = Column(Enum(EmailDirection), nullable=False)
    status = Column(Enum(EmailStatus), default=EmailStatus.DRAFT)
    priority = Column(Enum(EmailPriority), default=EmailPriority.NORMAL)

    # Addresses
    from_address = Column(String(255), nullable=False)
    from_name = Column(String(255), nullable=True)
    to_addresses = Column(JSON, default=list)  # [{email, name}]
    cc_addresses = Column(JSON, default=list)
    bcc_addresses = Column(JSON, default=list)
    reply_to = Column(String(255), nullable=True)

    # Content
    subject = Column(String(1024), nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)

    # Attachments
    attachments = Column(JSON, default=list)  # [{filename, content_type, size, url}]

    # Headers
    headers = Column(JSON, default=dict)
    in_reply_to = Column(String(255), nullable=True)  # Message-ID being replied to
    references = Column(JSON, default=list)  # Thread of Message-IDs

    # Sender info
    sender_id = Column(UUID(as_uuid=True), nullable=True)
    sender_type = Column(String(50), nullable=True)  # agent, human, ai

    # Tracking
    opened_at = Column(DateTime, nullable=True)
    open_count = Column(Integer, default=0)
    clicked_at = Column(DateTime, nullable=True)
    click_count = Column(Integer, default=0)

    # Delivery info
    provider_message_id = Column(String(255), nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    bounced_at = Column(DateTime, nullable=True)
    bounce_reason = Column(Text, nullable=True)

    # AI analysis
    ai_summary = Column(Text, nullable=True)
    ai_sentiment = Column(String(50), nullable=True)
    ai_categories = Column(JSON, default=list)
    ai_suggested_reply = Column(Text, nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)

    # Metadata
    is_read = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    labels = Column(JSON, default=list)

    account = relationship("EmailAccount", back_populates="emails")
    thread = relationship("EmailThread", back_populates="emails")


class EmailTemplate(Base):
    """Reusable email template."""

    __tablename__ = "email_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # Template content
    subject_template = Column(String(1024), nullable=True)
    body_text_template = Column(Text, nullable=True)
    body_html_template = Column(Text, nullable=True)

    # Variables
    variables = Column(JSON, default=list)  # [{name, description, default}]

    # Category
    category = Column(String(100), nullable=True)
    tags = Column(JSON, default=list)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
