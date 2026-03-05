"""Health monitoring API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.health.service import HealthService
from nexus.health.models import HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    agent_id: str
    status: str
    last_heartbeat: str | None
    last_invocation_received: str | None
    last_invocation_completed: str | None
    avg_response_time_ms: float
    success_rate: float
    consecutive_failures: int
    uptime_percentage: float


class AlertResponse(BaseModel):
    id: str
    alert_type: str
    message: str
    acknowledged: bool
    created_at: str


class SystemHealthResponse(BaseModel):
    total_agents: int
    healthy: int
    degraded: int
    unhealthy: int
    unknown: int
    overall_health_percentage: float


async def get_health_service(db: AsyncSession = Depends(get_db)) -> HealthService:
    return HealthService(db)


@router.post("/heartbeat")
async def send_heartbeat(
    agent: Agent = Depends(get_current_agent),
    service: HealthService = Depends(get_health_service),
):
    """Send a heartbeat to indicate agent is alive."""
    health = await service.record_heartbeat(agent.id)
    return {"status": "ok", "health_status": health.status.value}


@router.get("/me", response_model=HealthResponse)
async def get_my_health(
    agent: Agent = Depends(get_current_agent),
    service: HealthService = Depends(get_health_service),
):
    """Get health status for current agent."""
    health = await service.get_health(agent.id)
    return _health_to_response(health)


@router.get("/agents/{agent_id}", response_model=HealthResponse)
async def get_agent_health(
    agent_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: HealthService = Depends(get_health_service),
):
    """Get health status for a specific agent."""
    # SECURITY: Only allow viewing own health status
    if agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this agent's health")
    health = await service.get_health(agent_id)
    return _health_to_response(health)


@router.get("/me/alerts", response_model=list[AlertResponse])
async def get_my_alerts(
    unacknowledged_only: bool = False,
    limit: int = 50,
    agent: Agent = Depends(get_current_agent),
    service: HealthService = Depends(get_health_service),
):
    """Get health alerts for current agent."""
    alerts = await service.get_alerts(
        agent.id,
        unacknowledged_only=unacknowledged_only,
        limit=limit,
    )
    return [
        AlertResponse(
            id=str(a.id),
            alert_type=a.alert_type,
            message=a.message,
            acknowledged=a.acknowledged,
            created_at=a.created_at.isoformat(),
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: HealthService = Depends(get_health_service),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a health alert."""
    from sqlalchemy import select
    from nexus.health.models import HealthAlert

    # SECURITY: Verify ownership before acknowledging
    result = await db.execute(
        select(HealthAlert).where(HealthAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to acknowledge this alert")

    alert = await service.acknowledge_alert(alert_id)
    return {"status": "acknowledged"}


@router.get("/me/history")
async def get_health_history(
    hours: int = 24,
    limit: int = 100,
    agent: Agent = Depends(get_current_agent),
    service: HealthService = Depends(get_health_service),
):
    """Get health check history for current agent."""
    return await service.get_health_history(agent.id, hours=hours, limit=limit)


@router.get("/system", response_model=SystemHealthResponse)
async def get_system_health(
    agent: Agent = Depends(get_current_agent),  # SECURITY: Require authentication
    service: HealthService = Depends(get_health_service),
):
    """Get overall system health summary."""
    return await service.get_system_health()


def _health_to_response(health) -> HealthResponse:
    return HealthResponse(
        agent_id=str(health.agent_id),
        status=health.status.value,
        last_heartbeat=health.last_heartbeat.isoformat() if health.last_heartbeat else None,
        last_invocation_received=health.last_invocation_received.isoformat() if health.last_invocation_received else None,
        last_invocation_completed=health.last_invocation_completed.isoformat() if health.last_invocation_completed else None,
        avg_response_time_ms=health.avg_response_time_ms,
        success_rate=health.success_rate,
        consecutive_failures=health.consecutive_failures,
        uptime_percentage=health.uptime_percentage,
    )
