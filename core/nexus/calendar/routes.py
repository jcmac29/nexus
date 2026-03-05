"""Calendar API routes."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.calendar.service import CalendarService
from nexus.calendar.models import CalendarProvider, EventStatus, AttendeeStatus

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CreateCalendarRequest(BaseModel):
    provider: str = "internal"
    name: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    calendar_id: str | None = None
    email: str | None = None
    timezone: str = "UTC"
    working_hours: dict | None = None
    is_primary: bool = False


class CreateEventRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    calendar_id: str | None = None
    description: str | None = None
    location: str | None = None
    timezone: str = "UTC"
    is_all_day: bool = False
    attendee_emails: list[str] | None = None
    attendee_ids: list[str] | None = None
    video_link: str | None = None
    reminders: list[dict] | None = None
    recurrence_rule: str | None = None


class UpdateEventRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    status: str | None = None


class RespondToEventRequest(BaseModel):
    status: str  # accepted, declined, tentative
    comment: str | None = None


class CreateSchedulingLinkRequest(BaseModel):
    slug: str
    title: str
    description: str | None = None
    duration_options: list[int] | None = None
    default_duration: int = 30
    availability_schedule: dict | None = None
    buffer_before: int = 0
    buffer_after: int = 0
    min_notice: int = 60


class BookSlotRequest(BaseModel):
    start_time: str
    duration_minutes: int
    booker_email: str
    booker_name: str | None = None
    answers: dict | None = None


@router.post("/calendars")
async def create_calendar(
    request: CreateCalendarRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a calendar connection."""
    service = CalendarService(db)

    provider_map = {
        "google": CalendarProvider.GOOGLE,
        "outlook": CalendarProvider.OUTLOOK,
        "apple": CalendarProvider.APPLE,
        "caldav": CalendarProvider.CALDAV,
        "internal": CalendarProvider.INTERNAL,
    }

    calendar = await service.create_calendar(
        owner_id=agent.id,
        provider=provider_map.get(request.provider, CalendarProvider.INTERNAL),
        name=request.name,
        access_token=request.access_token,
        refresh_token=request.refresh_token,
        calendar_id=request.calendar_id,
        email=request.email,
        timezone=request.timezone,
        working_hours=request.working_hours,
        is_primary=request.is_primary,
    )

    return {
        "id": str(calendar.id),
        "name": calendar.name,
        "provider": calendar.provider.value,
        "is_primary": calendar.is_primary,
    }


