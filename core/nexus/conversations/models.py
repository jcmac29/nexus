"""Conversation models for persistent dialogue threads."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class ParticipantType(str, enum.Enum):
    """Type of conversation participant."""
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


class ConversationStatus(str, enum.Enum):
    """Status of a conversation."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Conversation(Base):
    """A conversation thread between agents and/or humans."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(Enum(ConversationStatus), default=ConversationStatus.ACTIVE)

    # Conversation context/purpose
    context = Column(JSON, default=dict)
    # Shared memory/state for the conversation
    shared_state = Column(JSON, default=dict)

    # Creator (can be agent or human)
    creator_id = Column(UUID(as_uuid=True), nullable=False)
    creator_type = Column(Enum(ParticipantType), default=ParticipantType.AGENT)

    # Team association (optional)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    # Message count for quick access
    message_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)

    # Relationships
    participants = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationParticipant(Base):
    """A participant in a conversation."""

    __tablename__ = "conversation_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)

    # Participant identity
    participant_id = Column(UUID(as_uuid=True), nullable=False)
    participant_type = Column(Enum(ParticipantType), default=ParticipantType.AGENT)
    display_name = Column(String(255), nullable=True)

    # Role in conversation
    role = Column(String(50), default="participant")  # owner, moderator, participant, observer

    # Participant state
    is_active = Column(Boolean, default=True)
    last_read_at = Column(DateTime, nullable=True)
    last_typed_at = Column(DateTime, nullable=True)

    # Participant-specific context
    context = Column(JSON, default=dict)

    joined_at = Column(DateTime, default=datetime.utcnow)
    left_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation", back_populates="participants")


class ConversationMessage(Base):
    """A message in a conversation thread."""

    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)

    # Sender
    sender_id = Column(UUID(as_uuid=True), nullable=False)
    sender_type = Column(Enum(ParticipantType), default=ParticipantType.AGENT)
    sender_name = Column(String(255), nullable=True)

    # Message content
    content = Column(Text, nullable=False)
    content_type = Column(String(50), default="text")  # text, code, image, file, tool_call, tool_result

    # For tool calls/results
    tool_name = Column(String(255), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)

    # Message metadata
    metadata_ = Column("metadata", JSON, default=dict)

    # Reply threading
    reply_to_id = Column(UUID(as_uuid=True), ForeignKey("conversation_messages.id"), nullable=True)

    # Reactions (emoji -> list of participant_ids)
    reactions = Column(JSON, default=dict)

    # Edit tracking
    is_edited = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    replies = relationship("ConversationMessage", backref="parent", remote_side=[id])
