"""Webhook management routes."""

from fastapi import APIRouter, Depends
from nexus.auth import get_current_agent
from nexus.identity.models import Agent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/pending")
async def get_pending_webhooks(agent: Agent = Depends(get_current_agent)):
    """Get count of pending webhook deliveries."""
    from nexus.webhooks.service import webhook_service
    return {
        "pending_count": webhook_service.get_pending_count(),
    }
