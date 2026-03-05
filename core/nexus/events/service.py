"""Event Bus service for pub/sub messaging."""

from __future__ import annotations

import asyncio
import fnmatch
import ipaddress
import logging
import httpx
from datetime import datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.events.models import Event, EventSubscription, EventDelivery

logger = logging.getLogger(__name__)


def _validate_webhook_url(url: str | None) -> bool:
    """
    Validate webhook URL to prevent SSRF attacks.

    Returns True if URL is safe, False otherwise.
    """
    if not url:
        return True  # None is valid (no webhook)

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        return False

    # Must have a hostname
    if not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()

    # Block localhost and common local hostnames
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "metadata.google.internal", "169.254.169.254",
        "metadata.internal", "kubernetes.default",
    }
    if hostname in blocked_hosts:
        logger.warning(f"Blocked event webhook to: {hostname}")
        return False

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            logger.warning(f"Blocked event webhook to private IP: {hostname}")
            return False
    except ValueError:
        # Not an IP address, it's a hostname
        pass

    # Block internal-looking hostnames
    if any(internal in hostname for internal in [".internal", ".local", ".localhost", ".svc.cluster"]):
        logger.warning(f"Blocked event webhook to internal host: {hostname}")
        return False

    return True


class EventBus:
    """Central event bus for pub/sub messaging."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._handlers: dict[str, list[Callable]] = {}  # In-memory handlers

    async def publish(
        self,
        event_type: str,
        topic: str,
        payload: dict,
        source_id: UUID | None = None,
        source_type: str | None = None,
        target_id: UUID | None = None,
        target_type: str | None = None,
        metadata: dict | None = None,
        ttl_seconds: int | None = None,
    ) -> Event:
        """Publish an event to the bus."""
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        event = Event(
            event_type=event_type,
            topic=topic,
            payload=payload,
            source_id=source_id,
            source_type=source_type,
            target_id=target_id,
            target_type=target_type,
            metadata=metadata or {},
            expires_at=expires_at,
        )
        self.db.add(event)
        await self.db.flush()

        # Deliver to subscribers
        await self._deliver_event(event)

        await self.db.commit()
        await self.db.refresh(event)

        # Trigger in-memory handlers
        await self._trigger_handlers(event)

        return event

    async def subscribe(
        self,
        subscriber_id: UUID,
        topic_pattern: str,
        subscriber_type: str = "agent",
        event_types: list[str] | None = None,
        delivery_method: str = "websocket",
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        filters: dict | None = None,
    ) -> EventSubscription:
        """Create a subscription to events."""
        # SECURITY: Validate webhook URL to prevent SSRF
        if delivery_method == "webhook" and webhook_url:
            if not _validate_webhook_url(webhook_url):
                raise ValueError("Invalid webhook URL: must be a public HTTP/HTTPS endpoint")

        subscription = EventSubscription(
            subscriber_id=subscriber_id,
            subscriber_type=subscriber_type,
            topic_pattern=topic_pattern,
            event_types=event_types or [],
            delivery_method=delivery_method,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            filters=filters or {},
        )
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def unsubscribe(self, subscription_id: UUID):
        """Remove a subscription."""
        result = await self.db.execute(
            select(EventSubscription).where(EventSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription:
            subscription.is_active = False
            await self.db.commit()

    async def get_subscriptions(
        self,
        subscriber_id: UUID,
        active_only: bool = True,
    ) -> list[EventSubscription]:
        """Get subscriptions for a subscriber."""
        query = select(EventSubscription).where(
            EventSubscription.subscriber_id == subscriber_id
        )
        if active_only:
            query = query.where(EventSubscription.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_events(
        self,
        topic: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Query events."""
        query = select(Event).order_by(Event.created_at.desc()).limit(limit)

        if topic:
            query = query.where(Event.topic == topic)
        if event_type:
            query = query.where(Event.event_type == event_type)
        if since:
            query = query.where(Event.created_at >= since)

        # Exclude expired events
        query = query.where(
            or_(
                Event.expires_at == None,
                Event.expires_at > datetime.utcnow(),
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def acknowledge(self, event_id: UUID, subscriber_id: UUID):
        """Acknowledge receipt of an event."""
        result = await self.db.execute(
            select(EventDelivery).where(
                and_(
                    EventDelivery.event_id == event_id,
                    EventDelivery.subscription_id.in_(
                        select(EventSubscription.id).where(
                            EventSubscription.subscriber_id == subscriber_id
                        )
                    ),
                )
            )
        )
        delivery = result.scalar_one_or_none()

        if delivery:
            delivery.status = "acknowledged"
            delivery.acknowledged_at = datetime.utcnow()

            # Update event acknowledged count
            event_result = await self.db.execute(
                select(Event).where(Event.id == event_id)
            )
            event = event_result.scalar_one_or_none()
            if event:
                event.acknowledged_count += 1

            await self.db.commit()

    async def _deliver_event(self, event: Event):
        """Deliver event to matching subscribers."""
        # Find matching subscriptions
        result = await self.db.execute(
            select(EventSubscription).where(EventSubscription.is_active == True)
        )
        subscriptions = result.scalars().all()

        for sub in subscriptions:
            if self._matches_subscription(event, sub):
                await self._deliver_to_subscriber(event, sub)

    def _matches_subscription(self, event: Event, subscription: EventSubscription) -> bool:
        """Check if an event matches a subscription."""
        # Check topic pattern (supports wildcards)
        if not fnmatch.fnmatch(event.topic, subscription.topic_pattern):
            return False

        # Check event types
        if subscription.event_types and event.event_type not in subscription.event_types:
            return False

        # Check filters
        if subscription.filters:
            for key, value in subscription.filters.items():
                if event.payload.get(key) != value:
                    return False

        return True

    async def _deliver_to_subscriber(self, event: Event, subscription: EventSubscription):
        """Deliver event to a specific subscriber."""
        delivery = EventDelivery(
            event_id=event.id,
            subscription_id=subscription.id,
            status="pending",
        )
        self.db.add(delivery)

        try:
            if subscription.delivery_method == "websocket":
                await self._deliver_via_websocket(event, subscription)
                delivery.status = "delivered"
            elif subscription.delivery_method == "webhook":
                await self._deliver_via_webhook(event, subscription)
                delivery.status = "delivered"
            elif subscription.delivery_method == "queue":
                # Queue delivery handled separately
                delivery.status = "queued"

            delivery.delivered_at = datetime.utcnow()
            event.delivered_count += 1
            subscription.event_count += 1
            subscription.last_event_at = datetime.utcnow()

        except Exception as e:
            delivery.status = "failed"
            delivery.error = str(e)
            delivery.attempts += 1

        delivery.last_attempt_at = datetime.utcnow()

    async def _deliver_via_websocket(self, event: Event, subscription: EventSubscription):
        """Deliver event via WebSocket."""
        try:
            from nexus.websockets.manager import manager

            await manager.send_to_agent(
                str(subscription.subscriber_id),
                {
                    "type": "event",
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "topic": event.topic,
                    "payload": event.payload,
                    "source_id": str(event.source_id) if event.source_id else None,
                    "timestamp": event.created_at.isoformat(),
                },
            )
        except Exception:
            # WebSocket might not be available
            pass

    async def _deliver_via_webhook(self, event: Event, subscription: EventSubscription):
        """Deliver event via webhook."""
        if not subscription.webhook_url:
            return

        # SECURITY: Validate URL to prevent SSRF (defense in depth)
        if not _validate_webhook_url(subscription.webhook_url):
            logger.warning(f"Blocked delivery to invalid webhook URL for subscription {subscription.id}")
            return

        headers = {"Content-Type": "application/json"}
        if subscription.webhook_secret:
            import hmac
            import hashlib
            import json

            payload_str = json.dumps(event.payload)
            signature = hmac.new(
                subscription.webhook_secret.encode(),
                payload_str.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Nexus-Signature"] = signature

        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                subscription.webhook_url,
                json={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "topic": event.topic,
                    "payload": event.payload,
                    "timestamp": event.created_at.isoformat(),
                },
                headers=headers,
            )

    def register_handler(self, topic_pattern: str, handler: Callable):
        """Register an in-memory event handler."""
        if topic_pattern not in self._handlers:
            self._handlers[topic_pattern] = []
        self._handlers[topic_pattern].append(handler)

    async def _trigger_handlers(self, event: Event):
        """Trigger in-memory handlers for an event."""
        for pattern, handlers in self._handlers.items():
            if fnmatch.fnmatch(event.topic, pattern):
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception:
                        pass  # Handler errors shouldn't affect event flow

    async def cleanup_expired(self) -> int:
        """Clean up expired events. Returns count deleted."""
        from sqlalchemy import delete

        result = await self.db.execute(
            delete(Event).where(
                and_(
                    Event.expires_at != None,
                    Event.expires_at < datetime.utcnow(),
                )
            )
        )
        await self.db.commit()
        return result.rowcount
