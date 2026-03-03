"""Calendar models for scheduling and events."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class CalendarProvider(str, enum.Enum):
    """Supported calendar providers."""
    GOOGLE = "google"
    OUTLOOK = "outlook"
    APPLE = "apple"
    CALDAV = "caldav"
    INTERNAL = "internal"


class EventStatus(str, enum.Enum):
    """Status of a calendar event."""
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class AttendeeStatus(str, enum.Enum):
    """Attendee response status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"


class CalendarConnection(Base):
    """Connection to an external calendar."""

    __tablename__ = "calendar_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # Provider
    provider = Column(Enum(CalendarProvider), nullable=False)
    name = Column(String(255), nullable=True)

    # Credentials
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # Provider-specific
    calendar_id = Column(String(255), nullable=True)  # External calendar ID
    email = Column(String(255), nullable=True)

    # Sync settings
    sync_enabled = Column(Boolean, default=True)
    sync_direction = Column(String(50), default="bidirectional")  # bidirectional, push, pull
    last_sync_at = Column(DateTime, nullable=True)
    sync_token = Column(String(512), nullable=True)  # For incremental sync

    # AI scheduling
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    auto_schedule_enabled = Column(Boolean, default=False)
    working_hours = Column(JSON, default=dict)  # {mon: {start: "09:00", end: "17:00"}, ...}
    timezone = Column(String(100), default="UTC")

    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    events = relationship("CalendarEvent", back_populates="calendar", cascade="all, delete-orphan")


class CalendarEvent(Base):
    """A calendar event."""

    __tablename__ = "calendar_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calendar_id = Column(UUID(as_uuid=True), ForeignKey("calendar_connections.id", ondelete="CASCADE"), nullable=True)

    # External ID
    external_id = Column(String(255), nullable=True, index=True)
    ical_uid = Column(String(255), nullable=True)

    # Event details
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(500), nullable=True)

    # Timing
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    timezone = Column(String(100), default="UTC")
    is_all_day = Column(Boolean, default=False)

    # Status
    status = Column(Enum(EventStatus), default=EventStatus.CONFIRMED)

    # Organizer
    organizer_id = Column(UUID(as_uuid=True), nullable=True)
    organizer_email = Column(String(255), nullable=True)
    organizer_name = Column(String(255), nullable=True)

    # Recurrence
    is_recurring = Column(Boolean, default=False)
    recurrence_rule = Column(String(512), nullable=True)  # RRULE format
    recurring_event_id = Column(UUID(as_uuid=True), nullable=True)  # Parent event

    # Video conferencing
    video_link = Column(String(1024), nullable=True)
    video_provider = Column(String(50), nullable=True)
    video_room_id = Column(UUID(as_uuid=True), nullable=True)

    # Reminders
    reminders = Column(JSON, default=list)  # [{method, minutes}]

    # Metadata
    color = Column(String(20), nullable=True)
    visibility = Column(String(50), default="default")  # default, public, private
    busy_status = Column(String(50), default="busy")  # busy, free, tentative
    metadata = Column(JSON, default=dict)

    # Sync
    etag = Column(String(255), nullable=True)
    last_modified = Column(DateTime, default=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    calendar = relationship("CalendarConnection", back_populates="events")
    attendees = relationship("EventAttendee", back_populates="event", cascade="all, delete-orphan")


class EventAttendee(Base):
    """An attendee of a calendar event."""

    __tablename__ = "event_attendees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=False)

    # Attendee identity
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    email = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)

    # Status
    status = Column(Enum(AttendeeStatus), default=AttendeeStatus.PENDING)
    is_organizer = Column(Boolean, default=False)
    is_optional = Column(Boolean, default=False)

    # Response
    responded_at = Column(DateTime, nullable=True)
    comment = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    event = relationship("CalendarEvent", back_populates="attendees")


class AvailabilitySlot(Base):
    """Availability for scheduling."""

    __tablename__ = "availability_slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Time slot
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    timezone = Column(String(100), default="UTC")

    # Type
    slot_type = Column(String(50), default="available")  # available, busy, tentative
    recurrence_rule = Column(String(512), nullable=True)

    # Booking info
    is_bookable = Column(Boolean, default=True)
    booking_buffer_before = Column(Integer, default=0)  # Minutes
    booking_buffer_after = Column(Integer, default=0)
    max_booking_duration = Column(Integer, nullable=True)  # Minutes

    # Metadata
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class SchedulingLink(Base):
    """A scheduling/booking link."""

    __tablename__ = "scheduling_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # Link info
    slug = Column(String(100), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Duration options
    duration_options = Column(JSON, default=[30])  # [15, 30, 60]
    default_duration = Column(Integer, default=30)

    # Availability
    availability_schedule = Column(JSON, default=dict)  # Weekly schedule
    buffer_before = Column(Integer, default=0)
    buffer_after = Column(Integer, default=0)
    min_notice = Column(Integer, default=60)  # Minutes

    # Booking limits
    max_bookings_per_day = Column(Integer, nullable=True)
    booking_window_days = Column(Integer, default=60)

    # Questions
    questions = Column(JSON, default=list)  # Custom questions for booker

    # Confirmation
    auto_confirm = Column(Boolean, default=True)
    confirmation_redirect = Column(String(1024), nullable=True)

    # Notifications
    notify_on_booking = Column(Boolean, default=True)
    reminder_minutes = Column(JSON, default=[60, 15])

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
