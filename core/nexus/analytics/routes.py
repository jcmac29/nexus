"""Analytics API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def get_analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


@router.get("/me")
async def get_my_stats(
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get statistics for the current agent."""
    return await service.get_agent_stats(agent.id)


@router.get("/agents/{agent_id}")
async def get_agent_stats(
    agent_id: UUID,
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get statistics for a specific agent."""
    return await service.get_agent_stats(agent_id)


@router.get("/capabilities/popular")
async def get_popular_capabilities(
    limit: int = Query(10, ge=1, le=100),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get most invoked capabilities."""
    return await service.get_popular_capabilities(limit=limit)


@router.get("/activity")
async def get_activity_timeline(
    agent_id: UUID | None = None,
    days: int = Query(7, ge=1, le=90),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get activity timeline (invocations per day)."""
    return await service.get_activity_timeline(agent_id=agent_id, days=days)


@router.get("/success-rate")
async def get_success_rate(
    agent_id: UUID | None = None,
    days: int = Query(30, ge=1, le=90),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get invocation success rate."""
    return await service.get_success_rate(agent_id=agent_id, days=days)


@router.get("/agents/top")
async def get_top_agents(
    limit: int = Query(10, ge=1, le=100),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get most active agents."""
    return await service.get_top_agents(limit=limit)


@router.get("/response-times")
async def get_response_times(
    agent_id: UUID | None = None,
    days: int = Query(7, ge=1, le=90),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get average response times."""
    return await service.get_response_times(agent_id=agent_id, days=days)
