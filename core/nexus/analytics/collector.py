"""Metrics collector middleware for tracking API usage."""

import time
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from nexus.analytics.models import MetricType


class MetricsCollector:
    """
    Collector for real-time metrics using Redis.

    Stores counters in Redis for fast increment operations,
    which are later aggregated to PostgreSQL by background jobs.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._local_buffer: dict[str, int] = {}  # Fallback if Redis unavailable

    async def _get_redis(self):
        """Lazy load Redis client."""
        if self._redis is None:
            try:
                from nexus.cache import get_cache
                self._redis = await get_cache()
            except Exception:
                pass
        return self._redis

    def _get_hour_key(self, agent_id: UUID, metric_type: MetricType, hour: datetime) -> str:
        """Generate Redis key for hourly counter."""
        hour_str = hour.strftime("%Y%m%d%H")
        return f"metrics:{agent_id}:{metric_type.value}:{hour_str}"

    def _get_endpoint_key(self, agent_id: UUID, endpoint: str, method: str, hour: datetime) -> str:
        """Generate Redis key for endpoint counter."""
        hour_str = hour.strftime("%Y%m%d%H")
        # Normalize endpoint path
        endpoint_norm = endpoint.replace("/", "_").strip("_")
        return f"endpoints:{agent_id}:{method}:{endpoint_norm}:{hour_str}"

    async def increment(
        self,
        agent_id: UUID,
        metric_type: MetricType,
        value: int = 1,
        dimensions: dict | None = None,
    ):
        """
        Increment a metric counter.

        Uses Redis for real-time counting, falls back to local buffer.
        """
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        key = self._get_hour_key(agent_id, metric_type, now)

        redis = await self._get_redis()
        if redis:
            try:
                await redis.incrby(key, value)
                # Set expiry for 48 hours (to allow for aggregation delay)
                await redis.expire(key, 48 * 3600)

                # Store dimensions if provided
                if dimensions:
                    dim_key = f"{key}:dims"
                    await redis.hset(dim_key, mapping={str(k): str(v) for k, v in dimensions.items()})
                    await redis.expire(dim_key, 48 * 3600)
            except Exception:
                # Fallback to local buffer
                self._local_buffer[key] = self._local_buffer.get(key, 0) + value
        else:
            self._local_buffer[key] = self._local_buffer.get(key, 0) + value

    async def record_latency(
        self,
        agent_id: UUID,
        endpoint: str,
        method: str,
        latency_ms: int,
        status_code: int,
    ):
        """
        Record API endpoint latency and status.

        Stores in Redis hash for later aggregation.
        """
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        key = self._get_endpoint_key(agent_id, endpoint, method, now)

        redis = await self._get_redis()
        if redis:
            try:
                # Use pipeline for atomic updates
                pipe = redis.pipeline()
                pipe.hincrby(key, "count", 1)
                pipe.hincrby(key, "total_latency", latency_ms)
                pipe.hincrby(key, f"status_{status_code}", 1)

                # Track min/max with Lua script or separate keys
                min_key = f"{key}:min"
                max_key = f"{key}:max"

                # Get current values
                current_min = await redis.get(min_key)
                current_max = await redis.get(max_key)

                if current_min is None or latency_ms < int(current_min):
                    pipe.set(min_key, latency_ms, ex=48 * 3600)
                if current_max is None or latency_ms > int(current_max):
                    pipe.set(max_key, latency_ms, ex=48 * 3600)

                pipe.expire(key, 48 * 3600)
                await pipe.execute()

                if status_code >= 400:
                    pipe = redis.pipeline()
                    pipe.hincrby(key, "errors", 1)
                    await pipe.execute()

            except Exception:
                pass

    async def get_current_count(
        self,
        agent_id: UUID,
        metric_type: MetricType,
    ) -> int:
        """Get current hour's count for a metric."""
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        key = self._get_hour_key(agent_id, metric_type, now)

        redis = await self._get_redis()
        if redis:
            try:
                value = await redis.get(key)
                return int(value) if value else 0
            except Exception:
                pass

        return self._local_buffer.get(key, 0)

    async def get_hourly_counts(
        self,
        agent_id: UUID,
        metric_type: MetricType,
        hours: int = 24,
    ) -> list[tuple[datetime, int]]:
        """Get counts for the last N hours."""
        results = []
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        redis = await self._get_redis()
        for i in range(hours):
            hour = now.replace(hour=(now.hour - i) % 24)
            if i >= now.hour:
                hour = hour.replace(day=hour.day - 1)

            key = self._get_hour_key(agent_id, metric_type, hour)

            count = 0
            if redis:
                try:
                    value = await redis.get(key)
                    count = int(value) if value else 0
                except Exception:
                    pass
            else:
                count = self._local_buffer.get(key, 0)

            results.append((hour, count))

        return results

    def flush_local_buffer(self) -> dict[str, int]:
        """Flush and return local buffer (for testing/debugging)."""
        buffer = self._local_buffer.copy()
        self._local_buffer.clear()
        return buffer


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic API metrics collection.

    Tracks request counts, latencies, and status codes per endpoint.
    """

    def __init__(self, app: ASGIApp, collector: MetricsCollector | None = None):
        super().__init__(app)
        self.collector = collector or MetricsCollector()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics for certain paths
        skip_paths = {"/metrics", "/health", "/docs", "/redoc", "/openapi.json"}
        if request.url.path in skip_paths:
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start_time) * 1000)

        # Try to get agent ID from request state (set by auth middleware)
        agent_id = getattr(request.state, "agent_id", None)
        if agent_id:
            # Record API request metric
            await self.collector.increment(
                agent_id=agent_id,
                metric_type=MetricType.API_REQUEST,
                dimensions={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "status_code": str(response.status_code),
                },
            )

            # Record endpoint-specific metrics
            await self.collector.record_latency(
                agent_id=agent_id,
                endpoint=request.url.path,
                method=request.method,
                latency_ms=latency_ms,
                status_code=response.status_code,
            )

        return response


# Global collector instance
metrics_collector = MetricsCollector()


async def track_metric(
    agent_id: UUID,
    metric_type: MetricType,
    value: int = 1,
    dimensions: dict | None = None,
):
    """Convenience function to track a metric."""
    await metrics_collector.increment(agent_id, metric_type, value, dimensions)
