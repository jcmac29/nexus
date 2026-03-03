"""Video service for video conferencing."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
import uuid as uuid_module

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.video.models import (
    VideoRoom, VideoParticipant, VideoRecording, ScheduledMeeting,
    VideoProvider, RoomStatus, ParticipantStatus, ParticipantRole
)


class VideoService:
    """Service for video conferencing operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._providers = {}

    def configure_daily(self, api_key: str):
        """Configure Daily.co for video."""
        self._providers["daily"] = {"api_key": api_key}

    def configure_twilio(self, account_sid: str, auth_token: str):
        """Configure Twilio for video."""
        from twilio.rest import Client
        self._providers["twilio"] = Client(account_sid, auth_token)

    def configure_livekit(self, api_key: str, api_secret: str, host: str):
        """Configure LiveKit for video."""
        self._providers["livekit"] = {
            "api_key": api_key,
            "api_secret": api_secret,
            "host": host,
        }

    async def create_room(
        self,
        name: str,
        provider: VideoProvider,
        owner_id: UUID,
        owner_type: str = "agent",
        description: str | None = None,
        max_participants: int = 50,
        is_private: bool = True,
        password: str | None = None,
        waiting_room_enabled: bool = False,
        recording_enabled: bool = False,
        transcription_enabled: bool = False,
        ai_agent_id: UUID | None = None,
        scheduled_start: datetime | None = None,
        scheduled_end: datetime | None = None,
    ) -> VideoRoom:
        """Create a video room."""
        room_id = str(uuid_module.uuid4())
        join_url = None
        host_url = None

        # Create room with provider
        if provider == VideoProvider.DAILY and "daily" in self._providers:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.daily.co/v1/rooms",
                    headers={"Authorization": f"Bearer {self._providers['daily']['api_key']}"},
                    json={
                        "name": room_id,
                        "privacy": "private" if is_private else "public",
                        "properties": {
                            "max_participants": max_participants,
                            "enable_recording": "cloud" if recording_enabled else None,
                        },
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    room_id = data.get("name", room_id)
                    join_url = data.get("url")

        elif provider == VideoProvider.TWILIO and "twilio" in self._providers:
            try:
                room_resource = self._providers["twilio"].video.rooms.create(
                    unique_name=room_id,
                    type="group",
                    max_participants=max_participants,
                    record_participants_on_connect=recording_enabled,
                )
                room_id = room_resource.sid
            except Exception:
                pass

        elif provider == VideoProvider.LIVEKIT and "livekit" in self._providers:
            # LiveKit room creation
            join_url = f"{self._providers['livekit']['host']}/room/{room_id}"

        # Create room record
        room = VideoRoom(
            room_id=room_id,
            name=name,
            description=description,
            provider=provider,
            owner_id=owner_id,
            owner_type=owner_type,
            max_participants=max_participants,
            is_private=is_private,
            password=password,
            waiting_room_enabled=waiting_room_enabled,
            recording_enabled=recording_enabled,
            transcription_enabled=transcription_enabled,
            ai_agent_id=ai_agent_id,
            status=RoomStatus.CREATED,
            join_url=join_url,
            host_url=host_url,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
        )
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)
        return room

    async def join_room(
        self,
        room_id: UUID,
        agent_id: UUID,
        agent_type: str = "agent",
        display_name: str | None = None,
        role: ParticipantRole = ParticipantRole.PARTICIPANT,
    ) -> VideoParticipant:
        """Join a video room."""
        result = await self.db.execute(
            select(VideoRoom).where(VideoRoom.id == room_id)
        )
        room = result.scalar_one_or_none()
        if not room:
            raise ValueError("Room not found")

        # Check if already in room
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room_id,
                    VideoParticipant.agent_id == agent_id,
                    VideoParticipant.status == ParticipantStatus.CONNECTED,
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        participant = VideoParticipant(
            room_id=room_id,
            agent_id=agent_id,
            agent_type=agent_type,
            display_name=display_name,
            status=ParticipantStatus.CONNECTED,
            role=role,
            joined_at=datetime.utcnow(),
        )
        self.db.add(participant)

        # Update room
        room.participant_count += 1
        if room.status == RoomStatus.CREATED:
            room.status = RoomStatus.ACTIVE
            room.actual_start = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(participant)
        return participant

    async def leave_room(
        self,
        room_id: UUID,
        agent_id: UUID,
    ):
        """Leave a video room."""
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room_id,
                    VideoParticipant.agent_id == agent_id,
                    VideoParticipant.status == ParticipantStatus.CONNECTED,
                )
            )
        )
        participant = result.scalar_one_or_none()
        if not participant:
            return

        participant.status = ParticipantStatus.DISCONNECTED
        participant.left_at = datetime.utcnow()
        if participant.joined_at:
            participant.duration_seconds = int(
                (participant.left_at - participant.joined_at).total_seconds()
            )

        # Update room
        result = await self.db.execute(
            select(VideoRoom).where(VideoRoom.id == room_id)
        )
        room = result.scalar_one_or_none()
        if room:
            room.participant_count = max(0, room.participant_count - 1)

        await self.db.commit()

    async def end_room(self, room_id: UUID):
        """End a video room."""
        result = await self.db.execute(
            select(VideoRoom).where(VideoRoom.id == room_id)
        )
        room = result.scalar_one_or_none()
        if not room:
            return

        room.status = RoomStatus.ENDED
        room.actual_end = datetime.utcnow()
        if room.actual_start:
            room.duration_seconds = int(
                (room.actual_end - room.actual_start).total_seconds()
            )

        # Disconnect all participants
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room_id,
                    VideoParticipant.status == ParticipantStatus.CONNECTED,
                )
            )
        )
        participants = result.scalars().all()
        for p in participants:
            p.status = ParticipantStatus.DISCONNECTED
            p.left_at = datetime.utcnow()

        await self.db.commit()

    async def update_participant_media(
        self,
        participant_id: UUID,
        audio_enabled: bool | None = None,
        video_enabled: bool | None = None,
        screen_sharing: bool | None = None,
        hand_raised: bool | None = None,
    ):
        """Update participant media state."""
        result = await self.db.execute(
            select(VideoParticipant).where(VideoParticipant.id == participant_id)
        )
        participant = result.scalar_one_or_none()
        if not participant:
            return

        if audio_enabled is not None:
            participant.audio_enabled = audio_enabled
        if video_enabled is not None:
            participant.video_enabled = video_enabled
        if screen_sharing is not None:
            participant.screen_sharing = screen_sharing
        if hand_raised is not None:
            participant.hand_raised = hand_raised

        await self.db.commit()

    async def start_recording(self, room_id: UUID) -> VideoRecording:
        """Start recording a room."""
        result = await self.db.execute(
            select(VideoRoom).where(VideoRoom.id == room_id)
        )
        room = result.scalar_one_or_none()
        if not room:
            raise ValueError("Room not found")

        recording = VideoRecording(
            room_id=room_id,
            status="recording",
            started_at=datetime.utcnow(),
        )
        self.db.add(recording)
        await self.db.commit()
        await self.db.refresh(recording)
        return recording

    async def stop_recording(self, recording_id: UUID) -> VideoRecording:
        """Stop a recording."""
        result = await self.db.execute(
            select(VideoRecording).where(VideoRecording.id == recording_id)
        )
        recording = result.scalar_one_or_none()
        if not recording:
            raise ValueError("Recording not found")

        recording.status = "processing"
        recording.ended_at = datetime.utcnow()
        if recording.started_at:
            recording.duration_seconds = int(
                (recording.ended_at - recording.started_at).total_seconds()
            )

        await self.db.commit()
        await self.db.refresh(recording)
        return recording

    async def get_room(self, room_id: UUID) -> VideoRoom | None:
        """Get a video room."""
        result = await self.db.execute(
            select(VideoRoom).where(VideoRoom.id == room_id)
        )
        return result.scalar_one_or_none()

    async def list_rooms(
        self,
        owner_id: UUID,
        status: RoomStatus | None = None,
        limit: int = 50,
    ) -> list[VideoRoom]:
        """List video rooms."""
        query = select(VideoRoom).where(VideoRoom.owner_id == owner_id)
        if status:
            query = query.where(VideoRoom.status == status)
        query = query.order_by(VideoRoom.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_room_participants(self, room_id: UUID) -> list[VideoParticipant]:
        """Get participants in a room."""
        result = await self.db.execute(
            select(VideoParticipant)
            .where(VideoParticipant.room_id == room_id)
            .order_by(VideoParticipant.joined_at.asc())
        )
        return list(result.scalars().all())

    async def schedule_meeting(
        self,
        title: str,
        organizer_id: UUID,
        provider: VideoProvider,
        scheduled_start: datetime,
        scheduled_end: datetime,
        description: str | None = None,
        agenda: str | None = None,
        invitees: list[dict] | None = None,
        is_recurring: bool = False,
        recurrence_rule: str | None = None,
        room_settings: dict | None = None,
    ) -> ScheduledMeeting:
        """Schedule a video meeting."""
        meeting = ScheduledMeeting(
            title=title,
            description=description,
            agenda=agenda,
            organizer_id=organizer_id,
            provider=provider,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            invitees=invitees or [],
            is_recurring=is_recurring,
            recurrence_rule=recurrence_rule,
            room_settings=room_settings or {},
        )
        self.db.add(meeting)
        await self.db.commit()
        await self.db.refresh(meeting)
        return meeting

    async def list_scheduled_meetings(
        self,
        organizer_id: UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
    ) -> list[ScheduledMeeting]:
        """List scheduled meetings."""
        query = select(ScheduledMeeting).where(
            ScheduledMeeting.organizer_id == organizer_id
        )
        if from_date:
            query = query.where(ScheduledMeeting.scheduled_start >= from_date)
        if to_date:
            query = query.where(ScheduledMeeting.scheduled_start <= to_date)

        query = query.order_by(ScheduledMeeting.scheduled_start.asc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())
