"""Notification API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.notifications.service import NotificationService
from nexus.notifications.models import NotificationChannel, NotificationCategory, NotificationPriority

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SendNotificationRequest(BaseModel):
    recipient_id: str
    title: str
    body: str | None = None
    channel: str = "in_app"
    category: str = "system"
    priority: str = "normal"
    data: dict | None = None
    action_url: str | None = None
    scheduled_for: str | None = None


class RegisterDeviceRequest(BaseModel):
    device_token: str
    device_type: str  # ios, android, web
    push_provider: str = "fcm"
    device_name: str | None = None
    app_version: str | None = None


class SendFromTemplateRequest(BaseModel):
    template_name: str
    recipient_id: str
    variables: dict
    channels: list[str] | None = None


class UpdatePreferencesRequest(BaseModel):
    push_enabled: bool | None = None
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    in_app_enabled: bool | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    dnd_enabled: bool | None = None
    dnd_until: str | None = None


@router.post("/send")
async def send_notification(
    request: SendNotificationRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send a notification."""
    service = NotificationService(db)

    channel_map = {
        "push": NotificationChannel.PUSH,
        "email": NotificationChannel.EMAIL,
        "sms": NotificationChannel.SMS,
        "webhook": NotificationChannel.WEBHOOK,
        "in_app": NotificationChannel.IN_APP,
    }
    category_map = {
        "system": NotificationCategory.SYSTEM,
        "agent": NotificationCategory.AGENT,
        "message": NotificationCategory.MESSAGE,
        "alert": NotificationCategory.ALERT,
        "reminder": NotificationCategory.REMINDER,
    }
    priority_map = {
        "low": NotificationPriority.LOW,
        "normal": NotificationPriority.NORMAL,
        "high": NotificationPriority.HIGH,
        "urgent": NotificationPriority.URGENT,
    }

    notification = await service.send_notification(
        recipient_id=UUID(request.recipient_id),
        title=request.title,
        body=request.body,
        channel=channel_map.get(request.channel, NotificationChannel.IN_APP),
        category=category_map.get(request.category, NotificationCategory.SYSTEM),
        priority=priority_map.get(request.priority, NotificationPriority.NORMAL),
        data=request.data,
        action_url=request.action_url,
        sender_id=agent.id,
        sender_type="agent",
        scheduled_for=datetime.fromisoformat(request.scheduled_for) if request.scheduled_for else None,
    )

    return {
        "id": str(notification.id),
        "status": notification.status.value,
        "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
    }


@router.get("/")
async def list_notifications(
    unread_only: bool = False,
    category: str | None = None,
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List notifications."""
    service = NotificationService(db)

    category_map = {
        "system": NotificationCategory.SYSTEM,
        "agent": NotificationCategory.AGENT,
        "message": NotificationCategory.MESSAGE,
        "alert": NotificationCategory.ALERT,
        "reminder": NotificationCategory.REMINDER,
    }

    notifications = await service.list_notifications(
        recipient_id=agent.id,
        unread_only=unread_only,
        category=category_map.get(category) if category else None,
        limit=limit,
    )

    return [
        {
            "id": str(n.id),
            "title": n.title,
            "body": n.body,
            "category": n.category.value,
            "priority": n.priority.value,
            "status": n.status.value,
            "data": n.data,
            "action_url": n.action_url,
            "created_at": n.created_at.isoformat(),
            "read_at": n.read_at.isoformat() if n.read_at else None,
        }
        for n in notifications
    ]


@router.get("/unread-count")
async def get_unread_count(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get unread notification count."""
    service = NotificationService(db)
    count = await service.get_unread_count(agent.id)
    return {"count": count}


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    from sqlalchemy import select
    from nexus.notifications.models import Notification

    # SECURITY: Verify ownership before marking as read
    result = await db.execute(
        select(Notification).where(Notification.id == UUID(notification_id))
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.recipient_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this notification")

    service = NotificationService(db)
    await service.mark_as_read(UUID(notification_id))
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_read(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    service = NotificationService(db)
    await service.mark_all_read(agent.id)
    return {"status": "all_read"}


@router.post("/devices")
async def register_device(
    request: RegisterDeviceRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Register a device for push notifications."""
    service = NotificationService(db)
    device = await service.register_device(
        owner_id=agent.id,
        device_token=request.device_token,
        device_type=request.device_type,
        push_provider=request.push_provider,
        device_name=request.device_name,
        app_version=request.app_version,
    )

    return {
        "id": str(device.id),
        "device_type": device.device_type,
        "push_provider": device.push_provider,
    }


@router.delete("/devices/{device_token}")
async def unregister_device(
    device_token: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Unregister a device."""
    from sqlalchemy import select
    from nexus.notifications.models import DeviceRegistration

    # SECURITY: Verify ownership before unregistering
    result = await db.execute(
        select(DeviceRegistration).where(DeviceRegistration.device_token == device_token)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to unregister this device")

    service = NotificationService(db)
    await service.unregister_device(device_token)
    return {"status": "unregistered"}


@router.post("/templates/send")
async def send_from_template(
    request: SendFromTemplateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send notification from a template."""
    service = NotificationService(db)

    channel_map = {
        "push": NotificationChannel.PUSH,
        "email": NotificationChannel.EMAIL,
        "sms": NotificationChannel.SMS,
        "in_app": NotificationChannel.IN_APP,
    }

    channels = None
    if request.channels:
        channels = [channel_map.get(c, NotificationChannel.IN_APP) for c in request.channels]

    notifications = await service.send_from_template(
        template_name=request.template_name,
        recipient_id=UUID(request.recipient_id),
        variables=request.variables,
        channels=channels,
        sender_id=agent.id,
    )

    return [
        {"id": str(n.id), "channel": n.channel.value, "status": n.status.value}
        for n in notifications
    ]


@router.put("/preferences")
async def update_preferences(
    request: UpdatePreferencesRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences."""
    from sqlalchemy import select
    from nexus.notifications.models import NotificationPreference

    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.owner_id == agent.id)
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        prefs = NotificationPreference(owner_id=agent.id)
        db.add(prefs)

    if request.push_enabled is not None:
        prefs.push_enabled = request.push_enabled
    if request.email_enabled is not None:
        prefs.email_enabled = request.email_enabled
    if request.sms_enabled is not None:
        prefs.sms_enabled = request.sms_enabled
    if request.in_app_enabled is not None:
        prefs.in_app_enabled = request.in_app_enabled
    if request.quiet_hours_enabled is not None:
        prefs.quiet_hours_enabled = request.quiet_hours_enabled
    if request.quiet_hours_start is not None:
        prefs.quiet_hours_start = request.quiet_hours_start
    if request.quiet_hours_end is not None:
        prefs.quiet_hours_end = request.quiet_hours_end
    if request.dnd_enabled is not None:
        prefs.dnd_enabled = request.dnd_enabled
    if request.dnd_until is not None:
        prefs.dnd_until = datetime.fromisoformat(request.dnd_until)

    await db.commit()
    return {"status": "updated"}
