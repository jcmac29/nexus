"""Notification service for push notifications."""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.notifications.models import (
    Notification, NotificationTemplate, PushDevice, NotificationPreference,
    NotificationChannel, NotificationPriority, NotificationStatus, NotificationCategory
)

logger = logging.getLogger(__name__)


def _validate_webhook_url(url: str | None) -> bool:
    """
    Validate webhook URL to prevent SSRF attacks.

    Returns True if URL is safe, False otherwise.
    """
    if not url:
        return False

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
        logger.warning(f"Blocked webhook to: {hostname}")
        return False

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            logger.warning(f"Blocked webhook to private IP: {hostname}")
            return False
    except ValueError:
        # Not an IP address, it's a hostname
        pass

    # Block internal-looking hostnames
    if any(internal in hostname for internal in [".internal", ".local", ".localhost", ".svc.cluster"]):
        logger.warning(f"Blocked webhook to internal host: {hostname}")
        return False

    return True


class NotificationService:
    """Service for notification operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._providers = {}

    def configure_fcm(self, credentials_path: str):
        """Configure Firebase Cloud Messaging."""
        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate(credentials_path)
        firebase_admin.initialize_app(cred)
        self._providers["fcm"] = True

    def configure_apns(self, key_path: str, key_id: str, team_id: str):
        """Configure Apple Push Notification Service."""
        self._providers["apns"] = {
            "key_path": key_path,
            "key_id": key_id,
            "team_id": team_id,
        }

    async def send_notification(
        self,
        recipient_id: UUID,
        title: str,
        body: str | None = None,
        channel: NotificationChannel = NotificationChannel.IN_APP,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        data: dict | None = None,
        action_url: str | None = None,
        sender_id: UUID | None = None,
        sender_type: str | None = None,
        scheduled_for: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> Notification:
        """Send a notification."""
        # SECURITY: Validate webhook URL at input time
        if channel == NotificationChannel.WEBHOOK and action_url:
            if not _validate_webhook_url(action_url):
                raise ValueError("Invalid action URL for webhook notification")

        # Check preferences
        prefs = await self._get_preferences(recipient_id)
        if prefs and not self._should_send(prefs, channel, category):
            # Create but don't send
            notification = Notification(
                recipient_id=recipient_id,
                sender_id=sender_id,
                sender_type=sender_type,
                title=title,
                body=body,
                category=category,
                priority=priority,
                channel=channel,
                data=data or {},
                action_url=action_url,
                status=NotificationStatus.EXPIRED,
                scheduled_for=scheduled_for,
                expires_at=expires_at,
            )
            self.db.add(notification)
            await self.db.commit()
            return notification

        notification = Notification(
            recipient_id=recipient_id,
            sender_id=sender_id,
            sender_type=sender_type,
            title=title,
            body=body,
            category=category,
            priority=priority,
            channel=channel,
            data=data or {},
            action_url=action_url,
            status=NotificationStatus.PENDING,
            scheduled_for=scheduled_for,
            expires_at=expires_at,
        )
        self.db.add(notification)
        await self.db.flush()

        # Send immediately if not scheduled
        if not scheduled_for or scheduled_for <= datetime.utcnow():
            await self._deliver_notification(notification)

        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def _deliver_notification(self, notification: Notification):
        """Deliver a notification via the specified channel."""
        if notification.channel == NotificationChannel.PUSH:
            await self._send_push(notification)
        elif notification.channel == NotificationChannel.IN_APP:
            notification.status = NotificationStatus.DELIVERED
            notification.delivered_at = datetime.utcnow()
        elif notification.channel == NotificationChannel.WEBHOOK:
            await self._send_webhook(notification)

        notification.sent_at = datetime.utcnow()

    async def _send_push(self, notification: Notification):
        """Send push notification to devices."""
        # Get user's devices
        result = await self.db.execute(
            select(PushDevice).where(
                and_(
                    PushDevice.owner_id == notification.recipient_id,
                    PushDevice.is_active == True,
                    PushDevice.enabled == True,
                )
            )
        )
        devices = result.scalars().all()

        for device in devices:
            if device.push_provider == "fcm" and "fcm" in self._providers:
                try:
                    from firebase_admin import messaging
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=notification.title,
                            body=notification.body,
                        ),
                        data={k: str(v) for k, v in (notification.data or {}).items()},
                        token=device.device_token,
                    )
                    response = messaging.send(message)
                    notification.provider_message_id = response
                    notification.status = NotificationStatus.SENT
                    device.last_push_at = datetime.utcnow()
                except Exception as e:
                    notification.error_message = str(e)
                    notification.status = NotificationStatus.FAILED

    async def _send_webhook(self, notification: Notification):
        """Send notification via webhook."""
        import httpx
        if notification.action_url:
            # SECURITY: Validate URL to prevent SSRF
            if not _validate_webhook_url(notification.action_url):
                notification.status = NotificationStatus.FAILED
                notification.error_message = "Invalid webhook URL"
                return

            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        notification.action_url,
                        json={
                            "notification_id": str(notification.id),
                            "title": notification.title,
                            "body": notification.body,
                            "data": notification.data,
                        },
                        timeout=10.0,
                    )
                notification.status = NotificationStatus.DELIVERED
                notification.delivered_at = datetime.utcnow()
            except Exception as e:
                notification.status = NotificationStatus.FAILED
                notification.error_message = str(e)

    async def _get_preferences(self, recipient_id: UUID) -> NotificationPreference | None:
        """Get notification preferences."""
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.owner_id == recipient_id
            )
        )
        return result.scalar_one_or_none()

    def _should_send(
        self,
        prefs: NotificationPreference,
        channel: NotificationChannel,
        category: NotificationCategory,
    ) -> bool:
        """Check if notification should be sent based on preferences."""
        # Check DND
        if prefs.dnd_enabled and prefs.dnd_until:
            if datetime.utcnow() < prefs.dnd_until:
                return False

        # Check channel enabled
        channel_map = {
            NotificationChannel.PUSH: prefs.push_enabled,
            NotificationChannel.EMAIL: prefs.email_enabled,
            NotificationChannel.SMS: prefs.sms_enabled,
            NotificationChannel.IN_APP: prefs.in_app_enabled,
        }
        if not channel_map.get(channel, True):
            return False

        # Check category preferences
        cat_prefs = prefs.categories.get(category.value, {})
        if cat_prefs.get("enabled") is False:
            return False

        return True

    async def mark_as_read(self, notification_id: UUID):
        """Mark a notification as read."""
        result = await self.db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        if notification and notification.status != NotificationStatus.READ:
            notification.status = NotificationStatus.READ
            notification.read_at = datetime.utcnow()
            await self.db.commit()

    async def mark_all_read(self, recipient_id: UUID):
        """Mark all notifications as read for a recipient."""
        result = await self.db.execute(
            select(Notification).where(
                and_(
                    Notification.recipient_id == recipient_id,
                    Notification.status != NotificationStatus.READ,
                )
            )
        )
        notifications = result.scalars().all()
        for n in notifications:
            n.status = NotificationStatus.READ
            n.read_at = datetime.utcnow()
        await self.db.commit()

    async def list_notifications(
        self,
        recipient_id: UUID,
        unread_only: bool = False,
        category: NotificationCategory | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        """List notifications for a recipient."""
        query = select(Notification).where(Notification.recipient_id == recipient_id)

        if unread_only:
            query = query.where(Notification.status != NotificationStatus.READ)
        if category:
            query = query.where(Notification.category == category)

        query = query.order_by(Notification.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_unread_count(self, recipient_id: UUID) -> int:
        """Get unread notification count."""
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.recipient_id == recipient_id,
                    Notification.status != NotificationStatus.READ,
                )
            )
        )
        return result.scalar() or 0

    async def register_device(
        self,
        owner_id: UUID,
        device_token: str,
        device_type: str,
        push_provider: str = "fcm",
        device_name: str | None = None,
        app_version: str | None = None,
    ) -> PushDevice:
        """Register a device for push notifications."""
        # Check if device exists
        result = await self.db.execute(
            select(PushDevice).where(PushDevice.device_token == device_token)
        )
        device = result.scalar_one_or_none()

        if device:
            device.owner_id = owner_id
            device.device_name = device_name
            device.app_version = app_version
            device.last_active_at = datetime.utcnow()
            device.is_active = True
        else:
            device = PushDevice(
                owner_id=owner_id,
                device_token=device_token,
                device_type=device_type,
                push_provider=push_provider,
                device_name=device_name,
                app_version=app_version,
                last_active_at=datetime.utcnow(),
            )
            self.db.add(device)

        await self.db.commit()
        await self.db.refresh(device)
        return device

    async def unregister_device(self, device_token: str):
        """Unregister a device."""
        result = await self.db.execute(
            select(PushDevice).where(PushDevice.device_token == device_token)
        )
        device = result.scalar_one_or_none()
        if device:
            device.is_active = False
            await self.db.commit()

    async def send_from_template(
        self,
        template_name: str,
        recipient_id: UUID,
        variables: dict,
        channels: list[NotificationChannel] | None = None,
        sender_id: UUID | None = None,
    ) -> list[Notification]:
        """Send notification from a template."""
        result = await self.db.execute(
            select(NotificationTemplate).where(NotificationTemplate.name == template_name)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Template '{template_name}' not found")

        # Render template
        title = template.title_template
        body = template.body_template or ""
        for key, value in variables.items():
            title = title.replace(f"{{{{{key}}}}}", str(value))
            body = body.replace(f"{{{{{key}}}}}", str(value))

        # Send to all channels
        target_channels = channels or [NotificationChannel(c) for c in template.default_channels]
        notifications = []

        for channel in target_channels:
            notification = await self.send_notification(
                recipient_id=recipient_id,
                title=title,
                body=body,
                channel=channel,
                category=template.category,
                priority=template.priority,
                sender_id=sender_id,
            )
            notifications.append(notification)

        return notifications
