"""SMS models for text messaging."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class SMSStatus(str, enum.Enum):
    """Status of an SMS message."""
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RECEIVED = "received"


class SMSDirection(str, enum.Enum):
    """Direction of SMS."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SMSConversation(Base):
    """An SMS conversation thread."""

    __tablename__ = "sms_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Phone numbers involved
    nexus_number = Column(String(20), nullable=False)
    external_number = Column(String(20), nullable=False)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # AI agent handling this conversation
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    auto_reply_enabled = Column(Boolean, default=False)
    system_prompt = Column(Text, nullable=True)

    # Context
    context = Column(JSON, default=dict)
    tags = Column(JSON, default=list)

    # Stats
    message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("SMSMessage", back_populates="conversation", cascade="all, delete-orphan")


class SMSMessage(Base):
    """An SMS message."""

    __tablename__ = "sms_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_sid = Column(String(255), unique=True, nullable=True)

    conversation_id = Column(UUID(as_uuid=True), ForeignKey("sms_conversations.id"), nullable=True)

    # Message details
    direction = Column(Enum(SMSDirection), nullable=False)
    status = Column(Enum(SMSStatus), default=SMSStatus.QUEUED)
    from_number = Column(String(20), nullable=False)
    to_number = Column(String(20), nullable=False)
    body = Column(Text, nullable=False)

    # Media (MMS)
    media_urls = Column(JSON, default=list)
    num_media = Column(Integer, default=0)

    # Sender info
    sender_id = Column(UUID(as_uuid=True), nullable=True)
    sender_type = Column(String(50), nullable=True)  # agent, human, system

    # Delivery info
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    conversation = relationship("SMSConversation", back_populates="messages")
