"""Webhook management routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.events.models import EventType
from nexus.identity.models import Agent
from nexus.webhooks.models import DeliveryStatus
from nexus.webhooks.schemas import (
    DeliveryLogListResponse,
    DeliveryLogResponse,
    EventTypesResponse,
    TestWebhookResponse,
    WebhookCreate,
    WebhookListResponse,
    WebhookResponse,
    WebhookSecretResponse,
    WebhookUpdate,
)
from nexus.webhooks.service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def get_webhook_service(db: AsyncSession = Depends(get_db)) -> WebhookService:
    """Get webhook service instance."""
    return WebhookService(db)


@router.post(
    "",
    response_model=WebhookSecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    data: WebhookCreate,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """
    Create a new webhook endpoint.

    Returns the webhook with its secret. **The secret is only shown once.**
    Store it securely to verify webhook signatures.
    """
    try:
        endpoint, secret = await service.create_endpoint(
            agent_id=agent.id,
            name=data.name,
            url=str(data.url),
            event_types=data.event_types,
            description=data.description,
            retry_policy=data.retry_policy,
            max_retries=data.max_retries,
            timeout_seconds=data.timeout_seconds,
            custom_headers=data.custom_headers,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return WebhookSecretResponse(
        webhook=WebhookResponse.model_validate(endpoint),
        secret=secret,
    )


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100000),  # SECURITY: Limit offset
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """List all webhook endpoints for the current agent."""
    endpoints, total = await service.list_endpoints(
        agent_id=agent.id,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    return WebhookListResponse(
        webhooks=[WebhookResponse.model_validate(e) for e in endpoints],
        total=total,
    )


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """Get a webhook endpoint by ID."""
    endpoint = await service.get_endpoint(webhook_id, agent_id=agent.id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    return WebhookResponse.model_validate(endpoint)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: UUID,
    data: WebhookUpdate,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """Update a webhook endpoint."""
    updates = data.model_dump(exclude_unset=True)
    if "url" in updates and updates["url"]:
        updates["url"] = str(updates["url"])

    endpoint = await service.update_endpoint(webhook_id, agent.id, **updates)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    return WebhookResponse.model_validate(endpoint)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """Delete a webhook endpoint."""
    deleted = await service.delete_endpoint(webhook_id, agent.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )


@router.post("/{webhook_id}/test", response_model=TestWebhookResponse)
async def test_webhook(
    webhook_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """
    Send a test ping to a webhook endpoint.

    Sends a `webhook.test` event to verify the endpoint is reachable.
    """
    result = await service.test_webhook(webhook_id, agent.id)
    if result.get("error") == "Webhook not found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    return TestWebhookResponse(**result)


@router.post("/{webhook_id}/rotate-secret", response_model=WebhookSecretResponse)
async def rotate_webhook_secret(
    webhook_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """
    Rotate the webhook signing secret.

    Returns the new secret. **The secret is only shown once.**
    Update your webhook receiver with the new secret.
    """
    result = await service.rotate_secret(webhook_id, agent.id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    endpoint, secret = result
    return WebhookSecretResponse(
        webhook=WebhookResponse.model_validate(endpoint),
        secret=secret,
    )


@router.get("/{webhook_id}/deliveries", response_model=DeliveryLogListResponse)
async def list_delivery_logs(
    webhook_id: UUID,
    status_filter: DeliveryStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),  # SECURITY: Limit offset
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """List delivery logs for a webhook endpoint."""
    logs, total = await service.get_delivery_logs(
        endpoint_id=webhook_id,
        agent_id=agent.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    if total == 0:
        # Check if webhook exists
        endpoint = await service.get_endpoint(webhook_id, agent.id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook not found",
            )
    return DeliveryLogListResponse(
        logs=[DeliveryLogResponse.model_validate(log) for log in logs],
        total=total,
    )


@router.get("/deliveries/{delivery_id}", response_model=DeliveryLogResponse)
async def get_delivery_log(
    delivery_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """Get a specific delivery log entry."""
    log = await service.get_delivery_log(delivery_id, agent.id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery log not found",
        )
    return DeliveryLogResponse.model_validate(log)


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryLogResponse)
async def retry_delivery(
    delivery_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WebhookService = Depends(get_webhook_service),
):
    """
    Manually retry a failed webhook delivery.

    Resets the delivery status and triggers a new delivery attempt.
    """
    log = await service.retry_delivery(delivery_id, agent.id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery log not found",
        )
    return DeliveryLogResponse.model_validate(log)


@router.get("/event-types", response_model=EventTypesResponse)
async def list_event_types(
    agent: Agent = Depends(get_current_agent),
):
    """
    List all available event types.

    Use these values when configuring webhook subscriptions.
    Wildcards are supported (e.g., `memory.*` matches all memory events).
    """
    event_types = []
    for event in EventType:
        event_types.append({
            "type": event.value,
            "description": _get_event_description(event),
        })
    return EventTypesResponse(event_types=event_types)


def _get_event_description(event: EventType) -> str:
    """Get description for an event type."""
    descriptions = {
        EventType.AGENT_CONNECTED: "Agent connected to Nexus",
        EventType.AGENT_DISCONNECTED: "Agent disconnected from Nexus",
        EventType.AGENT_UPDATED: "Agent profile was updated",
        EventType.MEMORY_CREATED: "New memory was stored",
        EventType.MEMORY_UPDATED: "Existing memory was updated",
        EventType.MEMORY_DELETED: "Memory was deleted",
        EventType.MESSAGE_SENT: "Message was sent to another agent",
        EventType.MESSAGE_RECEIVED: "Message was received from another agent",
        EventType.INVOCATION_STARTED: "Capability invocation started",
        EventType.INVOCATION_COMPLETED: "Capability invocation completed successfully",
        EventType.INVOCATION_FAILED: "Capability invocation failed",
        EventType.CONVERSATION_CREATED: "New conversation thread created",
        EventType.CONVERSATION_MESSAGE: "Message added to conversation",
        EventType.CONVERSATION_CLOSED: "Conversation was closed",
        EventType.TOOL_EXECUTED: "Tool was executed",
        EventType.TOOL_FAILED: "Tool execution failed",
        EventType.TEAM_JOINED: "Agent joined a team",
        EventType.TEAM_LEFT: "Agent left a team",
        EventType.WORKFLOW_STARTED: "Workflow execution started",
        EventType.WORKFLOW_STEP_COMPLETED: "Workflow step completed",
        EventType.WORKFLOW_COMPLETED: "Workflow execution completed",
        EventType.SYSTEM_ALERT: "System alert notification",
        EventType.SYSTEM_MAINTENANCE: "System maintenance notification",
        EventType.CUSTOM: "Custom event type",
    }
    return descriptions.get(event, "No description available")


# Legacy endpoint for backward compatibility
@router.get("/pending")
async def get_pending_webhooks(agent: Agent = Depends(get_current_agent)):
    """Get count of pending webhook deliveries (deprecated)."""
    from nexus.webhooks.service import webhook_service
    return {
        "pending_count": webhook_service.get_pending_count(),
    }
