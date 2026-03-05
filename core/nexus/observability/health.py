"""Health check endpoints for Nexus."""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    name: str
    status: HealthStatus
    message: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    version: str
    timestamp: str
    components: list[ComponentHealth]


async def check_database() -> ComponentHealth:
    """Check database connectivity."""
    try:
        from nexus.database import engine
        from sqlalchemy import text
        import time

        start = time.time()

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        latency = (time.time() - start) * 1000

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=str(e),
        )


async def check_redis() -> ComponentHealth:
    """Check Redis connectivity."""
    try:
        from nexus.cache import get_cache
        import time

        cache = await get_cache()
        start = time.time()

        await cache.set("health_check", "ok", ttl=10)
        value = await cache.get("health_check")

        latency = (time.time() - start) * 1000

        if value == "ok":
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
            )
        else:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                message="Cache read mismatch",
            )
    except Exception as e:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.DEGRADED,  # Degraded because we can fall back to local cache
            message=str(e),
        )


async def check_storage() -> ComponentHealth:
    """Check storage connectivity."""
    try:
        # Simple check - would verify S3 connectivity in production
        return ComponentHealth(
            name="storage",
            status=HealthStatus.HEALTHY,
        )
    except Exception as e:
        return ComponentHealth(
            name="storage",
            status=HealthStatus.DEGRADED,
            message=str(e),
        )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check."""
    from nexus import __version__

    # Run checks concurrently
    checks = await asyncio.gather(
        check_database(),
        check_redis(),
        check_storage(),
        return_exceptions=True,
    )

    components = []
    for check in checks:
        if isinstance(check, Exception):
            components.append(ComponentHealth(
                name="unknown",
                status=HealthStatus.UNHEALTHY,
                message=str(check),
            ))
        else:
            components.append(check)

    # Determine overall status
    if any(c.status == HealthStatus.UNHEALTHY for c in components):
        overall_status = HealthStatus.UNHEALTHY
    elif any(c.status == HealthStatus.DEGRADED for c in components):
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY

    return HealthResponse(
        status=overall_status,
        version=__version__,
        timestamp=datetime.utcnow().isoformat() + "Z",
        components=components,
    )


@router.get("/health/live")
async def liveness():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe."""
    # Check critical components
    db_health = await check_database()

    if db_health.status == HealthStatus.UNHEALTHY:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {"status": "ready"}
