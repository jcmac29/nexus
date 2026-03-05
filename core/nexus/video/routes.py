"""Video API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.video.service import VideoService
from nexus.video.models import VideoProvider, RoomStatus, ParticipantRole

router = APIRouter(prefix="/video", tags=["video"])


class CreateRoomRequest(BaseModel):
    name: str
    provider: str = "daily"
    description: str | None = None
    max_participants: int = 50
    is_private: bool = True
    password: str | None = None
    waiting_room_enabled: bool = False
    recording_enabled: bool = False
    transcription_enabled: bool = False
    ai_agent_id: str | None = None
    scheduled_start: str | None = None
    scheduled_end: str | None = None


class JoinRoomRequest(BaseModel):
    display_name: str | None = None
    role: str = "participant"


class UpdateMediaRequest(BaseModel):
    audio_enabled: bool | None = None
    video_enabled: bool | None = None
    screen_sharing: bool | None = None
    hand_raised: bool | None = None


class ScheduleMeetingRequest(BaseModel):
    title: str
    provider: str = "daily"
    scheduled_start: str
    scheduled_end: str
    description: str | None = None
    agenda: str | None = None
    invitees: list[dict] | None = None
    is_recurring: bool = False
    recurrence_rule: str | None = None
    room_settings: dict | None = None


@router.post("/rooms")
async def create_room(
    request: CreateRoomRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a video room."""
    service = VideoService(db)

    provider_map = {
        "twilio": VideoProvider.TWILIO,
        "daily": VideoProvider.DAILY,
        "zoom": VideoProvider.ZOOM,
        "vonage": VideoProvider.VONAGE,
        "agora": VideoProvider.AGORA,
        "livekit": VideoProvider.LIVEKIT,
        "jitsi": VideoProvider.JITSI,
    }

    room = await service.create_room(
        name=request.name,
        provider=provider_map.get(request.provider, VideoProvider.DAILY),
        owner_id=agent.id,
        description=request.description,
        max_participants=request.max_participants,
        is_private=request.is_private,
        password=request.password,
        waiting_room_enabled=request.waiting_room_enabled,
        recording_enabled=request.recording_enabled,
        transcription_enabled=request.transcription_enabled,
        ai_agent_id=UUID(request.ai_agent_id) if request.ai_agent_id else None,
        scheduled_start=datetime.fromisoformat(request.scheduled_start) if request.scheduled_start else None,
        scheduled_end=datetime.fromisoformat(request.scheduled_end) if request.scheduled_end else None,
    )

    return {
        "id": str(room.id),
        "room_id": room.room_id,
        "name": room.name,
        "provider": room.provider.value,
        "status": room.status.value,
        "join_url": room.join_url,
    }


