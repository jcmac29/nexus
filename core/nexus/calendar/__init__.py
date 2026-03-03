"""Calendar module - Scheduling and events for AI and human agents."""

from nexus.calendar.models import CalendarConnection, CalendarEvent, EventAttendee, AvailabilitySlot, SchedulingLink
from nexus.calendar.service import CalendarService
from nexus.calendar.routes import router

__all__ = [
    "CalendarConnection", "CalendarEvent", "EventAttendee",
    "AvailabilitySlot", "SchedulingLink", "CalendarService", "router"
]
