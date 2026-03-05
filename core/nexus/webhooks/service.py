"""Webhook delivery service with CRUD and retry logic."""

import asyncio
import fnmatch
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.webhooks.models import (
    DeliveryStatus,
    RetryPolicy,
    WebhookDeliveryLog,
    WebhookEndpoint,
)

logger = logging.getLogger(__name__)

# SECURITY: Blocked header names that could be used maliciously
BLOCKED_HEADERS = {
    "host", "authorization", "cookie", "set-cookie", "proxy-authorization",
    "x-forwarded-for", "x-real-ip", "x-forwarded-host", "x-forwarded-proto",
    "transfer-encoding", "content-length", "connection", "keep-alive",
}


def validate_webhook_url(url: str) -> None:
    """
    Validate webhook URL to prevent SSRF attacks.

    Raises ValueError if URL is unsafe.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must use http or https")

    # Must have a hostname
    if not parsed.hostname:
        raise ValueError("Webhook URL must have a hostname")

    hostname = parsed.hostname.lower()

    # Block localhost and common local hostnames
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "metadata.google.internal", "169.254.169.254",  # Cloud metadata
        "metadata.internal", "kubernetes.default",
    }
    if hostname in blocked_hosts:
        raise ValueError("Webhook URL cannot point to localhost or internal services")

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Webhook URL cannot point to private or reserved IP addresses")
    except ValueError:
        # Not an IP address, it's a hostname - check for suspicious patterns
        pass

    # Block internal-looking hostnames
    if any(internal in hostname for internal in [".internal", ".local", ".localhost", ".svc.cluster"]):
        raise ValueError("Webhook URL cannot point to internal services")


def sanitize_custom_headers(headers: dict) -> dict:
    """
    Sanitize custom webhook headers to prevent injection.

    Returns filtered headers dict.
    """
    if not headers:
        return {}

    sanitized = {}
    for key, value in headers.items():
        # Normalize header name
        key_lower = key.lower().strip()

        # Skip blocked headers
        if key_lower in BLOCKED_HEADERS:
            logger.warning(f"Blocked custom webhook header: {key}")
            continue

        # Validate header name (RFC 7230 - token chars only)
        if not all(c.isalnum() or c in "-_" for c in key_lower):
            logger.warning(f"Invalid webhook header name: {key}")
            continue

        # Limit header value length
        if len(str(value)) > 4096:
            logger.warning(f"Webhook header value too long: {key}")
            continue

        sanitized[key] = str(value)

    return sanitized


class WebhookService:
    """Service for webhook management and delivery."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- CRUD Operations ---

    async def create_endpoint(
        self,
        agent_id: UUID,
        name: str,
        url: str,
        event_types: list[str] | None = None,
        description: str | None = None,
        retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL,
        max_retries: int = 5,
        timeout_seconds: int = 30,
        custom_headers: dict | None = None,
    ) -> tuple[WebhookEndpoint, str]:
        """
        Create a webhook endpoint.

        Returns (endpoint, plain_secret) - secret is only shown once.
        """
        # SECURITY: Validate webhook URL to prevent SSRF
        validate_webhook_url(url)

        # SECURITY: Sanitize custom headers
        safe_headers = sanitize_custom_headers(custom_headers)

        # Generate a secure secret
        secret = secrets.token_urlsafe(32)

        endpoint = WebhookEndpoint(
            agent_id=agent_id,
            name=name,
            description=description,
            url=str(url),
            secret=secret,
            event_types=event_types or ["*"],
            retry_policy=retry_policy,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            custom_headers=safe_headers,
        )
        self.db.add(endpoint)
        await self.db.commit()
        await self.db.refresh(endpoint)
        return endpoint, secret

    async def get_endpoint(
        self,
        endpoint_id: UUID,
        agent_id: UUID | None = None,
    ) -> WebhookEndpoint | None:
        """Get a webhook endpoint by ID, optionally filtering by agent."""
        conditions = [WebhookEndpoint.id == endpoint_id]
        if agent_id:
            conditions.append(WebhookEndpoint.agent_id == agent_id)

        stmt = select(WebhookEndpoint).where(and_(*conditions))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_endpoints(
        self,
        agent_id: UUID,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[WebhookEndpoint], int]:
        """List webhook endpoints for an agent."""
        conditions = [WebhookEndpoint.agent_id == agent_id]
        if not include_inactive:
            conditions.append(WebhookEndpoint.is_active == True)

        # Get total count
        count_stmt = select(func.count()).select_from(WebhookEndpoint).where(and_(*conditions))
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get paginated results
        stmt = (
            select(WebhookEndpoint)
            .where(and_(*conditions))
            .order_by(WebhookEndpoint.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        endpoints = list(result.scalars().all())

        return endpoints, total

    async def update_endpoint(
        self,
        endpoint_id: UUID,
        agent_id: UUID,
        **updates,
    ) -> WebhookEndpoint | None:
        """Update a webhook endpoint."""
        endpoint = await self.get_endpoint(endpoint_id, agent_id)
        if not endpoint:
            return None

        # SECURITY: Whitelist of allowed fields to prevent mass assignment
        # Sensitive fields like 'secret', 'agent_id' are excluded
        allowed_fields = {
            "name",
            "url",
            "events",
            "is_active",
            "retry_config",
            "custom_headers",
        }

        # Apply updates only for allowed fields
        for key, value in updates.items():
            if key in allowed_fields and value is not None:
                setattr(endpoint, key, value)

        await self.db.commit()
        await self.db.refresh(endpoint)
        return endpoint

    async def delete_endpoint(
        self,
        endpoint_id: UUID,
        agent_id: UUID,
    ) -> bool:
        """Delete a webhook endpoint."""
        stmt = delete(WebhookEndpoint).where(
            and_(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.agent_id == agent_id,
            )
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def rotate_secret(
        self,
        endpoint_id: UUID,
        agent_id: UUID,
    ) -> tuple[WebhookEndpoint, str] | None:
        """Rotate the webhook secret. Returns (endpoint, new_secret)."""
        endpoint = await self.get_endpoint(endpoint_id, agent_id)
        if not endpoint:
            return None

        new_secret = secrets.token_urlsafe(32)
        endpoint.secret = new_secret
        await self.db.commit()
        await self.db.refresh(endpoint)
        return endpoint, new_secret

    # --- Delivery Operations ---

    async def trigger_webhook(
        self,
        event_type: str,
        payload: dict[str, Any],
        agent_id: UUID | None = None,
        event_id: UUID | None = None,
    ) -> list[WebhookDeliveryLog]:
        """
        Trigger webhooks for an event.

        Finds all matching webhook endpoints and creates delivery logs.
        Returns list of created delivery logs.
        """
        # Find matching endpoints
        conditions = [WebhookEndpoint.is_active == True]
        if agent_id:
            conditions.append(WebhookEndpoint.agent_id == agent_id)

        stmt = select(WebhookEndpoint).where(and_(*conditions))
        result = await self.db.execute(stmt)
        endpoints = list(result.scalars().all())

        delivery_logs = []
        for endpoint in endpoints:
            if self._matches_event_type(event_type, endpoint.event_types):
                log = await self._create_delivery_log(endpoint, event_type, payload, event_id)
                delivery_logs.append(log)
                # Start async delivery (fire and forget)
                asyncio.create_task(self._deliver(log.id))

        return delivery_logs

    def _matches_event_type(self, event_type: str, patterns: list[str]) -> bool:
        """Check if event type matches any of the subscription patterns."""
        for pattern in patterns:
            if pattern == "*" or pattern == event_type:
                return True
            # Support wildcards like "memory.*"
            if fnmatch.fnmatch(event_type, pattern):
                return True
        return False

    async def _create_delivery_log(
        self,
        endpoint: WebhookEndpoint,
        event_type: str,
        payload: dict,
        event_id: UUID | None = None,
    ) -> WebhookDeliveryLog:
        """Create a delivery log entry."""
        log = WebhookDeliveryLog(
            webhook_endpoint_id=endpoint.id,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            status=DeliveryStatus.PENDING,
        )
        self.db.add(log)

        # Update endpoint stats
        endpoint.total_deliveries += 1
        endpoint.last_triggered_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def _deliver(self, delivery_log_id: UUID) -> bool:
        """Attempt to deliver a webhook."""
        # Re-fetch in new session context
        stmt = (
            select(WebhookDeliveryLog)
            .where(WebhookDeliveryLog.id == delivery_log_id)
        )
        result = await self.db.execute(stmt)
        log = result.scalar_one_or_none()
        if not log:
            return False

        # Get endpoint
        endpoint = await self.get_endpoint(log.webhook_endpoint_id)
        if not endpoint:
            return False

        log.attempts += 1
        log.status = DeliveryStatus.RETRYING if log.attempts > 1 else DeliveryStatus.PENDING

        # Build request
        timestamp = datetime.now(timezone.utc).isoformat()
        body = {
            "event": log.event_type,
            "data": log.payload,
            "delivery_id": str(log.id),
            "timestamp": timestamp,
        }
        body_json = json.dumps(body, sort_keys=True)

        # Sign payload
        signature = self._sign_payload(endpoint.secret, timestamp, body_json)

        # SECURITY: Sanitize custom headers before use
        safe_custom_headers = sanitize_custom_headers(endpoint.custom_headers)

        headers = {
            "Content-Type": "application/json",
            "X-Nexus-Event": log.event_type,
            "X-Nexus-Delivery": str(log.id),
            "X-Nexus-Timestamp": timestamp,
            "X-Nexus-Signature": signature,
            **safe_custom_headers,
        }

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=endpoint.timeout_seconds) as client:
                response = await client.post(endpoint.url, content=body_json, headers=headers)

            log.response_time_ms = int((time.time() - start_time) * 1000)
            log.response_status_code = response.status_code
            log.response_body = response.text[:10240] if response.text else None  # Truncate to 10KB

            if response.status_code < 300:
                log.status = DeliveryStatus.DELIVERED
                log.delivered_at = datetime.now(timezone.utc)
                endpoint.successful_deliveries += 1
                endpoint.last_success_at = datetime.now(timezone.utc)
                await self.db.commit()
                return True
            else:
                log.last_error = f"HTTP {response.status_code}"

        except httpx.TimeoutException:
            log.response_time_ms = int((time.time() - start_time) * 1000)
            log.last_error = "Request timed out"
        except Exception as e:
            log.response_time_ms = int((time.time() - start_time) * 1000)
            log.last_error = str(e)[:1000]

        # Handle retry logic
        if log.attempts < endpoint.max_retries and endpoint.retry_policy != RetryPolicy.NONE:
            delay = self._get_retry_delay(endpoint.retry_policy, log.attempts)
            log.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            log.status = DeliveryStatus.RETRYING
            await self.db.commit()
            # Schedule retry
            asyncio.create_task(self._retry_after_delay(log.id, delay))
        else:
            log.status = DeliveryStatus.FAILED
            endpoint.failed_deliveries += 1
            endpoint.last_failure_at = datetime.now(timezone.utc)
            await self.db.commit()

        return False

    def _sign_payload(self, secret: str, timestamp: str, body: str) -> str:
        """Create HMAC-SHA256 signature for webhook payload."""
        message = f"{timestamp}.{body}"
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}"

    def _get_retry_delay(self, policy: RetryPolicy, attempt: int) -> int:
        """Calculate retry delay based on policy."""
        if policy == RetryPolicy.EXPONENTIAL:
            return 2 ** attempt  # 2, 4, 8, 16, 32 seconds
        elif policy == RetryPolicy.LINEAR:
            return attempt * 10  # 10, 20, 30, 40, 50 seconds
        return 0

    async def _retry_after_delay(self, delivery_log_id: UUID, delay: int):
        """Retry delivery after delay."""
        await asyncio.sleep(delay)
        await self._deliver(delivery_log_id)

    async def retry_delivery(
        self,
        delivery_id: UUID,
        agent_id: UUID,
    ) -> WebhookDeliveryLog | None:
        """Manually retry a failed delivery."""
        stmt = (
            select(WebhookDeliveryLog)
            .join(WebhookEndpoint)
            .where(
                and_(
                    WebhookDeliveryLog.id == delivery_id,
                    WebhookEndpoint.agent_id == agent_id,
                )
            )
        )
        result = await self.db.execute(stmt)
        log = result.scalar_one_or_none()
        if not log:
            return None

        # Reset for retry
        log.status = DeliveryStatus.PENDING
        log.next_retry_at = None
        await self.db.commit()

        # Trigger delivery
        asyncio.create_task(self._deliver(log.id))
        return log

    # --- Delivery Log Operations ---

    async def get_delivery_logs(
        self,
        endpoint_id: UUID,
        agent_id: UUID,
        status: DeliveryStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WebhookDeliveryLog], int]:
        """Get delivery logs for an endpoint."""
        # Verify ownership
        endpoint = await self.get_endpoint(endpoint_id, agent_id)
        if not endpoint:
            return [], 0

        conditions = [WebhookDeliveryLog.webhook_endpoint_id == endpoint_id]
        if status:
            conditions.append(WebhookDeliveryLog.status == status)

        # Get total count
        count_stmt = select(func.count()).select_from(WebhookDeliveryLog).where(and_(*conditions))
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get paginated results
        stmt = (
            select(WebhookDeliveryLog)
            .where(and_(*conditions))
            .order_by(WebhookDeliveryLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        logs = list(result.scalars().all())

        return logs, total

    async def get_delivery_log(
        self,
        delivery_id: UUID,
        agent_id: UUID,
    ) -> WebhookDeliveryLog | None:
        """Get a specific delivery log."""
        stmt = (
            select(WebhookDeliveryLog)
            .join(WebhookEndpoint)
            .where(
                and_(
                    WebhookDeliveryLog.id == delivery_id,
                    WebhookEndpoint.agent_id == agent_id,
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # --- Test Operations ---

    async def test_webhook(
        self,
        endpoint_id: UUID,
        agent_id: UUID,
    ) -> dict:
        """Send a test ping to a webhook endpoint."""
        endpoint = await self.get_endpoint(endpoint_id, agent_id)
        if not endpoint:
            return {"success": False, "error": "Webhook not found"}

        timestamp = datetime.now(timezone.utc).isoformat()
        body = {
            "event": "webhook.test",
            "data": {"message": "This is a test webhook from Nexus"},
            "delivery_id": "test",
            "timestamp": timestamp,
        }
        body_json = json.dumps(body, sort_keys=True)
        signature = self._sign_payload(endpoint.secret, timestamp, body_json)

        # SECURITY: Sanitize custom headers (defense in depth)
        safe_custom_headers = sanitize_custom_headers(endpoint.custom_headers)

        headers = {
            "Content-Type": "application/json",
            "X-Nexus-Event": "webhook.test",
            "X-Nexus-Delivery": "test",
            "X-Nexus-Timestamp": timestamp,
            "X-Nexus-Signature": signature,
            **safe_custom_headers,
        }

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=endpoint.timeout_seconds) as client:
                response = await client.post(endpoint.url, content=body_json, headers=headers)

            response_time_ms = int((time.time() - start_time) * 1000)
            return {
                "success": response.status_code < 300,
                "status_code": response.status_code,
                "response_time_ms": response_time_ms,
                "error": None if response.status_code < 300 else f"HTTP {response.status_code}",
            }

        except httpx.TimeoutException:
            return {
                "success": False,
                "status_code": None,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "error": "Request timed out",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "error": str(e),
            }

    # --- Cleanup Operations ---

    async def cleanup_old_logs(self, retention_days: int = 30) -> int:
        """Delete delivery logs older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        stmt = delete(WebhookDeliveryLog).where(WebhookDeliveryLog.created_at < cutoff)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    # --- Background Processing ---

    async def process_pending_retries(self) -> int:
        """Process deliveries that are due for retry."""
        now = datetime.now(timezone.utc)
        stmt = select(WebhookDeliveryLog).where(
            and_(
                WebhookDeliveryLog.status == DeliveryStatus.RETRYING,
                WebhookDeliveryLog.next_retry_at <= now,
            )
        ).limit(100)
        result = await self.db.execute(stmt)
        logs = list(result.scalars().all())

        for log in logs:
            asyncio.create_task(self._deliver(log.id))

        return len(logs)


# Legacy singleton for backward compatibility
class LegacyWebhookService:
    """In-memory webhook service for backward compatibility."""

    def __init__(self):
        self._pending_count = 0

    def get_pending_count(self) -> int:
        return self._pending_count


webhook_service = LegacyWebhookService()
