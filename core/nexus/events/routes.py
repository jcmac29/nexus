"""Event API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.events.service import EventBus

router = APIRouter(prefix="/events", tags=["events"])


class PublishEventRequest(BaseModel):
    event_type: str
    topic: str
    payload: dict
    target_id: str | None = None
    target_type: str | None = None
    metadata: dict | None = None
    ttl_seconds: int | None = None


class SubscribeRequest(BaseModel):
    topic_pattern: str
    event_types: list[str] | None = None
    delivery_method: str = "websocket"
    webhook_url: str | None = None
    webhook_secret: str | None = None
    filters: dict | None = None


@router.post("/publish")
async def publish_event(
    request: PublishEventRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Publish an event to the event bus."""
    bus = EventBus(db)

    event = await bus.publish(
        event_type=request.event_type,
        topic=request.topic,
        payload=request.payload,
        source_id=agent.id,
        source_type="agent",
        target_id=UUID(request.target_id) if request.target_id else None,
        target_type=request.target_type,
        metadata=request.metadata,
        ttl_seconds=request.ttl_seconds,
    )

    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "topic": event.topic,
        "delivered_count": event.delivered_count,
        "created_at": event.created_at.isoformat(),
    }


@router.post("/subscribe")
async def subscribe_to_events(
    request: SubscribeRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Subscribe to events matching a pattern."""
    bus = EventBus(db)

    subscription = await bus.subscribe(
        subscriber_id=agent.id,
        topic_pattern=request.topic_pattern,
        subscriber_type="agent",
        event_types=request.event_types,
        delivery_method=request.delivery_method,
        webhook_url=request.webhook_url,
        webhook_secret=request.webhook_secret,
        filters=request.filters,
    )

    return {
        "subscription_id": str(subscription.id),
        "topic_pattern": subscription.topic_pattern,
        "event_types": subscription.event_types,
        "delivery_method": subscription.delivery_method,
        "created_at": subscription.created_at.isoformat(),
    }


@router.delete("/subscriptions/{subscription_id}")
async def unsubscribe(
    subscription_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Unsubscribe from events."""
    from sqlalchemy import select
    from nexus.events.models import EventSubscription

    # SECURITY: Verify subscription ownership before unsubscribing
    result = await db.execute(
        select(EventSubscription).where(EventSubscription.id == UUID(subscription_id))
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if subscription.subscriber_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this subscription")

    bus = EventBus(db)
    await bus.unsubscribe(UUID(subscription_id))
    return {"status": "unsubscribed"}


@router.get("/subscriptions")
async def list_subscriptions(
    active_only: bool = True,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List subscriptions for the current agent."""
    bus = EventBus(db)
    subscriptions = await bus.get_subscriptions(agent.id, active_only)

    return [
        {
            "id": str(s.id),
            "topic_pattern": s.topic_pattern,
            "event_types": s.event_types,
            "delivery_method": s.delivery_method,
            "is_active": s.is_active,
            "event_count": s.event_count,
            "last_event_at": s.last_event_at.isoformat() if s.last_event_at else None,
        }
        for s in subscriptions
    ]


@router.get("")
async def query_events(
    topic: str | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Query events."""
    bus = EventBus(db)
    events = await bus.get_events(
        topic=topic,
        event_type=event_type,
        since=since,
        limit=limit,
    )

    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "topic": e.topic,
            "payload": e.payload,
            "source_id": str(e.source_id) if e.source_id else None,
            "delivered_count": e.delivered_count,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.post("/{event_id}/acknowledge")
async def acknowledge_event(
    event_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge receipt of an event."""
    bus = EventBus(db)
    await bus.acknowledge(UUID(event_id), agent.id)
    return {"status": "acknowledged"}