@router.get("/calendars")
async def list_calendars(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List calendars."""
    service = CalendarService(db)
    calendars = await service.list_calendars(agent.id)

    return [
        {
            "id": str(c.id),
            "name": c.name,
            "provider": c.provider.value,
            "is_primary": c.is_primary,
            "timezone": c.timezone,
            "sync_enabled": c.sync_enabled,
        }
        for c in calendars
    ]


@router.post("/events")
async def create_event(
    request: CreateEventRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a calendar event."""
    service = CalendarService(db)

    event = await service.create_event(
        calendar_id=UUID(request.calendar_id) if request.calendar_id else None,
        title=request.title,
        start_time=datetime.fromisoformat(request.start_time),
        end_time=datetime.fromisoformat(request.end_time),
        organizer_id=agent.id,
        description=request.description,
        location=request.location,
        timezone=request.timezone,
        is_all_day=request.is_all_day,
        attendee_emails=request.attendee_emails,
        attendee_ids=[UUID(aid) for aid in request.attendee_ids] if request.attendee_ids else None,
        video_link=request.video_link,
        reminders=request.reminders,
        recurrence_rule=request.recurrence_rule,
    )

    return {
        "id": str(event.id),
        "title": event.title,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "status": event.status.value,
    }


@router.get("/events")
async def get_events(
    start_date: str | None = None,
    end_date: str | None = None,
    calendar_id: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get calendar events."""
    service = CalendarService(db)

    start = datetime.fromisoformat(start_date) if start_date else datetime.utcnow()
    end = datetime.fromisoformat(end_date) if end_date else start + timedelta(days=30)

    events = await service.get_events(
        owner_id=agent.id,
        start_date=start,
        end_date=end,
        calendar_id=UUID(calendar_id) if calendar_id else None,
    )

    return [
        {
            "id": str(e.id),
            "title": e.title,
            "description": e.description,
            "location": e.location,
            "start_time": e.start_time.isoformat(),
            "end_time": e.end_time.isoformat(),
            "is_all_day": e.is_all_day,
            "status": e.status.value,
            "video_link": e.video_link,
        }
        for e in events
    ]


@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a calendar event."""
    from sqlalchemy import select
    from nexus.calendar.models import CalendarEvent, EventAttendee

    result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.id == UUID(event_id))
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # SECURITY: Check if agent is organizer or attendee
    attendee_result = await db.execute(
        select(EventAttendee).where(
            EventAttendee.event_id == UUID(event_id),
            EventAttendee.agent_id == agent.id,
        )
    )
    is_attendee = attendee_result.scalar_one_or_none() is not None

    if event.organizer_id != agent.id and not is_attendee:
        raise HTTPException(status_code=403, detail="Not authorized to view this event")

    result = await db.execute(
        select(EventAttendee).where(EventAttendee.event_id == UUID(event_id))
    )
    attendees = result.scalars().all()

    return {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "timezone": event.timezone,
        "is_all_day": event.is_all_day,
        "status": event.status.value,
        "video_link": event.video_link,
        "is_recurring": event.is_recurring,
        "recurrence_rule": event.recurrence_rule,
        "attendees": [
            {
                "id": str(a.id),
                "email": a.email,
                "name": a.name,
                "status": a.status.value,
                "is_organizer": a.is_organizer,
            }
            for a in attendees
        ],
    }


@router.patch("/events/{event_id}")
async def update_event(
    event_id: str,
    request: UpdateEventRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update a calendar event."""
    service = CalendarService(db)

    status_map = {
        "confirmed": EventStatus.CONFIRMED,
        "tentative": EventStatus.TENTATIVE,
        "cancelled": EventStatus.CANCELLED,
    }

    try:
        event = await service.update_event(
            event_id=UUID(event_id),
            agent_id=agent.id,
            title=request.title,
            description=request.description,
            start_time=datetime.fromisoformat(request.start_time) if request.start_time else None,
            end_time=datetime.fromisoformat(request.end_time) if request.end_time else None,
            location=request.location,
            status=status_map.get(request.status) if request.status else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=403 if "Not authorized" in str(e) else 404, detail=str(e))

    return {
        "id": str(event.id),
        "title": event.title,
        "status": event.status.value,
    }


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Delete a calendar event."""
    service = CalendarService(db)
    try:
        await service.delete_event(UUID(event_id), agent.id)
    except ValueError as e:
        raise HTTPException(status_code=403 if "Not authorized" in str(e) else 404, detail=str(e))
    return {"status": "deleted"}


@router.post("/events/{event_id}/respond")
async def respond_to_event(
    event_id: str,
    request: RespondToEventRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Respond to an event invitation."""
    service = CalendarService(db)

    status_map = {
        "accepted": AttendeeStatus.ACCEPTED,
        "declined": AttendeeStatus.DECLINED,
        "tentative": AttendeeStatus.TENTATIVE,
    }

    await service.respond_to_event(
        event_id=UUID(event_id),
        agent_id=agent.id,
        status=status_map.get(request.status, AttendeeStatus.PENDING),
        comment=request.comment,
    )

    return {"status": "responded"}


@router.get("/availability")
async def get_availability(
    start_date: str | None = None,
    end_date: str | None = None,
    duration_minutes: int = 30,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get available time slots."""
    service = CalendarService(db)

    start = datetime.fromisoformat(start_date) if start_date else datetime.utcnow()
    end = datetime.fromisoformat(end_date) if end_date else start + timedelta(days=7)

    slots = await service.get_availability(
        owner_id=agent.id,
        start_date=start,
        end_date=end,
        duration_minutes=duration_minutes,
    )

    return {"slots": slots}


@router.post("/scheduling-links")
async def create_scheduling_link(
    request: CreateSchedulingLinkRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a scheduling link."""
    service = CalendarService(db)

    link = await service.create_scheduling_link(
        owner_id=agent.id,
        slug=request.slug,
        title=request.title,
        description=request.description,
        duration_options=request.duration_options,
        default_duration=request.default_duration,
        availability_schedule=request.availability_schedule,
        buffer_before=request.buffer_before,
        buffer_after=request.buffer_after,
        min_notice=request.min_notice,
    )

    return {
        "id": str(link.id),
        "slug": link.slug,
        "title": link.title,
    }


@router.post("/scheduling-links/{link_id}/book")
async def book_slot(
    link_id: str,
    request: BookSlotRequest,
    db: AsyncSession = Depends(get_db),
):
    """Book a slot from a scheduling link (public endpoint)."""
    service = CalendarService(db)

    event = await service.book_slot(
        link_id=UUID(link_id),
        start_time=datetime.fromisoformat(request.start_time),
        duration_minutes=request.duration_minutes,
        booker_email=request.booker_email,
        booker_name=request.booker_name,
        answers=request.answers,
    )

    return {
        "event_id": str(event.id),
        "title": event.title,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
    }
