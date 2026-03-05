"""WebSocket routes for real-time communication."""

from __future__ import annotations

import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.websockets.manager import manager, WebSocketConnection

router = APIRouter(prefix="/ws", tags=["websockets"])


async def get_agent_from_token(
    token: str,
    db: AsyncSession,
) -> Agent | None:
    """Validate token and get agent."""
    from nexus.auth import verify_api_key

    try:
        agent = await verify_api_key(token, db)
        return agent
    except Exception:
        return None


@router.websocket("/connect")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for real-time agent communication.

    Message types:
    - subscribe: {"type": "subscribe", "channel": "channel-name"}
    - unsubscribe: {"type": "unsubscribe", "channel": "channel-name"}
    - message: {"type": "message", "to": "agent-id", "data": {...}}
    - channel_message: {"type": "channel_message", "channel": "name", "data": {...}}
    - ping: {"type": "ping"}
    """
    # Authenticate
    agent = await get_agent_from_token(token, db)
    if not agent:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Connect
    conn = await manager.connect(websocket, str(agent.id))

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "agent_id": str(agent.id),
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Message loop
        while True:
            data = await websocket.receive_json()
            await handle_message(conn, data, db)

    except WebSocketDisconnect:
        await manager.disconnect(conn)
    except Exception as e:
        await manager.disconnect(conn)
        raise


async def handle_message(
    conn: WebSocketConnection,
    data: dict,
    db: AsyncSession,
):
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type")

    if msg_type == "ping":
        await conn.websocket.send_json({
            "type": "pong",
            "timestamp": datetime.utcnow().isoformat(),
        })

    elif msg_type == "subscribe":
        channel = data.get("channel")
        if channel:
            await manager.subscribe(conn, channel)
            await conn.websocket.send_json({
                "type": "subscribed",
                "channel": channel,
            })

    elif msg_type == "unsubscribe":
        channel = data.get("channel")
        if channel:
            await manager.unsubscribe(conn, channel)
            await conn.websocket.send_json({
                "type": "unsubscribed",
                "channel": channel,
            })

    elif msg_type == "message":
        # Direct message to another agent
        to_agent = data.get("to")
        payload = data.get("data", {})

        if to_agent:
            sent = await manager.send_to_agent(to_agent, {
                "type": "message",
                "from": conn.agent_id,
                "data": payload,
                "timestamp": datetime.utcnow().isoformat(),
            })

            await conn.websocket.send_json({
                "type": "message_sent",
                "to": to_agent,
                "delivered": sent > 0,
            })

    elif msg_type == "channel_message":
        # Broadcast to channel
        channel = data.get("channel")
        payload = data.get("data", {})

        if channel and channel in conn.subscriptions:
            await manager.send_to_channel(
                channel,
                {
                    "type": "channel_message",
                    "channel": channel,
                    "from": conn.agent_id,
                    "data": payload,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                exclude_agent=conn.agent_id,
            )

    elif msg_type == "get_online":
        # Get list of online agents
        online = manager.get_online_agents()
        await conn.websocket.send_json({
            "type": "online_agents",
            "agents": online,
        })

    elif msg_type == "get_channel_members":
        channel = data.get("channel")
        if channel:
            members = list(manager.get_channel_members(channel))
            await conn.websocket.send_json({
                "type": "channel_members",
                "channel": channel,
                "members": members,
            })


@router.get("/online")
async def get_online_agents(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get list of currently online agents."""
    # SECURITY: Require authentication
    agent = await get_agent_from_token(token, db)
    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"online": manager.get_online_agents()}


@router.get("/channels/{channel}/members")
async def get_channel_members(
    channel: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get members of a channel."""
    # SECURITY: Require authentication
    agent = await get_agent_from_token(token, db)
    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"channel": channel, "members": list(manager.get_channel_members(channel))}
