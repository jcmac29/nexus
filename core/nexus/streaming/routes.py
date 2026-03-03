"""Server-Sent Events streaming routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.streaming.service import event_manager

router = APIRouter(prefix="/stream", tags=["streaming"])


@router.get("/events")
async def stream_events(
    request: Request,
    agent: Agent = Depends(get_current_agent),
):
    """
    Stream real-time events for the current agent.

    Events include:
    - invocation.update: When an invocation status changes
    - message.received: When a new message arrives
    - capability.invoked: When someone invokes your capability

    Use Server-Sent Events (SSE) to receive updates.
    """
    stream = event_manager.connect(agent.id)

    async def event_generator():
        try:
            async for event in stream.events():
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                yield event
        finally:
            event_manager.disconnect(stream)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def stream_status(agent: Agent = Depends(get_current_agent)):
    """Get streaming connection status."""
    return {
        "agent_id": str(agent.id),
        "active_connections": event_manager.get_connection_count(agent.id),
    }