@router.get("/rooms")
async def list_rooms(
    status: str | None = None,
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List video rooms."""
    service = VideoService(db)

    status_map = {
        "created": RoomStatus.CREATED,
        "active": RoomStatus.ACTIVE,
        "ended": RoomStatus.ENDED,
    }

    rooms = await service.list_rooms(
        owner_id=agent.id,
        status=status_map.get(status) if status else None,
        limit=limit,
    )

    return [
        {
            "id": str(r.id),
            "room_id": r.room_id,
            "name": r.name,
            "status": r.status.value,
            "participant_count": r.participant_count,
            "join_url": r.join_url,
            "created_at": r.created_at.isoformat(),
        }
        for r in rooms
    ]


@router.get("/rooms/{room_id}")
async def get_room(
    room_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a video room."""
    service = VideoService(db)
    room = await service.get_room(UUID(room_id))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # SECURITY: Only owner or participants can view room details
    # For now, require ownership for private rooms
    if room.is_private and room.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this room")

    return {
        "id": str(room.id),
        "room_id": room.room_id,
        "name": room.name,
        "description": room.description,
        "provider": room.provider.value,
        "status": room.status.value,
        "participant_count": room.participant_count,
        "max_participants": room.max_participants,
        "join_url": room.join_url,
        "recording_enabled": room.recording_enabled,
        "transcription_enabled": room.transcription_enabled,
        "created_at": room.created_at.isoformat(),
        "actual_start": room.actual_start.isoformat() if room.actual_start else None,
    }


@router.post("/rooms/{room_id}/join")
async def join_room(
    room_id: str,
    request: JoinRoomRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Join a video room."""
    service = VideoService(db)

    role_map = {
        "host": ParticipantRole.HOST,
        "co_host": ParticipantRole.CO_HOST,
        "presenter": ParticipantRole.PRESENTER,
        "participant": ParticipantRole.PARTICIPANT,
        "viewer": ParticipantRole.VIEWER,
    }

    participant = await service.join_room(
        room_id=UUID(room_id),
        agent_id=agent.id,
        agent_type="agent",
        display_name=request.display_name,
        role=role_map.get(request.role, ParticipantRole.PARTICIPANT),
    )

    return {
        "id": str(participant.id),
        "status": participant.status.value,
        "role": participant.role.value,
        "joined_at": participant.joined_at.isoformat() if participant.joined_at else None,
    }


@router.post("/rooms/{room_id}/leave")
async def leave_room(
    room_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Leave a video room."""
    service = VideoService(db)
    await service.leave_room(UUID(room_id), agent.id)
    return {"status": "left"}


@router.post("/rooms/{room_id}/end")
async def end_room(
    room_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """End a video room."""
    service = VideoService(db)

    # SECURITY: Verify ownership before ending room
    room = await service.get_room(UUID(room_id))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to end this room")

    await service.end_room(UUID(room_id))
    return {"status": "ended"}


@router.get("/rooms/{room_id}/participants")
async def get_participants(
    room_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get participants in a room."""
    service = VideoService(db)

    # SECURITY: Verify agent is owner or participant before listing participants
    room = await service.get_room(UUID(room_id))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    participants = await service.get_room_participants(UUID(room_id))
    is_participant = any(p.agent_id == agent.id for p in participants)

    if room.owner_id != agent.id and not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized to view participants")

    return [
        {
            "id": str(p.id),
            "agent_id": str(p.agent_id) if p.agent_id else None,
            "display_name": p.display_name,
            "status": p.status.value,
            "role": p.role.value,
            "audio_enabled": p.audio_enabled,
            "video_enabled": p.video_enabled,
            "screen_sharing": p.screen_sharing,
            "hand_raised": p.hand_raised,
            "joined_at": p.joined_at.isoformat() if p.joined_at else None,
        }
        for p in participants
    ]


@router.patch("/participants/{participant_id}/media")
async def update_media(
    participant_id: str,
    request: UpdateMediaRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update participant media state."""
    from sqlalchemy import select
    from nexus.video.models import VideoParticipant

    # SECURITY: Verify the participant belongs to the agent
    result = await db.execute(
        select(VideoParticipant).where(VideoParticipant.id == UUID(participant_id))
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    if participant.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this participant's media")

    service = VideoService(db)
    await service.update_participant_media(
        participant_id=UUID(participant_id),
        audio_enabled=request.audio_enabled,
        video_enabled=request.video_enabled,
        screen_sharing=request.screen_sharing,
        hand_raised=request.hand_raised,
    )
    return {"status": "updated"}


@router.post("/rooms/{room_id}/recordings/start")
async def start_recording(
    room_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Start recording a room."""
    service = VideoService(db)

    # SECURITY: Verify ownership before starting recording
    room = await service.get_room(UUID(room_id))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to record this room")

    recording = await service.start_recording(UUID(room_id))
    return {
        "id": str(recording.id),
        "status": recording.status,
        "started_at": recording.started_at.isoformat() if recording.started_at else None,
    }


@router.post("/recordings/{recording_id}/stop")
async def stop_recording(
    recording_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Stop a recording."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.video.models import VideoRecording

    # SECURITY: Verify ownership via room before stopping recording
    result = await db.execute(
        select(VideoRecording)
        .options(selectinload(VideoRecording.room))
        .where(VideoRecording.id == UUID(recording_id))
    )
    recording_record = result.scalar_one_or_none()
    if not recording_record:
        raise HTTPException(status_code=404, detail="Recording not found")
    if recording_record.room and recording_record.room.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to stop this recording")

    service = VideoService(db)
    recording = await service.stop_recording(UUID(recording_id))
    return {
        "id": str(recording.id),
        "status": recording.status,
        "duration_seconds": recording.duration_seconds,
    }


@router.post("/meetings")
async def schedule_meeting(
    request: ScheduleMeetingRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Schedule a video meeting."""
    service = VideoService(db)

    provider_map = {
        "twilio": VideoProvider.TWILIO,
        "daily": VideoProvider.DAILY,
        "zoom": VideoProvider.ZOOM,
        "livekit": VideoProvider.LIVEKIT,
    }

    meeting = await service.schedule_meeting(
        title=request.title,
        organizer_id=agent.id,
        provider=provider_map.get(request.provider, VideoProvider.DAILY),
        scheduled_start=datetime.fromisoformat(request.scheduled_start),
        scheduled_end=datetime.fromisoformat(request.scheduled_end),
        description=request.description,
        agenda=request.agenda,
        invitees=request.invitees,
        is_recurring=request.is_recurring,
        recurrence_rule=request.recurrence_rule,
        room_settings=request.room_settings,
    )

    return {
        "id": str(meeting.id),
        "title": meeting.title,
        "scheduled_start": meeting.scheduled_start.isoformat(),
        "scheduled_end": meeting.scheduled_end.isoformat(),
        "status": meeting.status,
    }


@router.get("/meetings")
async def list_meetings(
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List scheduled meetings."""
    service = VideoService(db)
    meetings = await service.list_scheduled_meetings(
        organizer_id=agent.id,
        from_date=datetime.fromisoformat(from_date) if from_date else None,
        to_date=datetime.fromisoformat(to_date) if to_date else None,
        limit=limit,
    )

    return [
        {
            "id": str(m.id),
            "title": m.title,
            "scheduled_start": m.scheduled_start.isoformat(),
            "scheduled_end": m.scheduled_end.isoformat(),
            "status": m.status,
            "invitees": m.invitees,
        }
        for m in meetings
    ]
