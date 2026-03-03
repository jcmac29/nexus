"""Rate limiting API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.ratelimit.service import RateLimitService

router = APIRouter(prefix="/ratelimit", tags=["rate-limiting"])


class RateLimitConfigResponse(BaseModel):
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    invocations_per_minute: int
    invocations_per_hour: int
    burst_allowance: int


class UpdateRateLimitRequest(BaseModel):
    requests_per_minute: int | None = Field(None, ge=1, le=10000)
    requests_per_hour: int | None = Field(None, ge=1, le=100000)
    requests_per_day: int | None = Field(None, ge=1, le=1000000)
    invocations_per_minute: int | None = Field(None, ge=1, le=1000)
    invocations_per_hour: int | None = Field(None, ge=1, le=10000)
    burst_allowance: int | None = Field(None, ge=0, le=100)


class RateLimitUsageResponse(BaseModel):
    minute: dict
    hour: dict
    day: dict


async def get_ratelimit_service(db: AsyncSession = Depends(get_db)) -> RateLimitService:
    return RateLimitService(db)


@router.get("/config", response_model=RateLimitConfigResponse)
async def get_rate_limit_config(
    agent: Agent = Depends(get_current_agent),
    service: RateLimitService = Depends(get_ratelimit_service),
):
    """Get current rate limit configuration."""
    config = await service.get_config(agent.id)
    return RateLimitConfigResponse(
        requests_per_minute=config.requests_per_minute,
        requests_per_hour=config.requests_per_hour,
        requests_per_day=config.requests_per_day,
        invocations_per_minute=config.invocations_per_minute,
        invocations_per_hour=config.invocations_per_hour,
        burst_allowance=config.burst_allowance,
    )


@router.patch("/config", response_model=RateLimitConfigResponse)
async def update_rate_limit_config(
    data: UpdateRateLimitRequest,
    agent: Agent = Depends(get_current_agent),
    service: RateLimitService = Depends(get_ratelimit_service),
):
    """Update rate limit configuration."""
    config = await service.update_config(
        agent_id=agent.id,
        requests_per_minute=data.requests_per_minute,
        requests_per_hour=data.requests_per_hour,
        requests_per_day=data.requests_per_day,
        invocations_per_minute=data.invocations_per_minute,
        invocations_per_hour=data.invocations_per_hour,
        burst_allowance=data.burst_allowance,
    )
    return RateLimitConfigResponse(
        requests_per_minute=config.requests_per_minute,
        requests_per_hour=config.requests_per_hour,
        requests_per_day=config.requests_per_day,
        invocations_per_minute=config.invocations_per_minute,
        invocations_per_hour=config.invocations_per_hour,
        burst_allowance=config.burst_allowance,
    )


@router.get("/usage", response_model=RateLimitUsageResponse)
async def get_rate_limit_usage(
    agent: Agent = Depends(get_current_agent),
    service: RateLimitService = Depends(get_ratelimit_service),
):
    """Get current rate limit usage."""
    usage = await service.get_usage(agent.id)
    return RateLimitUsageResponse(**usage)
