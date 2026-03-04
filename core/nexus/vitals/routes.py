"""Vitals API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.vitals.schemas import (
    FindHealthyRequest,
    HeartbeatResponse,
    HealthyAgentResponse,
    SubscribeRequest,
    SubscriptionResponse,
    UpdateVitalsRequest,
    VitalsResponse,
    VitalsSnapshotResponse,
)
from nexus.vitals.service import VitalsService

router = APIRouter(prefix="/vitals", tags=["vitals"])


def _vitals_to_response(vitals) -> VitalsResponse:
    return VitalsResponse(
        agent_id=vitals.agent_id,
        status=vitals.status.value,
        status_message=vitals.status_message,
        is_online=vitals.is_online,
        is_busy=vitals.is_busy,
        current_load=vitals.current_load,
        max_concurrent_tasks=vitals.max_concurrent_tasks,
        current_tasks=vitals.current_tasks,
        avg_response_time_ms=vitals.avg_response_time_ms,
        p95_response_time_ms=vitals.p95_response_time_ms,
        p99_response_time_ms=vitals.p99_response_time_ms,
        error_rate=vitals.error_rate,
        uptime_percent=vitals.uptime_percent,
        queue_depth=vitals.queue_depth,
        estimated_wait_seconds=vitals.estimated_wait_seconds,
        capabilities_status=vitals.capabilities_status,
        last_heartbeat=vitals.last_heartbeat,
        agent_version=vitals.agent_version,
        updated_at=vitals.updated_at,
    )


@router.get("/me")
async def get_my_vitals(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> VitalsResponse:
    """Get my vitals."""
    service = VitalsService(db)
    vitals = await service.get_or_create_vitals(agent.id)
    return _vitals_to_response(vitals)


@router.patch("/me")
async def update_my_vitals(
    request: UpdateVitalsRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> VitalsResponse:
    """Update my vitals."""
    service = VitalsService(db)

    vitals = await service.update_vitals(
        agent_id=agent.id,
        is_online=request.is_online,
        is_busy=request.is_busy,
        current_load=request.current_load,
        max_concurrent_tasks=request.max_concurrent_tasks,
        current_tasks=request.current_tasks,
        queue_depth=request.queue_depth,
        estimated_wait_seconds=request.estimated_wait_seconds,
        capabilities_status=request.capabilities_status,
        agent_version=request.agent_version,
    )

    return _vitals_to_response(vitals)


@router.post("/heartbeat")
async def heartbeat(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatResponse:
    """Send heartbeat."""
    service = VitalsService(db)
    vitals = await service.heartbeat(agent.id)

    return HeartbeatResponse(
        agent_id=vitals.agent_id,
        status=vitals.status.value,
        last_heartbeat=vitals.last_heartbeat,
        missed_heartbeats=vitals.missed_heartbeats,
    )


@router.delete("/subscriptions/{subscription_id}")
async def unsubscribe(
    subscription_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unsubscribe from vitals."""
    service = VitalsService(db)
    await service.unsubscribe(subscription_id, agent.id)
    return {"status": "unsubscribed"}


@router.get("/subscriptions")
async def list_subscriptions(
    active_only: bool = True,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionResponse]:
    """List my subscriptions."""
    service = VitalsService(db)
    subscriptions = await service.get_subscriptions(agent.id, active_only)

    return [
        SubscriptionResponse(
            id=s.id,
            subscriber_id=s.subscriber_id,
            target_agent_id=s.target_agent_id,
            notify_on=s.notify_on or [],
            threshold_load=s.threshold_load,
            threshold_error_rate=s.threshold_error_rate,
            threshold_response_time_ms=s.threshold_response_time_ms,
            is_active=s.is_active,
            webhook_url=s.webhook_url,
            last_notified=s.last_notified,
            created_at=s.created_at,
        )
        for s in subscriptions
    ]


