"""Phone/Voice models for voice communication."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class PhoneProvider(str, enum.Enum):
    """Supported phone providers."""
    TWILIO = "twilio"
    VONAGE = "vonage"
    PLIVO = "plivo"
    TELNYX = "telnyx"
    BANDWIDTH = "bandwidth"


class CallStatus(str, enum.Enum):
    """Status of a phone call."""
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    FAILED = "failed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    CANCELED = "canceled"


class CallDirection(str, enum.Enum):
    """Direction of a call."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class PhoneNumber(Base):
    """A phone number provisioned for the system."""

    __tablename__ = "phone_numbers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number = Column(String(20), nullable=False, unique=True)
    friendly_name = Column(String(255), nullable=True)

    # Provider info
    provider = Column(Enum(PhoneProvider), nullable=False)
    provider_sid = Column(String(255), nullable=True)

    # Capabilities
    voice_enabled = Column(Boolean, default=True)
    sms_enabled = Column(Boolean, default=True)
    mms_enabled = Column(Boolean, default=False)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # Configuration
    voice_webhook_url = Column(String(1024), nullable=True)
    sms_webhook_url = Column(String(1024), nullable=True)
    fallback_url = Column(String(1024), nullable=True)

    # Voice settings
    voice_agent_id = Column(UUID(as_uuid=True), ForeignKey("voice_agents.id"), nullable=True)
    default_greeting = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    calls = relationship("PhoneCall", back_populates="phone_number")


class VoiceAgent(Base):
    """Configuration for an AI voice agent."""

    __tablename__ = "voice_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # Voice settings
    voice_provider = Column(String(50), default="elevenlabs")  # elevenlabs, openai, aws, google
    voice_id = Column(String(255), nullable=True)  # Provider-specific voice ID
    voice_settings = Column(JSON, default=dict)  # Speed, pitch, etc.

    # Speech-to-text
    stt_provider = Column(String(50), default="whisper")  # whisper, deepgram, google, aws
    stt_language = Column(String(10), default="en")
    stt_settings = Column(JSON, default=dict)

    # AI behavior
    system_prompt = Column(Text, nullable=True)
    greeting_message = Column(Text, nullable=True)
    personality = Column(JSON, default=dict)

    # Linked Nexus agent
    nexus_agent_id = Column(UUID(as_uuid=True), nullable=True)

    # Call handling
    max_call_duration = Column(Integer, default=3600)  # Seconds
    silence_timeout = Column(Integer, default=10)  # Seconds of silence before prompting
    interrupt_enabled = Column(Boolean, default=True)

    # Tools the voice agent can use
    available_tools = Column(JSON, default=list)
    available_capabilities = Column(JSON, default=list)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PhoneCall(Base):
    """A phone call record."""

    __tablename__ = "phone_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_sid = Column(String(255), unique=True, index=True)  # Provider's call ID

    phone_number_id = Column(UUID(as_uuid=True), ForeignKey("phone_numbers.id"), nullable=True)
    voice_agent_id = Column(UUID(as_uuid=True), ForeignKey("voice_agents.id"), nullable=True)

    # Call details
    direction = Column(Enum(CallDirection), nullable=False)
    status = Column(Enum(CallStatus), default=CallStatus.QUEUED)
    from_number = Column(String(20), nullable=False)
    to_number = Column(String(20), nullable=False)

    # Participants
    caller_agent_id = Column(UUID(as_uuid=True), nullable=True)
    caller_type = Column(String(50), nullable=True)  # agent, human, system

    # Call content
    transcript = Column(JSON, default=list)  # List of {speaker, text, timestamp}
    summary = Column(Text, nullable=True)
    sentiment = Column(String(50), nullable=True)
    topics = Column(JSON, default=list)

    # Timing
    queued_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    answered_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Recording
    recording_url = Column(String(1024), nullable=True)
    recording_duration = Column(Integer, nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSON, default=dict)
    tags = Column(JSON, default=list)

    # Error info
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # Linked conversation
    conversation_id = Column(UUID(as_uuid=True), nullable=True)

    phone_number = relationship("PhoneNumber", back_populates="calls")
    recordings = relationship("CallRecording", back_populates="call", cascade="all, delete-orphan")


class CallRecording(Base):
    """Recording of a phone call."""

    __tablename__ = "call_recordings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id = Column(UUID(as_uuid=True), ForeignKey("phone_calls.id", ondelete="CASCADE"), nullable=False)

    recording_sid = Column(String(255), nullable=True)
    url = Column(String(1024), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    # Transcription
    transcription_status = Column(String(50), default="pending")
    transcription = Column(Text, nullable=True)
    transcription_confidence = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    call = relationship("PhoneCall", back_populates="recordings")
