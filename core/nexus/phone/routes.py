"""Phone API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.phone.models import PhoneProvider, CallStatus, CallDirection
from nexus.phone.service import PhoneService

router = APIRouter(prefix="/phone", tags=["phone"])


class ProvisionNumberRequest(BaseModel):
    provider: str
    area_code: str | None = None
    country: str = "US"
    voice_enabled: bool = True
    sms_enabled: bool = True


class CreateVoiceAgentRequest(BaseModel):
    name: str
    system_prompt: str | None = None
    greeting_message: str | None = None
    voice_provider: str = "elevenlabs"
    voice_id: str | None = None
    nexus_agent_id: str | None = None
    available_tools: list[str] | None = None
    max_call_duration: int = Field(default=3600, ge=60, le=14400, description="Max call duration 1-240 minutes")
    silence_timeout: int = Field(default=10, ge=5, le=60, description="Silence timeout 5-60 seconds")


class MakeCallRequest(BaseModel):
    from_number_id: str
    to_number: str
    voice_agent_id: str | None = None
    metadata: dict | None = None


class TransferCallRequest(BaseModel):
    to_number: str | None = None
    to_agent_id: str | None = None


@router.post("/numbers/provision")
async def provision_number(
    request: ProvisionNumberRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Provision a new phone number."""
    service = PhoneService(db)

    try:
        number = await service.provision_number(
            provider=PhoneProvider(request.provider),
            owner_id=agent.id,
            area_code=request.area_code,
            country=request.country,
            voice_enabled=request.voice_enabled,
            sms_enabled=request.sms_enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": str(number.id),
        "number": number.number,
        "provider": number.provider.value,
        "voice_enabled": number.voice_enabled,
        "sms_enabled": number.sms_enabled,
    }