@router.post("/find-healthy")
async def find_healthy_agents(
    request: FindHealthyRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[HealthyAgentResponse]:
    """Find healthy agents matching criteria."""
    service = VitalsService(db)

    agents = await service.find_healthy(
        capability=request.capability,
        max_load=request.max_load,
        max_response_time_ms=request.max_response_time_ms,
        require_online=request.require_online,
        limit=request.limit,
    )

    return [
        HealthyAgentResponse(
            agent_id=a.agent_id,
            agent_name=None,  # Would join with agents table
            status=a.status.value,
            current_load=a.current_load,
            avg_response_time_ms=a.avg_response_time_ms,
            queue_depth=a.queue_depth,
            estimated_wait_seconds=a.estimated_wait_seconds,
            capabilities_status=a.capabilities_status,
        )
        for a in agents
    ]


@router.get("/best")
async def find_best_agent(
    capability: str | None = None,
    max_load: float = 0.8,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> HealthyAgentResponse | None:
    """Find the best healthy agent."""
    service = VitalsService(db)

    agents = await service.find_healthy(
        capability=capability,
        max_load=max_load,
        limit=1,
    )

    if not agents:
        return None

    a = agents[0]
    return HealthyAgentResponse(
        agent_id=a.agent_id,
        agent_name=None,
        status=a.status.value,
        current_load=a.current_load,
        avg_response_time_ms=a.avg_response_time_ms,
        queue_depth=a.queue_depth,
        estimated_wait_seconds=a.estimated_wait_seconds,
        capabilities_status=a.capabilities_status,
    )


# Routes with path parameters must come after specific routes
@router.get("/{agent_id}")
async def get_agent_vitals(
    agent_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> VitalsResponse:
    """Get vitals for an agent."""
    service = VitalsService(db)
    vitals = await service.get_vitals(agent_id)

    if not vitals:
        raise HTTPException(status_code=404, detail="Agent vitals not found")

    return _vitals_to_response(vitals)


@router.post("/{agent_id}/subscribe", status_code=201)
async def subscribe_to_vitals(
    agent_id: UUID,
    request: SubscribeRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    """Subscribe to an agent's vitals."""
    service = VitalsService(db)

    subscription = await service.subscribe(
        subscriber_id=agent.id,
        target_agent_id=agent_id,
        notify_on=request.notify_on,
        threshold_load=request.threshold_load,
        threshold_error_rate=request.threshold_error_rate,
        threshold_response_time_ms=request.threshold_response_time_ms,
        webhook_url=request.webhook_url,
    )

    return SubscriptionResponse(
        id=subscription.id,
        subscriber_id=subscription.subscriber_id,
        target_agent_id=subscription.target_agent_id,
        notify_on=subscription.notify_on or [],
        threshold_load=subscription.threshold_load,
        threshold_error_rate=subscription.threshold_error_rate,
        threshold_response_time_ms=subscription.threshold_response_time_ms,
        is_active=subscription.is_active,
        webhook_url=subscription.webhook_url,
        last_notified=subscription.last_notified,
        created_at=subscription.created_at,
    )


@router.post("/snapshot")
async def take_snapshot(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> VitalsSnapshotResponse:
    """Take a snapshot of current vitals."""
    service = VitalsService(db)

    try:
        snapshot = await service.take_snapshot(agent.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return VitalsSnapshotResponse(
        agent_id=snapshot.agent_id,
        status=snapshot.status.value,
        is_online=snapshot.is_online,
        current_load=snapshot.current_load,
        current_tasks=snapshot.current_tasks,
        avg_response_time_ms=snapshot.avg_response_time_ms,
        error_rate=snapshot.error_rate,
        queue_depth=snapshot.queue_depth,
        created_at=snapshot.created_at,
    )


@router.get("/{agent_id}/snapshots")
async def get_snapshots(
    agent_id: UUID,
    hours: int = Query(default=24, le=168),
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[VitalsSnapshotResponse]:
    """Get historical snapshots."""
    service = VitalsService(db)
    snapshots = await service.get_snapshots(agent_id, hours, limit)

    return [
        VitalsSnapshotResponse(
            agent_id=s.agent_id,
            status=s.status.value,
            is_online=s.is_online,
            current_load=s.current_load,
            current_tasks=s.current_tasks,
            avg_response_time_ms=s.avg_response_time_ms,
            error_rate=s.error_rate,
            queue_depth=s.queue_depth,
            created_at=s.created_at,
        )
        for s in snapshots
    ]
