"""Video models for video conferencing."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class VideoProvider(str, enum.Enum):
    """Supported video providers."""
    TWILIO = "twilio"
    DAILY = "daily"
    ZOOM = "zoom"
    VONAGE = "vonage"
    AGORA = "agora"
    LIVEKIT = "livekit"
    JITSI = "jitsi"


class RoomStatus(str, enum.Enum):
    """Status of a video room."""
    CREATED = "created"
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


class ParticipantStatus(str, enum.Enum):
    """Status of a participant."""
    INVITED = "invited"
    JOINING = "joining"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    KICKED = "kicked"


class ParticipantRole(str, enum.Enum):
    """Role of a participant."""
    HOST = "host"
    CO_HOST = "co_host"
    PRESENTER = "presenter"
    PARTICIPANT = "participant"
    VIEWER = "viewer"


class VideoRoom(Base):
    """A video conference room."""

    __tablename__ = "video_rooms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(String(255), unique=True, index=True)  # Provider's room ID

    # Room info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Provider
    provider = Column(Enum(VideoProvider), nullable=False)
    provider_config = Column(JSON, default=dict)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # Room settings
    max_participants = Column(Integer, default=50)
    is_private = Column(Boolean, default=True)
    password = Column(String(255), nullable=True)
    waiting_room_enabled = Column(Boolean, default=False)

    # Recording
    recording_enabled = Column(Boolean, default=False)
    auto_record = Column(Boolean, default=False)

    # AI features
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    transcription_enabled = Column(Boolean, default=False)
    ai_summary_enabled = Column(Boolean, default=False)
    real_time_translation = Column(Boolean, default=False)
    translation_languages = Column(JSON, default=list)

    # Status
    status = Column(Enum(RoomStatus), default=RoomStatus.CREATED)
    participant_count = Column(Integer, default=0)

    # URLs
    join_url = Column(String(1024), nullable=True)
    host_url = Column(String(1024), nullable=True)

    # Timing
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSON, default=dict)
    tags = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)

    participants = relationship("VideoParticipant", back_populates="room", cascade="all, delete-orphan")
    recordings = relationship("VideoRecording", back_populates="room", cascade="all, delete-orphan")


class VideoParticipant(Base):
    """A participant in a video room."""

    __tablename__ = "video_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("video_rooms.id", ondelete="CASCADE"), nullable=False)

    # Participant identity
    participant_id = Column(String(255), nullable=True)  # Provider's participant ID
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    agent_type = Column(String(50), nullable=True)  # human, ai, system

    # Display info
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(1024), nullable=True)

    # Status
    status = Column(Enum(ParticipantStatus), default=ParticipantStatus.INVITED)
    role = Column(Enum(ParticipantRole), default=ParticipantRole.PARTICIPANT)

    # Media state
    audio_enabled = Column(Boolean, default=True)
    video_enabled = Column(Boolean, default=True)
    screen_sharing = Column(Boolean, default=False)
    hand_raised = Column(Boolean, default=False)

    # Permissions
    can_speak = Column(Boolean, default=True)
    can_share_screen = Column(Boolean, default=True)
    can_chat = Column(Boolean, default=True)

    # Timing
    invited_at = Column(DateTime, default=datetime.utcnow)
    joined_at = Column(DateTime, nullable=True)
    left_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Connection info
    connection_quality = Column(String(50), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(512), nullable=True)

    room = relationship("VideoRoom", back_populates="participants")


class VideoRecording(Base):
    """Recording of a video session."""

    __tablename__ = "video_recordings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("video_rooms.id", ondelete="CASCADE"), nullable=False)

    recording_id = Column(String(255), nullable=True)  # Provider's recording ID

    # Recording info
    status = Column(String(50), default="processing")
    url = Column(String(1024), nullable=True)
    download_url = Column(String(1024), nullable=True)

    # File info
    file_size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    format = Column(String(50), default="mp4")
    resolution = Column(String(50), nullable=True)

    # Transcription
    transcription_status = Column(String(50), default="pending")
    transcription = Column(JSON, default=list)  # [{speaker, text, start_time, end_time}]

    # AI summary
    summary = Column(Text, nullable=True)
    action_items = Column(JSON, default=list)
    key_topics = Column(JSON, default=list)

    # Timing
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("VideoRoom", back_populates="recordings")


class ScheduledMeeting(Base):
    """A scheduled video meeting."""

    __tablename__ = "scheduled_meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Meeting info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    agenda = Column(Text, nullable=True)

    # Organizer
    organizer_id = Column(UUID(as_uuid=True), nullable=False)
    organizer_type = Column(String(50), default="agent")

    # Provider
    provider = Column(Enum(VideoProvider), nullable=False)
    room_settings = Column(JSON, default=dict)

    # Schedule
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    timezone = Column(String(100), default="UTC")

    # Recurrence
    is_recurring = Column(Boolean, default=False)
    recurrence_rule = Column(String(255), nullable=True)  # RRULE format
    recurrence_end = Column(DateTime, nullable=True)

    # Invitees
    invitees = Column(JSON, default=list)  # [{agent_id, email, status}]

    # Room reference
    room_id = Column(UUID(as_uuid=True), ForeignKey("video_rooms.id"), nullable=True)

    # Reminders
    reminder_minutes = Column(JSON, default=[15, 5])  # Minutes before meeting

    # Status
    status = Column(String(50), default="scheduled")  # scheduled, in_progress, completed, cancelled

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
