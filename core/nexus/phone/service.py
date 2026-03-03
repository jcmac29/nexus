"""Phone service for voice communication."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.phone.models import (
    PhoneNumber, VoiceAgent, PhoneCall, CallRecording,
    PhoneProvider, CallStatus, CallDirection
)


class PhoneService:
    """Service for managing phone/voice operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._providers: dict[PhoneProvider, Any] = {}

    def configure_provider(self, provider: PhoneProvider, config: dict):
        """Configure a phone provider."""
        if provider == PhoneProvider.TWILIO:
            from twilio.rest import Client
            self._providers[provider] = Client(
                config.get("account_sid"),
                config.get("auth_token")
            )
        elif provider == PhoneProvider.VONAGE:
            # Would configure Vonage client
            pass

    async def provision_number(
        self,
        provider: PhoneProvider,
        owner_id: UUID,
        area_code: str | None = None,
        country: str = "US",
        voice_enabled: bool = True,
        sms_enabled: bool = True,
    ) -> PhoneNumber:
        """Provision a new phone number."""
        client = self._providers.get(provider)
        if not client:
            raise ValueError(f"Provider {provider} not configured")

        # Search and purchase number (Twilio example)
        if provider == PhoneProvider.TWILIO:
            available = client.available_phone_numbers(country).local.list(
                area_code=area_code,
                voice_enabled=voice_enabled,
                sms_enabled=sms_enabled,
                limit=1
            )
            if not available:
                raise ValueError("No numbers available")

            purchased = client.incoming_phone_numbers.create(
                phone_number=available[0].phone_number
            )

            phone_number = PhoneNumber(
                number=purchased.phone_number,
                friendly_name=purchased.friendly_name,
                provider=provider,
                provider_sid=purchased.sid,
                voice_enabled=voice_enabled,
                sms_enabled=sms_enabled,
                owner_id=owner_id,
            )
        else:
            # Placeholder for other providers
            phone_number = PhoneNumber(
                number=f"+1555{area_code or '000'}0000",
                provider=provider,
                owner_id=owner_id,
            )

        self.db.add(phone_number)
        await self.db.commit()
        await self.db.refresh(phone_number)
        return phone_number

    async def create_voice_agent(
        self,
        name: str,
        owner_id: UUID,
        system_prompt: str | None = None,
        greeting_message: str | None = None,
        voice_provider: str = "elevenlabs",
        voice_id: str | None = None,
        nexus_agent_id: UUID | None = None,
        available_tools: list[str] | None = None,
        **kwargs,
    ) -> VoiceAgent:
        """Create a voice agent configuration."""
        agent = VoiceAgent(
            name=name,
            owner_id=owner_id,
            system_prompt=system_prompt,
            greeting_message=greeting_message,
            voice_provider=voice_provider,
            voice_id=voice_id,
            nexus_agent_id=nexus_agent_id,
            available_tools=available_tools or [],
            **kwargs,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def make_call(
        self,
        from_number_id: UUID,
        to_number: str,
        voice_agent_id: UUID | None = None,
        caller_agent_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> PhoneCall:
        """Initiate an outbound call."""
        phone_number = await self.get_phone_number(from_number_id)
        if not phone_number:
            raise ValueError("Phone number not found")

        client = self._providers.get(phone_number.provider)
        if not client:
            raise ValueError(f"Provider {phone_number.provider} not configured")

        # Create call record
        call = PhoneCall(
            phone_number_id=from_number_id,
            voice_agent_id=voice_agent_id,
            direction=CallDirection.OUTBOUND,
            from_number=phone_number.number,
            to_number=to_number,
            caller_agent_id=caller_agent_id,
            caller_type="agent" if caller_agent_id else "system",
            metadata=metadata or {},
        )
        self.db.add(call)
        await self.db.flush()

        # Make call via provider
        if phone_number.provider == PhoneProvider.TWILIO:
            try:
                provider_call = client.calls.create(
                    to=to_number,
                    from_=phone_number.number,
                    url=phone_number.voice_webhook_url or "https://your-nexus-instance/api/v1/phone/webhook/voice",
                    status_callback=f"https://your-nexus-instance/api/v1/phone/webhook/status/{call.id}",
                )
                call.call_sid = provider_call.sid
                call.status = CallStatus.QUEUED
            except Exception as e:
                call.status = CallStatus.FAILED
                call.error_message = str(e)

        await self.db.commit()
        await self.db.refresh(call)
        return call

    async def answer_call(
        self,
        call_id: UUID,
        voice_agent_id: UUID | None = None,
    ) -> dict:
        """Generate response for answering a call (webhook handler)."""
        call = await self.get_call(call_id)
        if not call:
            raise ValueError("Call not found")

        voice_agent = None
        if voice_agent_id:
            voice_agent = await self.get_voice_agent(voice_agent_id)
        elif call.voice_agent_id:
            voice_agent = await self.get_voice_agent(call.voice_agent_id)

        # Update call status
        call.status = CallStatus.IN_PROGRESS
        call.answered_at = datetime.utcnow()
        await self.db.commit()

        # Generate TwiML or similar response
        greeting = voice_agent.greeting_message if voice_agent else "Hello, how can I help you?"

        return {
            "response_type": "twiml",
            "response": f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">{greeting}</Say>
    <Gather input="speech" timeout="5" speechTimeout="auto" action="/api/v1/phone/webhook/gather/{call.id}">
        <Say>Please speak after the tone.</Say>
    </Gather>
</Response>"""
        }

    async def process_speech(
        self,
        call_id: UUID,
        speech_result: str,
    ) -> dict:
        """Process speech input and generate AI response."""
        call = await self.get_call(call_id)
        if not call:
            raise ValueError("Call not found")

        voice_agent = await self.get_voice_agent(call.voice_agent_id) if call.voice_agent_id else None

        # Add to transcript
        transcript = list(call.transcript or [])
        transcript.append({
            "speaker": "caller",
            "text": speech_result,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Generate AI response (would integrate with LLM)
        ai_response = await self._generate_ai_response(voice_agent, transcript, speech_result)

        transcript.append({
            "speaker": "agent",
            "text": ai_response,
            "timestamp": datetime.utcnow().isoformat(),
        })

        call.transcript = transcript
        await self.db.commit()

        return {
            "response_type": "twiml",
            "response": f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">{ai_response}</Say>
    <Gather input="speech" timeout="5" speechTimeout="auto" action="/api/v1/phone/webhook/gather/{call.id}">
    </Gather>
</Response>"""
        }

    async def _generate_ai_response(
        self,
        voice_agent: VoiceAgent | None,
        transcript: list,
        latest_input: str,
    ) -> str:
        """Generate AI response for voice conversation."""
        # This would integrate with your LLM provider
        # For now, return a placeholder
        system_prompt = voice_agent.system_prompt if voice_agent else "You are a helpful assistant."

        # Would call OpenAI, Anthropic, etc.
        return f"I heard you say: {latest_input}. How can I help you further?"

    async def end_call(
        self,
        call_id: UUID,
        generate_summary: bool = True,
    ) -> PhoneCall:
        """End a call and optionally generate summary."""
        call = await self.get_call(call_id)
        if not call:
            raise ValueError("Call not found")

        call.status = CallStatus.COMPLETED
        call.ended_at = datetime.utcnow()

        if call.answered_at:
            call.duration_seconds = int((call.ended_at - call.answered_at).total_seconds())

        if generate_summary and call.transcript:
            # Would generate summary using LLM
            call.summary = f"Call lasted {call.duration_seconds} seconds with {len(call.transcript)} exchanges."

        await self.db.commit()
        return call

    async def get_phone_number(self, number_id: UUID) -> PhoneNumber | None:
        """Get a phone number by ID."""
        result = await self.db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id))
        return result.scalar_one_or_none()

    async def get_voice_agent(self, agent_id: UUID) -> VoiceAgent | None:
        """Get a voice agent by ID."""
        result = await self.db.execute(select(VoiceAgent).where(VoiceAgent.id == agent_id))
        return result.scalar_one_or_none()

    async def get_call(self, call_id: UUID) -> PhoneCall | None:
        """Get a call by ID."""
        result = await self.db.execute(select(PhoneCall).where(PhoneCall.id == call_id))
        return result.scalar_one_or_none()

    async def list_calls(
        self,
        phone_number_id: UUID | None = None,
        status: CallStatus | None = None,
        direction: CallDirection | None = None,
        limit: int = 100,
    ) -> list[PhoneCall]:
        """List calls with filters."""
        query = select(PhoneCall).order_by(PhoneCall.queued_at.desc()).limit(limit)

        if phone_number_id:
            query = query.where(PhoneCall.phone_number_id == phone_number_id)
        if status:
            query = query.where(PhoneCall.status == status)
        if direction:
            query = query.where(PhoneCall.direction == direction)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def transfer_call(
        self,
        call_id: UUID,
        to_number: str | None = None,
        to_agent_id: UUID | None = None,
    ) -> PhoneCall:
        """Transfer a call to another number or agent."""
        call = await self.get_call(call_id)
        if not call:
            raise ValueError("Call not found")

        # Would implement call transfer via provider
        # This is a placeholder

        return call
