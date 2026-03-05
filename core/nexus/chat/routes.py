"""Chat API routes for external chat platform integrations."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.chat.service import ChatService
from nexus.chat.models import ChatPlatform

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateConnectionRequest(BaseModel):
    platform: str
    access_token: str | None = None
    bot_token: str | None = None
    webhook_url: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    ai_agent_id: str | None = None
    auto_reply_enabled: bool = False
    system_prompt: str | None = None


class SendMessageRequest(BaseModel):
    content: str
    thread_id: str | None = None
    attachments: list[dict] | None = None


class ConfigureChannelRequest(BaseModel):
    ai_agent_id: str | None = None
    auto_reply_enabled: bool = False
    mention_only: bool = True
    is_synced: bool = True


class CreateCommandRequest(BaseModel):
    name: str
    description: str | None = None
    handler_type: str = "agent"
    handler_id: str | None = None
    options: list[dict] | None = None


@router.post("/connections")
async def create_connection(
    request: CreateConnectionRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a connection to a chat platform."""
    service = ChatService(db)

    platform_map = {
        "slack": ChatPlatform.SLACK,
        "discord": ChatPlatform.DISCORD,
        "telegram": ChatPlatform.TELEGRAM,
        "whatsapp": ChatPlatform.WHATSAPP,
        "teams": ChatPlatform.TEAMS,
        "mattermost": ChatPlatform.MATTERMOST,
    }

    connection = await service.create_connection(
        owner_id=agent.id,
        platform=platform_map.get(request.platform, ChatPlatform.SLACK),
        access_token=request.access_token,
        bot_token=request.bot_token,
        webhook_url=request.webhook_url,
        workspace_id=request.workspace_id,
        workspace_name=request.workspace_name,
        ai_agent_id=UUID(request.ai_agent_id) if request.ai_agent_id else None,
        auto_reply_enabled=request.auto_reply_enabled,
        system_prompt=request.system_prompt,
    )

    return {
        "id": str(connection.id),
        "platform": connection.platform.value,
        "status": connection.status.value,
        "workspace_name": connection.workspace_name,
    }


