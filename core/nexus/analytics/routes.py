"""Analytics API routes."""

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.analytics.models import MetricType
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


# --- New Dashboard and Usage Endpoints ---


@router.get("/dashboard")
async def get_dashboard(
    days: int = Query(7, ge=1, le=90),
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get dashboard summary data.

    Includes totals, comparisons with previous period, and top items.
    """
    return await service.get_dashboard_data(agent.id, days=days)


@router.get("/usage")
async def get_usage_metrics(
    metric_types: list[MetricType] | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    granularity: str = Query(default="day", pattern="^(hour|day)$"),
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get detailed usage metrics with timeline.

    - **metric_types**: Filter by specific metric types (default: all)
    - **granularity**: "hour" or "day" aggregation level
    """
    return await service.get_usage_metrics(
        agent_id=agent.id,
        metric_types=metric_types,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )


@router.get("/usage/timeline")
async def get_usage_timeline(
    metric_type: MetricType = Query(...),
    days: int = Query(30, ge=1, le=90),
    granularity: str = Query(default="day", pattern="^(hour|day)$"),
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get usage timeline for a specific metric type."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    result = await service.get_usage_metrics(
        agent_id=agent.id,
        metric_types=[metric_type],
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )
    return result.get("metrics", {}).get(metric_type.value, {})


@router.get("/endpoints")
async def get_endpoint_metrics(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get per-endpoint usage breakdown.

    Shows request counts, error rates, and latency stats by endpoint.
    """
    return await service.get_endpoint_metrics(agent.id, days=days, limit=limit)


@router.get("/storage")
async def get_storage_usage(
    days: int = Query(30, ge=1, le=365),
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get storage usage trends.

    Shows memory and media storage over time.
    """
    return await service.get_storage_usage(agent.id, days=days)


@router.get("/quota")
async def get_quota_usage(
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get current quota usage against plan limits.

    Shows usage for the current billing period.
    """
    return await service.get_quota_usage(agent.id)


@router.get("/team/{team_id}")
async def get_team_analytics(
    team_id: UUID,
    days: int = Query(7, ge=1, le=90),
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get aggregated analytics for a team."""
    return await service.get_dashboard_data(agent.id, team_id=team_id, days=days)


@router.get("/export")
async def export_analytics(
    start_date: date = Query(...),
    end_date: date = Query(...),
    metric_types: list[MetricType] | None = Query(default=None),
    format: str = Query(default="json", pattern="^(json|csv)$"),
    include_dimensions: bool = Query(default=False),
    agent: Agent = Depends(get_current_agent),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Export analytics data.

    - **format**: "json" or "csv"
    - **include_dimensions**: Include dimensional breakdown in export
    """
    result = await service.export_data(
        agent_id=agent.id,
        start_date=start_date,
        end_date=end_date,
        metric_types=metric_types,
        format=format,
        include_dimensions=include_dimensions,
    )

    if format == "csv":
        return PlainTextResponse(
            content=result["data"],
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=analytics_{start_date}_{end_date}.csv"
            },
        )

    return result