@router.get("/numbers")
async def list_numbers(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List phone numbers."""
    from sqlalchemy import select
    from nexus.phone.models import PhoneNumber

    result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.owner_id == agent.id)
    )
    numbers = result.scalars().all()

    return [
        {
            "id": str(n.id),
            "number": n.number,
            "friendly_name": n.friendly_name,
            "provider": n.provider.value,
            "voice_enabled": n.voice_enabled,
            "sms_enabled": n.sms_enabled,
            "is_active": n.is_active,
        }
        for n in numbers
    ]


@router.post("/voice-agents")
async def create_voice_agent(
    request: CreateVoiceAgentRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a voice agent configuration."""
    service = PhoneService(db)

    voice_agent = await service.create_voice_agent(
        name=request.name,
        owner_id=agent.id,
        system_prompt=request.system_prompt,
        greeting_message=request.greeting_message,
        voice_provider=request.voice_provider,
        voice_id=request.voice_id,
        nexus_agent_id=UUID(request.nexus_agent_id) if request.nexus_agent_id else None,
        available_tools=request.available_tools,
        max_call_duration=request.max_call_duration,
        silence_timeout=request.silence_timeout,
    )

    return {
        "id": str(voice_agent.id),
        "name": voice_agent.name,
        "voice_provider": voice_agent.voice_provider,
        "created_at": voice_agent.created_at.isoformat(),
    }


@router.get("/voice-agents")
async def list_voice_agents(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List voice agents."""
    from sqlalchemy import select
    from nexus.phone.models import VoiceAgent

    result = await db.execute(
        select(VoiceAgent).where(VoiceAgent.owner_id == agent.id)
    )
    agents = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "name": a.name,
            "voice_provider": a.voice_provider,
            "is_active": a.is_active,
        }
        for a in agents
    ]


@router.post("/calls")
async def make_call(
    request: MakeCallRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Make an outbound call."""
    from sqlalchemy import select
    from nexus.phone.models import PhoneNumber

    # SECURITY: Verify ownership of the from number
    result = await db.execute(
        select(PhoneNumber).where(PhoneNumber.id == UUID(request.from_number_id))
    )
    phone_number = result.scalar_one_or_none()
    if not phone_number:
        raise HTTPException(status_code=404, detail="Phone number not found")
    if phone_number.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to use this phone number")

    service = PhoneService(db)

    try:
        call = await service.make_call(
            from_number_id=UUID(request.from_number_id),
            to_number=request.to_number,
            voice_agent_id=UUID(request.voice_agent_id) if request.voice_agent_id else None,
            caller_agent_id=agent.id,
            metadata=request.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": str(call.id),
        "call_sid": call.call_sid,
        "status": call.status.value,
        "from_number": call.from_number,
        "to_number": call.to_number,
    }


@router.get("/calls")
async def list_calls(
    status: str | None = None,
    direction: str | None = None,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List calls."""
    service = PhoneService(db)

    # SECURITY: Pass owner_id to filter calls by agent's phone numbers
    calls = await service.list_calls(
        owner_id=agent.id,
        status=CallStatus(status) if status else None,
        direction=CallDirection(direction) if direction else None,
        limit=limit,
    )

    return [
        {
            "id": str(c.id),
            "call_sid": c.call_sid,
            "direction": c.direction.value,
            "status": c.status.value,
            "from_number": c.from_number,
            "to_number": c.to_number,
            "duration_seconds": c.duration_seconds,
            "queued_at": c.queued_at.isoformat(),
        }
        for c in calls
    ]


@router.get("/calls/{call_id}")
async def get_call(
    call_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a call by ID."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.phone.models import PhoneCall

    # SECURITY: Verify ownership via phone number
    result = await db.execute(
        select(PhoneCall)
        .options(selectinload(PhoneCall.phone_number))
        .where(PhoneCall.id == UUID(call_id))
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.phone_number and call.phone_number.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this call")

    return {
        "id": str(call.id),
        "call_sid": call.call_sid,
        "direction": call.direction.value,
        "status": call.status.value,
        "from_number": call.from_number,
        "to_number": call.to_number,
        "transcript": call.transcript,
        "summary": call.summary,
        "duration_seconds": call.duration_seconds,
        "recording_url": call.recording_url,
        "queued_at": call.queued_at.isoformat(),
        "answered_at": call.answered_at.isoformat() if call.answered_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
    }


@router.post("/calls/{call_id}/end")
async def end_call(
    call_id: str,
    generate_summary: bool = True,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """End a call."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.phone.models import PhoneCall

    # SECURITY: Verify ownership via phone number before ending call
    result = await db.execute(
        select(PhoneCall)
        .options(selectinload(PhoneCall.phone_number))
        .where(PhoneCall.id == UUID(call_id))
    )
    call_record = result.scalar_one_or_none()
    if not call_record:
        raise HTTPException(status_code=404, detail="Call not found")
    if call_record.phone_number and call_record.phone_number.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to end this call")

    service = PhoneService(db)

    try:
        call = await service.end_call(UUID(call_id), generate_summary)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "status": call.status.value,
        "duration_seconds": call.duration_seconds,
        "summary": call.summary,
    }


@router.post("/calls/{call_id}/transfer")
async def transfer_call(
    call_id: str,
    request: TransferCallRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Transfer a call."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.phone.models import PhoneCall

    # SECURITY: Verify ownership via phone number before transferring
    result = await db.execute(
        select(PhoneCall)
        .options(selectinload(PhoneCall.phone_number))
        .where(PhoneCall.id == UUID(call_id))
    )
    call_record = result.scalar_one_or_none()
    if not call_record:
        raise HTTPException(status_code=404, detail="Call not found")
    if call_record.phone_number and call_record.phone_number.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to transfer this call")

    service = PhoneService(db)

    try:
        call = await service.transfer_call(
            call_id=UUID(call_id),
            to_number=request.to_number,
            to_agent_id=UUID(request.to_agent_id) if request.to_agent_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "transferred"}


# Webhook endpoints for phone providers
@router.post("/webhook/voice/{number_id}")
async def voice_webhook(
    number_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle incoming voice webhook from phone provider."""
    service = PhoneService(db)
    form_data = await request.form()

    # Create call record for inbound call
    from nexus.phone.models import PhoneCall

    call = PhoneCall(
        call_sid=form_data.get("CallSid"),
        phone_number_id=UUID(number_id),
        direction=CallDirection.INBOUND,
        from_number=form_data.get("From"),
        to_number=form_data.get("To"),
        status=CallStatus.RINGING,
    )
    db.add(call)
    await db.commit()

    # Generate answer response
    response = await service.answer_call(call.id)

    from fastapi.responses import Response
    return Response(content=response["response"], media_type="application/xml")


@router.post("/webhook/gather/{call_id}")
async def gather_webhook(
    call_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle speech input from caller."""
    service = PhoneService(db)
    form_data = await request.form()

    speech_result = form_data.get("SpeechResult", "")

    response = await service.process_speech(UUID(call_id), speech_result)

    from fastapi.responses import Response
    return Response(content=response["response"], media_type="application/xml")


@router.post("/webhook/status/{call_id}")
async def status_webhook(
    call_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle call status updates."""
    form_data = await request.form()
    call_status = form_data.get("CallStatus")

    service = PhoneService(db)
    call = await service.get_call(UUID(call_id))

    if call:
        status_map = {
            "queued": CallStatus.QUEUED,
            "ringing": CallStatus.RINGING,
            "in-progress": CallStatus.IN_PROGRESS,
            "completed": CallStatus.COMPLETED,
            "busy": CallStatus.BUSY,
            "failed": CallStatus.FAILED,
            "no-answer": CallStatus.NO_ANSWER,
            "canceled": CallStatus.CANCELED,
        }
        call.status = status_map.get(call_status, call.status)

        if call_status == "completed":
            call.ended_at = datetime.utcnow()
            if form_data.get("CallDuration"):
                call.duration_seconds = int(form_data.get("CallDuration"))

        await db.commit()

    return {"status": "received"}