@router.get("/connections")
async def list_connections(
    platform: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List chat connections."""
    service = ChatService(db)

    platform_map = {
        "slack": ChatPlatform.SLACK,
        "discord": ChatPlatform.DISCORD,
        "telegram": ChatPlatform.TELEGRAM,
        "whatsapp": ChatPlatform.WHATSAPP,
    }

    connections = await service.list_connections(
        owner_id=agent.id,
        platform=platform_map.get(platform) if platform else None,
    )

    return [
        {
            "id": str(c.id),
            "platform": c.platform.value,
            "status": c.status.value,
            "workspace_name": c.workspace_name,
            "auto_reply_enabled": c.auto_reply_enabled,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
        }
        for c in connections
    ]


@router.post("/connections/{connection_id}/sync")
async def sync_channels(
    connection_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Sync channels from a platform."""
    from sqlalchemy import select
    from nexus.chat.models import ChatConnection

    # SECURITY: Verify ownership before syncing
    result = await db.execute(
        select(ChatConnection).where(ChatConnection.id == UUID(connection_id))
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    if connection.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to sync this connection")

    service = ChatService(db)
    channels = await service.sync_channels(UUID(connection_id))

    return [
        {
            "id": str(ch.id),
            "channel_id": ch.channel_id,
            "channel_name": ch.channel_name,
            "channel_type": ch.channel_type,
            "member_count": ch.member_count,
            "is_member": ch.is_member,
        }
        for ch in channels
    ]


@router.get("/connections/{connection_id}/channels")
async def list_channels(
    connection_id: str,
    synced_only: bool = False,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List channels for a connection."""
    from sqlalchemy import select
    from nexus.chat.models import ChatConnection

    # SECURITY: Verify ownership before listing channels
    result = await db.execute(
        select(ChatConnection).where(ChatConnection.id == UUID(connection_id))
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    if connection.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this connection")

    service = ChatService(db)
    channels = await service.list_channels(UUID(connection_id), synced_only)

    return [
        {
            "id": str(ch.id),
            "channel_id": ch.channel_id,
            "channel_name": ch.channel_name,
            "channel_type": ch.channel_type,
            "is_synced": ch.is_synced,
            "auto_reply_enabled": ch.auto_reply_enabled,
            "last_message_at": ch.last_message_at.isoformat() if ch.last_message_at else None,
        }
        for ch in channels
    ]


@router.put("/channels/{channel_id}/configure")
async def configure_channel(
    channel_id: str,
    request: ConfigureChannelRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Configure a channel."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.chat.models import ChatChannel

    result = await db.execute(
        select(ChatChannel)
        .options(selectinload(ChatChannel.connection))
        .where(ChatChannel.id == UUID(channel_id))
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # SECURITY: Verify ownership via connection
    if channel.connection.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to configure this channel")

    if request.ai_agent_id:
        channel.ai_agent_id = UUID(request.ai_agent_id)
    channel.auto_reply_enabled = request.auto_reply_enabled
    channel.mention_only = request.mention_only
    channel.is_synced = request.is_synced

    await db.commit()
    return {"status": "configured"}


@router.post("/channels/{channel_id}/messages")
async def send_message(
    channel_id: str,
    request: SendMessageRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to a channel."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.chat.models import ChatChannel

    # SECURITY: Verify ownership via connection before sending
    result = await db.execute(
        select(ChatChannel)
        .options(selectinload(ChatChannel.connection))
        .where(ChatChannel.id == UUID(channel_id))
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.connection.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to send messages to this channel")

    service = ChatService(db)
    response = await service.send_message(
        channel_id=UUID(channel_id),
        content=request.content,
        thread_id=request.thread_id,
        attachments=request.attachments,
    )
    return response


@router.get("/channels/{channel_id}/messages")
async def get_messages(
    channel_id: str,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get messages from a channel."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.chat.models import ChatChannel

    # SECURITY: Verify ownership via connection before reading messages
    result = await db.execute(
        select(ChatChannel)
        .options(selectinload(ChatChannel.connection))
        .where(ChatChannel.id == UUID(channel_id))
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.connection.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to read messages from this channel")

    service = ChatService(db)
    messages = await service.get_messages(UUID(channel_id), limit)

    return [
        {
            "id": str(m.id),
            "message_id": m.message_id,
            "thread_id": m.thread_id,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "is_bot": m.is_bot,
            "content": m.content,
            "attachments": m.attachments,
            "received_at": m.received_at.isoformat(),
        }
        for m in messages
    ]


@router.post("/connections/{connection_id}/commands")
async def create_command(
    connection_id: str,
    request: CreateCommandRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a slash command."""
    from sqlalchemy import select
    from nexus.chat.models import ChatConnection

    # SECURITY: Verify ownership before creating command
    result = await db.execute(
        select(ChatConnection).where(ChatConnection.id == UUID(connection_id))
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    if connection.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to create commands for this connection")

    service = ChatService(db)
    command = await service.create_command(
        connection_id=UUID(connection_id),
        name=request.name,
        description=request.description,
        handler_type=request.handler_type,
        handler_id=UUID(request.handler_id) if request.handler_id else None,
        options=request.options,
    )

    return {
        "id": str(command.id),
        "name": command.name,
    }


@router.post("/webhook/slack")
async def slack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Slack event webhook."""
    data = await request.json()

    # URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Process events
    event = data.get("event", {})
    if event.get("type") == "message" and not event.get("bot_id"):
        service = ChatService(db)

        # Find connection by workspace
        from sqlalchemy import select, and_
        from nexus.chat.models import ChatConnection, ChatPlatform

        result = await db.execute(
            select(ChatConnection).where(
                and_(
                    ChatConnection.platform == ChatPlatform.SLACK,
                    ChatConnection.workspace_id == data.get("team_id"),
                )
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            from datetime import datetime
            await service.process_incoming_message(
                connection_id=connection.id,
                channel_id=event.get("channel"),
                message_id=event.get("ts"),
                sender_id=event.get("user"),
                content=event.get("text", ""),
                thread_id=event.get("thread_ts"),
                platform_timestamp=datetime.fromtimestamp(float(event.get("ts", 0))),
            )

    return {"status": "ok"}


@router.post("/webhook/discord")
async def discord_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Discord interaction webhook."""
    data = await request.json()
    # Discord webhook processing
    return {"type": 1}  # PONG for Discord verification


@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Telegram webhook."""
    data = await request.json()
    message = data.get("message", {})

    if message and message.get("text"):
        service = ChatService(db)

        # Find connection (would need bot token matching)
        # Process message
        pass

    return {"status": "ok"}
