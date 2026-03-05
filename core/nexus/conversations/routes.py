"""Conversation API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.conversations.models import ParticipantType, ConversationStatus
from nexus.conversations.service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    context: dict | None = None
    participant_ids: list[str] | None = None
    team_id: str | None = None


class SendMessageRequest(BaseModel):
    content: str
    content_type: str = "text"
    reply_to_id: str | None = None
    metadata: dict | None = None
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: dict | None = None


class AddParticipantRequest(BaseModel):
    participant_id: str
    participant_type: str = "agent"
    role: str = "participant"
    display_name: str | None = None


class UpdateStateRequest(BaseModel):
    state: dict


class AddReactionRequest(BaseModel):
    emoji: str


@router.post("")
async def create_conversation(
    request: CreateConversationRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation."""
    service = ConversationService(db)

    participant_ids = None
    if request.participant_ids:
        participant_ids = [
            (UUID(pid), ParticipantType.AGENT)
            for pid in request.participant_ids
        ]

    conversation = await service.create_conversation(
        creator_id=agent.id,
        creator_type=ParticipantType.AGENT,
        title=request.title,
        description=request.description,
        context=request.context,
        participant_ids=participant_ids,
        team_id=UUID(request.team_id) if request.team_id else None,
    )

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "status": conversation.status.value,
        "created_at": conversation.created_at.isoformat(),
        "participants": [
            {
                "id": str(p.participant_id),
                "type": p.participant_type.value,
                "role": p.role,
            }
            for p in conversation.participants
        ],
    }


