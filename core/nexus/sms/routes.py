"""SMS API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.sms.service import SMSService

router = APIRouter(prefix="/sms", tags=["sms"])


class SendSMSRequest(BaseModel):
    from_number: str
    to_number: str
    body: str
    media_urls: list[str] | None = None


class ConfigureConversationRequest(BaseModel):
    auto_reply_enabled: bool = False
    ai_agent_id: str | None = None
    system_prompt: str | None = None


@router.post("/send")
async def send_sms(
    request: SendSMSRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send an SMS message."""
    service = SMSService(db)

    message = await service.send_sms(
        from_number=request.from_number,
        to_number=request.to_number,
        body=request.body,
        sender_id=agent.id,
        sender_type="agent",
        media_urls=request.media_urls,
    )

    return {
        "id": str(message.id),
        "message_sid": message.message_sid,
        "status": message.status.value,
        "from_number": message.from_number,
        "to_number": message.to_number,
    }


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List SMS conversations."""
    service = SMSService(db)
    conversations = await service.list_conversations(agent.id, limit)

    return [
        {
            "id": str(c.id),
            "nexus_number": c.nexus_number,
            "external_number": c.external_number,
            "message_count": c.message_count,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            "auto_reply_enabled": c.auto_reply_enabled,
        }
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get messages from a conversation."""
    service = SMSService(db)
    messages = await service.get_messages(UUID(conversation_id), limit)

    return [
        {
            "id": str(m.id),
            "direction": m.direction.value,
            "status": m.status.value,
            "from_number": m.from_number,
            "to_number": m.to_number,
            "body": m.body,
            "media_urls": m.media_urls,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.put("/conversations/{conversation_id}/configure")
async def configure_conversation(
    conversation_id: str,
    request: ConfigureConversationRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Configure auto-reply for a conversation."""
    from sqlalchemy import select
    from nexus.sms.models import SMSConversation

    result = await db.execute(
        select(SMSConversation).where(SMSConversation.id == UUID(conversation_id))
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.auto_reply_enabled = request.auto_reply_enabled
    if request.ai_agent_id:
        conversation.ai_agent_id = UUID(request.ai_agent_id)
    if request.system_prompt:
        conversation.system_prompt = request.system_prompt

    await db.commit()

    return {"status": "configured"}


@router.post("/webhook/inbound")
async def inbound_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle inbound SMS webhook."""
    form_data = await request.form()

    service = SMSService(db)
    message = await service.receive_sms(
        from_number=form_data.get("From"),
        to_number=form_data.get("To"),
        body=form_data.get("Body", ""),
        message_sid=form_data.get("MessageSid"),
        media_urls=[form_data.get(f"MediaUrl{i}") for i in range(int(form_data.get("NumMedia", 0)))],
    )

    return {"status": "received", "message_id": str(message.id)}


@router.post("/webhook/status")
async def status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle SMS status webhook."""
    form_data = await request.form()

    from sqlalchemy import select
    from nexus.sms.models import SMSMessage, SMSStatus

    message_sid = form_data.get("MessageSid")
    status = form_data.get("MessageStatus")

    result = await db.execute(
        select(SMSMessage).where(SMSMessage.message_sid == message_sid)
    )
    message = result.scalar_one_or_none()

    if message:
        status_map = {
            "queued": SMSStatus.QUEUED,
            "sending": SMSStatus.SENDING,
            "sent": SMSStatus.SENT,
            "delivered": SMSStatus.DELIVERED,
            "failed": SMSStatus.FAILED,
        }
        message.status = status_map.get(status, message.status)

        if status == "delivered":
            from datetime import datetime
            message.delivered_at = datetime.utcnow()
        elif status == "failed":
            message.error_code = form_data.get("ErrorCode")
            message.error_message = form_data.get("ErrorMessage")

        await db.commit()

    return {"status": "received"}
