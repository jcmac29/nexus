"""Webhook delivery service with retry logic."""

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx


class WebhookDelivery:
    """Represents a webhook delivery attempt."""

    def __init__(
        self,
        id: str,
        webhook_url: str,
        event: str,
        payload: dict,
        agent_id: UUID,
        secret: str | None = None,
    ):
        self.id = id
        self.webhook_url = webhook_url
        self.event = event
        self.payload = payload
        self.agent_id = agent_id
        self.secret = secret
        self.attempts = 0
        self.max_attempts = 5
        self.last_error: str | None = None
        self.status = "pending"  # pending, delivered, failed
        self.created_at = datetime.now(timezone.utc)
        self.delivered_at: datetime | None = None

    def get_retry_delay(self) -> int:
        """Get delay before next retry (exponential backoff)."""
        # 1s, 2s, 4s, 8s, 16s
        return 2 ** self.attempts

    def sign_payload(self) -> str | None:
        """Create HMAC signature for payload."""
        if not self.secret:
            return None
        payload_bytes = json.dumps(self.payload, sort_keys=True).encode()
        signature = hmac.new(
            self.secret.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"


class WebhookService:
    """Service for reliable webhook delivery."""

    def __init__(self):
        self._pending_deliveries: dict[str, WebhookDelivery] = {}
        self._delivery_task: asyncio.Task | None = None

    async def send(
        self,
        webhook_url: str,
        event: str,
        payload: dict[str, Any],
        agent_id: UUID,
        secret: str | None = None,
    ) -> WebhookDelivery:
        """
        Queue a webhook for delivery.

        Returns immediately, delivery happens in background with retries.
        """
        delivery = WebhookDelivery(
            id=str(uuid4()),
            webhook_url=webhook_url,
            event=event,
            payload=payload,
            agent_id=agent_id,
            secret=secret,
        )

        self._pending_deliveries[delivery.id] = delivery

        # Attempt immediate delivery
        asyncio.create_task(self._deliver(delivery))

        return delivery

    async def _deliver(self, delivery: WebhookDelivery) -> bool:
        """Attempt to deliver a webhook."""
        delivery.attempts += 1

        headers = {
            "Content-Type": "application/json",
            "X-Nexus-Event": delivery.event,
            "X-Nexus-Delivery": delivery.id,
            "X-Nexus-Timestamp": datetime.now(timezone.utc).isoformat(),
        }

        signature = delivery.sign_payload()
        if signature:
            headers["X-Nexus-Signature"] = signature

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    delivery.webhook_url,
                    json={
                        "event": delivery.event,
                        "data": delivery.payload,
                        "delivery_id": delivery.id,
                        "timestamp": headers["X-Nexus-Timestamp"],
                    },
                    headers=headers,
                )

                if response.status_code < 300:
                    delivery.status = "delivered"
                    delivery.delivered_at = datetime.now(timezone.utc)
                    self._pending_deliveries.pop(delivery.id, None)
                    return True
                else:
                    delivery.last_error = f"HTTP {response.status_code}"

        except httpx.TimeoutException:
            delivery.last_error = "Timeout"
        except Exception as e:
            delivery.last_error = str(e)

        # Schedule retry if attempts remaining
        if delivery.attempts < delivery.max_attempts:
            delay = delivery.get_retry_delay()
            asyncio.create_task(self._retry_after_delay(delivery, delay))
        else:
            delivery.status = "failed"
            self._pending_deliveries.pop(delivery.id, None)

        return False

    async def _retry_after_delay(self, delivery: WebhookDelivery, delay: int):
        """Retry delivery after a delay."""
        await asyncio.sleep(delay)
        await self._deliver(delivery)

    def get_delivery(self, delivery_id: str) -> WebhookDelivery | None:
        """Get a delivery by ID."""
        return self._pending_deliveries.get(delivery_id)

    def get_pending_count(self) -> int:
        """Get count of pending deliveries."""
        return len(self._pending_deliveries)


# Singleton instance
webhook_service = WebhookService()
