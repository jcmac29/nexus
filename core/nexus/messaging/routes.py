"""API routes for agent-to-agent messaging."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.discovery.models import Capability
from nexus.identity.models import Agent
from nexus.messaging.models import InvocationStatus
from nexus.messaging.schemas import (
    SendMessageRequest,
    MessageResponse,
    MessageListResponse,
    InvokeCapabilityRequest,
    InvocationResponse,
    InvocationListResponse,
    WebhookConfig,
    WebhookResponse,
    PendingInvocation,
    PendingWorkResponse,
    CompleteInvocationRequest,
)
from nexus.messaging.service import MessagingService

router = APIRouter(tags=["messaging"])


async def get_messaging_service(db: AsyncSession = Depends(get_db)) -> MessagingService:
    """Get messaging service instance."""
    return MessagingService(db)


# --- Messages ---

@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    data: SendMessageRequest,
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """Send a message to another agent."""
    try:
        message = await service.send_message(
            from_agent_id=agent.id,
            to_agent_id=data.to_agent_id,
            content=data.content,
            subject=data.subject,
            reply_to_id=data.reply_to_id,
        )
        return MessageResponse.model_validate(message)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/messages", response_model=MessageListResponse)
async def get_messages(
    inbox: bool = True,
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """Get messages for the current agent."""
    messages, total = await service.get_messages(
        agent_id=agent.id,
        inbox=inbox,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return MessageListResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        total=total,
    )


@router.post("/messages/{message_id}/read", response_model=MessageResponse)
async def mark_message_read(
    message_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """Mark a message as read."""
    message = await service.mark_message_read(message_id, agent.id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return MessageResponse.model_validate(message)


# --- Invocations ---

@router.post(
    "/invoke/{target_agent_id}/{capability_name}",
    response_model=InvocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invoke_capability(
    target_agent_id: UUID,
    capability_name: str,
    data: InvokeCapabilityRequest,
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Invoke a capability on another agent.

    The target agent will receive the invocation and can respond with a result.
    If the capability has an endpoint_url configured, it will be called directly.
    Otherwise, the invocation will be queued for the agent to poll.
    """
    try:
        invocation = await service.invoke_capability(
            caller_agent_id=agent.id,
            target_agent_id=target_agent_id,
            capability_name=capability_name,
            input_data=data.input,
            timeout_seconds=data.timeout_seconds,
            async_mode=data.async_mode,
        )

        # Get capability name for response
        from sqlalchemy import select
        cap_result = await db.execute(
            select(Capability).where(Capability.id == invocation.capability_id)
        )
        capability = cap_result.scalar_one_or_none()

        return InvocationResponse(
            id=invocation.id,
            caller_agent_id=invocation.caller_agent_id,
            target_agent_id=invocation.target_agent_id,
            capability_id=invocation.capability_id,
            capability_name=capability.name if capability else None,
            status=invocation.status.value,
            input_data=invocation.input_data,
            output_data=invocation.output_data,
            error_message=invocation.error_message,
            created_at=invocation.created_at,
            started_at=invocation.started_at,
            completed_at=invocation.completed_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/invocations/{invocation_id}", response_model=InvocationResponse)
async def get_invocation(
    invocation_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
    db: AsyncSession = Depends(get_db),
):
    """Get an invocation by ID."""
    invocation = await service.get_invocation(invocation_id)
    if not invocation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invocation not found")

    # Check if agent is caller or target
    if invocation.caller_agent_id != agent.id and invocation.target_agent_id != agent.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Get capability name
    from sqlalchemy import select
    cap_result = await db.execute(
        select(Capability).where(Capability.id == invocation.capability_id)
    )
    capability = cap_result.scalar_one_or_none()

    return InvocationResponse(
        id=invocation.id,
        caller_agent_id=invocation.caller_agent_id,
        target_agent_id=invocation.target_agent_id,
        capability_id=invocation.capability_id,
        capability_name=capability.name if capability else None,
        status=invocation.status.value,
        input_data=invocation.input_data,
        output_data=invocation.output_data,
        error_message=invocation.error_message,
        created_at=invocation.created_at,
        started_at=invocation.started_at,
        completed_at=invocation.completed_at,
    )


@router.get("/invocations", response_model=InvocationListResponse)
async def list_invocations(
    as_caller: bool = True,
    status: str | None = None,
    limit: int = 50,
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """List invocations for the current agent."""
    status_enum = None
    if status:
        try:
            status_enum = InvocationStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}",
            )

    invocations = await service.get_invocations(
        agent_id=agent.id,
        as_caller=as_caller,
        status=status_enum,
        limit=limit,
    )

    return InvocationListResponse(
        invocations=[
            InvocationResponse(
                id=inv.id,
                caller_agent_id=inv.caller_agent_id,
                target_agent_id=inv.target_agent_id,
                capability_id=inv.capability_id,
                status=inv.status.value,
                input_data=inv.input_data,
                output_data=inv.output_data,
                error_message=inv.error_message,
                created_at=inv.created_at,
                started_at=inv.started_at,
                completed_at=inv.completed_at,
            )
            for inv in invocations
        ],
        total=len(invocations),
    )


