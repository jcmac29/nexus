"""Calendar service for scheduling and events."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.calendar.models import (
    CalendarConnection, CalendarEvent, EventAttendee, AvailabilitySlot, SchedulingLink,
    CalendarProvider, EventStatus, AttendeeStatus
)


class CalendarService:
    """Service for calendar operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._providers = {}

    def configure_google(self, credentials: dict):
        """Configure Google Calendar."""
        self._providers["google"] = credentials

    def configure_outlook(self, client_id: str, client_secret: str):
        """Configure Outlook Calendar."""
        self._providers["outlook"] = {
            "client_id": client_id,
            "client_secret": client_secret,
        }

    async def create_calendar(
        self,
        owner_id: UUID,
        provider: CalendarProvider,
        name: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        calendar_id: str | None = None,
        email: str | None = None,
        timezone: str = "UTC",
        working_hours: dict | None = None,
        is_primary: bool = False,
    ) -> CalendarConnection:
        """Create a calendar connection."""
        calendar = CalendarConnection(
            owner_id=owner_id,
            provider=provider,
            name=name or f"{provider.value} Calendar",
            access_token=access_token,
            refresh_token=refresh_token,
            calendar_id=calendar_id,
            email=email,
            timezone=timezone,
            working_hours=working_hours or {},
            is_primary=is_primary,
        )
        self.db.add(calendar)
        await self.db.commit()
        await self.db.refresh(calendar)
        return calendar

    async def create_event(
        self,
        calendar_id: UUID | None,
        title: str,
        start_time: datetime,
        end_time: datetime,
        organizer_id: UUID | None = None,
        description: str | None = None,
        location: str | None = None,
        timezone: str = "UTC",
        is_all_day: bool = False,
        attendee_emails: list[str] | None = None,
        attendee_ids: list[UUID] | None = None,
        video_link: str | None = None,
        reminders: list[dict] | None = None,
        recurrence_rule: str | None = None,
    ) -> CalendarEvent:
        """Create a calendar event."""
        event = CalendarEvent(
            calendar_id=calendar_id,
            title=title,
            description=description,
            location=location,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            is_all_day=is_all_day,
            organizer_id=organizer_id,
            video_link=video_link,
            reminders=reminders or [],
            is_recurring=bool(recurrence_rule),
            recurrence_rule=recurrence_rule,
        )
        self.db.add(event)
        await self.db.flush()

        # Add attendees
        if attendee_emails:
            for email in attendee_emails:
                attendee = EventAttendee(
                    event_id=event.id,
                    email=email,
                )
                self.db.add(attendee)

        if attendee_ids:
            for agent_id in attendee_ids:
                attendee = EventAttendee(
                    event_id=event.id,
                    agent_id=agent_id,
                )
                self.db.add(attendee)

        # Sync to external calendar if connected
        if calendar_id:
            await self._sync_event_to_provider(event)

        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def _sync_event_to_provider(self, event: CalendarEvent):
        """Sync event to external calendar provider."""
        if not event.calendar_id:
            return

        result = await self.db.execute(
            select(CalendarConnection).where(CalendarConnection.id == event.calendar_id)
        )
        calendar = result.scalar_one_or_none()
        if not calendar or not calendar.sync_enabled:
            return

        if calendar.provider == CalendarProvider.GOOGLE and "google" in self._providers:
            # Google Calendar API sync
            pass
        elif calendar.provider == CalendarProvider.OUTLOOK and "outlook" in self._providers:
            # Microsoft Graph API sync
            pass

    async def update_event(
        self,
        event_id: UUID,
        agent_id: UUID,
        title: str | None = None,
        description: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        location: str | None = None,
        status: EventStatus | None = None,
    ) -> CalendarEvent:
        """Update a calendar event."""
        result = await self.db.execute(
            select(CalendarEvent).where(CalendarEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError("Event not found")

        # SECURITY: Verify ownership before modification
        if event.organizer_id != agent_id:
            raise ValueError("Not authorized to modify this event")

        if title is not None:
            event.title = title
        if description is not None:
            event.description = description
        if start_time is not None:
            event.start_time = start_time
        if end_time is not None:
            event.end_time = end_time
        if location is not None:
            event.location = location
        if status is not None:
            event.status = status

        event.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def delete_event(self, event_id: UUID, agent_id: UUID):
        """Delete a calendar event."""
        result = await self.db.execute(
            select(CalendarEvent).where(CalendarEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError("Event not found")

        # SECURITY: Verify ownership before deletion
        if event.organizer_id != agent_id:
            raise ValueError("Not authorized to delete this event")

        await self.db.delete(event)
        await self.db.commit()

    async def respond_to_event(
        self,
        event_id: UUID,
        agent_id: UUID,
        status: AttendeeStatus,
        comment: str | None = None,
    ):
        """Respond to an event invitation."""
        result = await self.db.execute(
            select(EventAttendee).where(
                and_(
                    EventAttendee.event_id == event_id,
                    EventAttendee.agent_id == agent_id,
                )
            )
        )
        attendee = result.scalar_one_or_none()
        if not attendee:
            raise ValueError("Attendee not found")

        attendee.status = status
        attendee.comment = comment
        attendee.responded_at = datetime.utcnow()
        await self.db.commit()

    async def get_events(
        self,
        owner_id: UUID,
        start_date: datetime,
        end_date: datetime,
        calendar_id: UUID | None = None,
    ) -> list[CalendarEvent]:
        """Get events in a date range."""
        # Get owner's calendars
        calendar_query = select(CalendarConnection.id).where(
            CalendarConnection.owner_id == owner_id
        )
        if calendar_id:
            calendar_query = calendar_query.where(CalendarConnection.id == calendar_id)

        result = await self.db.execute(calendar_query)
        calendar_ids = [row[0] for row in result.fetchall()]

        if not calendar_ids:
            return []

        # Get events
        result = await self.db.execute(
            select(CalendarEvent)
            .where(
                and_(
                    CalendarEvent.calendar_id.in_(calendar_ids),
                    CalendarEvent.start_time >= start_date,
                    CalendarEvent.start_time <= end_date,
                    CalendarEvent.status != EventStatus.CANCELLED,
                )
            )
            .order_by(CalendarEvent.start_time.asc())
        )
        return list(result.scalars().all())

    async def get_availability(
        self,
        owner_id: UUID,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int = 30,
    ) -> list[dict]:
        """Get available time slots."""
        # Get busy times from events
        events = await self.get_events(owner_id, start_date, end_date)
        busy_times = [(e.start_time, e.end_time) for e in events]

        # Get explicit availability slots
        result = await self.db.execute(
            select(AvailabilitySlot)
            .where(
                and_(
                    AvailabilitySlot.owner_id == owner_id,
                    AvailabilitySlot.start_time >= start_date,
                    AvailabilitySlot.end_time <= end_date,
                    AvailabilitySlot.is_bookable == True,
                )
            )
            .order_by(AvailabilitySlot.start_time.asc())
        )
        slots = result.scalars().all()

        # Calculate available slots
        available = []
        duration = timedelta(minutes=duration_minutes)

        for slot in slots:
            current = slot.start_time
            while current + duration <= slot.end_time:
                # Check if overlaps with busy times
                is_free = True
                for busy_start, busy_end in busy_times:
                    if current < busy_end and current + duration > busy_start:
                        is_free = False
                        break

                if is_free:
                    available.append({
                        "start": current.isoformat(),
                        "end": (current + duration).isoformat(),
                    })

                current += timedelta(minutes=15)  # 15-minute increments

        return available

    async def create_scheduling_link(
        self,
        owner_id: UUID,
        slug: str,
        title: str,
        description: str | None = None,
        duration_options: list[int] | None = None,
        default_duration: int = 30,
        availability_schedule: dict | None = None,
        buffer_before: int = 0,
        buffer_after: int = 0,
        min_notice: int = 60,
    ) -> SchedulingLink:
        """Create a scheduling/booking link."""
        link = SchedulingLink(
            owner_id=owner_id,
            slug=slug,
            title=title,
            description=description,
            duration_options=duration_options or [30],
            default_duration=default_duration,
            availability_schedule=availability_schedule or {},
            buffer_before=buffer_before,
            buffer_after=buffer_after,
            min_notice=min_notice,
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        return link

    async def book_slot(
        self,
        link_id: UUID,
        start_time: datetime,
        duration_minutes: int,
        booker_email: str,
        booker_name: str | None = None,
        answers: dict | None = None,
    ) -> CalendarEvent:
        """Book a slot from a scheduling link."""
        result = await self.db.execute(
            select(SchedulingLink).where(SchedulingLink.id == link_id)
        )
        link = result.scalar_one_or_none()
        if not link:
            raise ValueError("Scheduling link not found")

        # Verify duration is allowed
        if duration_minutes not in link.duration_options:
            raise ValueError("Duration not allowed")

        # Verify minimum notice
        if start_time < datetime.utcnow() + timedelta(minutes=link.min_notice):
            raise ValueError("Not enough notice")

        # Get owner's primary calendar
        result = await self.db.execute(
            select(CalendarConnection).where(
                and_(
                    CalendarConnection.owner_id == link.owner_id,
                    CalendarConnection.is_primary == True,
                )
            )
        )
        calendar = result.scalar_one_or_none()

        # Create event
        end_time = start_time + timedelta(minutes=duration_minutes)
        event = await self.create_event(
            calendar_id=calendar.id if calendar else None,
            title=f"{link.title} with {booker_name or booker_email}",
            start_time=start_time,
            end_time=end_time,
            organizer_id=link.owner_id,
            attendee_emails=[booker_email],
        )

        return event

    async def list_calendars(self, owner_id: UUID) -> list[CalendarConnection]:
        """List calendars for an owner."""
        result = await self.db.execute(
            select(CalendarConnection)
            .where(CalendarConnection.owner_id == owner_id)
            .order_by(CalendarConnection.is_primary.desc(), CalendarConnection.created_at.desc())
        )
        return list(result.scalars().all())