@router.get("")
async def list_conversations(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List conversations for the current agent."""
    service = ConversationService(db)

    conv_status = ConversationStatus(status) if status else None
    conversations = await service.list_conversations(
        participant_id=agent.id,
        status=conv_status,
        limit=limit,
        offset=offset,
    )

    return [
        {
            "id": str(c.id),
            "title": c.title,
            "status": c.status.value,
            "message_count": c.message_count,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            "participant_count": len(c.participants),
        }
        for c in conversations
    ]


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    include_messages: bool = False,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation by ID."""
    service = ConversationService(db)
    conversation = await service.get_conversation(
        UUID(conversation_id),
        include_messages=include_messages,
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if agent is participant
    is_participant = any(
        p.participant_id == agent.id for p in conversation.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not a participant")

    result = {
        "id": str(conversation.id),
        "title": conversation.title,
        "description": conversation.description,
        "status": conversation.status.value,
        "context": conversation.context,
        "shared_state": conversation.shared_state,
        "message_count": conversation.message_count,
        "created_at": conversation.created_at.isoformat(),
        "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        "participants": [
            {
                "id": str(p.participant_id),
                "type": p.participant_type.value,
                "role": p.role,
                "display_name": p.display_name,
                "is_active": p.is_active,
            }
            for p in conversation.participants
        ],
    }

    if include_messages:
        result["messages"] = [
            {
                "id": str(m.id),
                "sender_id": str(m.sender_id),
                "sender_type": m.sender_type.value,
                "sender_name": m.sender_name,
                "content": m.content,
                "content_type": m.content_type,
                "created_at": m.created_at.isoformat(),
                "reactions": m.reactions,
                "is_edited": m.is_edited,
            }
            for m in conversation.messages
        ]

    return result


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to a conversation."""
    service = ConversationService(db)

    # Verify conversation exists and agent is participant
    conversation = await service.get_conversation(UUID(conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_participant = any(
        p.participant_id == agent.id and p.is_active
        for p in conversation.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not a participant")

    message = await service.send_message(
        conversation_id=UUID(conversation_id),
        sender_id=agent.id,
        content=request.content,
        sender_type=ParticipantType.AGENT,
        sender_name=agent.name,
        content_type=request.content_type,
        reply_to_id=UUID(request.reply_to_id) if request.reply_to_id else None,
        metadata=request.metadata,
        tool_name=request.tool_name,
        tool_input=request.tool_input,
        tool_output=request.tool_output,
    )

    # Broadcast via WebSocket if available
    try:
        from nexus.websockets.manager import manager

        for p in conversation.participants:
            if p.participant_id != agent.id and p.is_active:
                await manager.send_to_agent(str(p.participant_id), {
                    "type": "conversation_message",
                    "conversation_id": conversation_id,
                    "message": {
                        "id": str(message.id),
                        "sender_id": str(message.sender_id),
                        "sender_name": message.sender_name,
                        "content": message.content,
                        "content_type": message.content_type,
                        "created_at": message.created_at.isoformat(),
                    },
                })
    except Exception:
        pass  # WebSocket broadcast is best-effort

    return {
        "id": str(message.id),
        "conversation_id": conversation_id,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=100, le=500),
    before: datetime | None = None,
    after: datetime | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get messages from a conversation."""
    service = ConversationService(db)

    # SECURITY: Verify agent is a participant before viewing messages
    conversation = await service.get_conversation(UUID(conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_participant = any(
        p.participant_id == agent.id for p in conversation.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not a participant")

    messages = await service.get_messages(
        conversation_id=UUID(conversation_id),
        limit=limit,
        before=before,
        after=after,
    )

    return [
        {
            "id": str(m.id),
            "sender_id": str(m.sender_id),
            "sender_type": m.sender_type.value,
            "sender_name": m.sender_name,
            "content": m.content,
            "content_type": m.content_type,
            "reply_to_id": str(m.reply_to_id) if m.reply_to_id else None,
            "tool_name": m.tool_name,
            "tool_input": m.tool_input,
            "tool_output": m.tool_output,
            "reactions": m.reactions,
            "is_edited": m.is_edited,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.post("/{conversation_id}/participants")
async def add_participant(
    conversation_id: str,
    request: AddParticipantRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add a participant to a conversation."""
    service = ConversationService(db)

    # SECURITY: Verify agent is a participant before adding others
    conversation = await service.get_conversation(UUID(conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_participant = any(
        p.participant_id == agent.id and p.is_active for p in conversation.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized to add participants")

    participant = await service.add_participant(
        conversation_id=UUID(conversation_id),
        participant_id=UUID(request.participant_id),
        participant_type=ParticipantType(request.participant_type),
        role=request.role,
        display_name=request.display_name,
    )

    return {
        "id": str(participant.id),
        "participant_id": str(participant.participant_id),
        "role": participant.role,
        "joined_at": participant.joined_at.isoformat(),
    }


@router.delete("/{conversation_id}/participants/{participant_id}")
async def remove_participant(
    conversation_id: str,
    participant_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Remove a participant from a conversation."""
    service = ConversationService(db)

    # SECURITY: Verify agent is a participant before removing others
    conversation = await service.get_conversation(UUID(conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_participant = any(
        p.participant_id == agent.id and p.is_active for p in conversation.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized to remove participants")

    await service.remove_participant(UUID(conversation_id), UUID(participant_id))
    return {"status": "removed"}


@router.put("/{conversation_id}/state")
async def update_shared_state(
    conversation_id: str,
    request: UpdateStateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update the shared state of a conversation."""
    service = ConversationService(db)

    # SECURITY: Verify agent is a participant before updating state
    conv = await service.get_conversation(UUID(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_participant = any(
        p.participant_id == agent.id and p.is_active for p in conv.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized to update state")

    conversation = await service.update_shared_state(
        UUID(conversation_id),
        request.state,
    )

    return {"shared_state": conversation.shared_state}


@router.post("/{conversation_id}/messages/{message_id}/reactions")
async def add_reaction(
    conversation_id: str,
    message_id: str,
    request: AddReactionRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add a reaction to a message."""
    service = ConversationService(db)

    # SECURITY: Verify agent is a participant before adding reactions
    conversation = await service.get_conversation(UUID(conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_participant = any(
        p.participant_id == agent.id for p in conversation.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized to add reactions")

    await service.add_reaction(UUID(message_id), agent.id, request.emoji)
    return {"status": "added"}


@router.post("/{conversation_id}/read")
async def mark_read(
    conversation_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Mark a conversation as read."""
    service = ConversationService(db)
    await service.mark_read(UUID(conversation_id), agent.id)
    return {"status": "read"}


@router.post("/{conversation_id}/close")
async def close_conversation(
    conversation_id: str,
    summary: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Close a conversation."""
    service = ConversationService(db)

    # SECURITY: Verify agent is a participant before closing
    conversation = await service.get_conversation(UUID(conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_participant = any(
        p.participant_id == agent.id and p.is_active for p in conversation.participants
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized to close this conversation")

    await service.close_conversation(UUID(conversation_id), summary)
    return {"status": "closed"}