# --- Pending Work (for polling agents) ---

@router.get("/agents/me/pending", response_model=PendingWorkResponse)
async def get_pending_work(
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Get pending work for the current agent.

    This endpoint is for agents that poll for work instead of using webhooks.
    Returns pending invocations and unread messages.
    """
    # Get pending invocations
    invocations = await service.get_pending_invocations(agent.id)

    # Get capability names and caller names
    from sqlalchemy import select
    pending = []
    for inv in invocations:
        cap_result = await db.execute(
            select(Capability).where(Capability.id == inv.capability_id)
        )
        capability = cap_result.scalar_one_or_none()

        caller_result = await db.execute(
            select(Agent).where(Agent.id == inv.caller_agent_id)
        )
        caller = caller_result.scalar_one_or_none()

        pending.append(PendingInvocation(
            id=inv.id,
            caller_agent_id=inv.caller_agent_id,
            caller_agent_name=caller.name if caller else None,
            capability_name=capability.name if capability else "unknown",
            input_data=inv.input_data,
            created_at=inv.created_at,
            timeout_seconds=inv.timeout_seconds,
        ))

    # Get unread messages
    messages, _ = await service.get_messages(
        agent_id=agent.id,
        inbox=True,
        unread_only=True,
        limit=50,
    )

    return PendingWorkResponse(
        invocations=pending,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.post("/invocations/{invocation_id}/complete", response_model=InvocationResponse)
async def complete_invocation(
    invocation_id: UUID,
    data: CompleteInvocationRequest,
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """
    Complete an invocation with a result.

    For agents that poll for work, use this endpoint to submit the result.
    """
    invocation = await service.complete_invocation(
        invocation_id=invocation_id,
        agent_id=agent.id,
        output=data.output,
        error=data.error,
    )

    if not invocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invocation not found or not owned by this agent",
        )

    return InvocationResponse(
        id=invocation.id,
        caller_agent_id=invocation.caller_agent_id,
        target_agent_id=invocation.target_agent_id,
        capability_id=invocation.capability_id,
        status=invocation.status.value,
        input_data=invocation.input_data,
        output_data=invocation.output_data,
        error_message=invocation.error_message,
        created_at=invocation.created_at,
        started_at=invocation.started_at,
        completed_at=invocation.completed_at,
    )


# --- Webhook Configuration ---

@router.post("/agents/me/webhook", response_model=WebhookResponse)
async def set_webhook(
    data: WebhookConfig,
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """
    Configure webhook for receiving invocations and messages.

    When another agent invokes your capability or sends a message,
    Nexus will POST to your webhook URL.
    """
    await service.set_webhook(
        agent_id=agent.id,
        endpoint_url=data.endpoint_url,
        events=data.events,
    )

    return WebhookResponse(
        endpoint_url=data.endpoint_url,
        events=data.events,
        active=True,
    )


@router.get("/agents/me/webhook", response_model=WebhookResponse | None)
async def get_webhook(
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """Get current webhook configuration."""
    webhook = await service.get_webhook(agent.id)
    if not webhook:
        return None
    return WebhookResponse(**webhook)


@router.delete("/agents/me/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def remove_webhook(
    agent: Agent = Depends(get_current_agent),
    service: MessagingService = Depends(get_messaging_service),
):
    """Remove webhook configuration."""
    await service.remove_webhook(agent.id)
