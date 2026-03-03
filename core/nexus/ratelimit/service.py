"""Rate limiting service."""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import NamedTuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.ratelimit.models import RateLimitConfig, RateLimitCounter


class RateLimitResult(NamedTuple):
    """Result of a rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: int | None  # seconds until can retry


class RateLimitService:
    """Service for managing rate limits."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_config(self, agent_id: UUID) -> RateLimitConfig:
        """Get rate limit config for an agent, creating default if needed."""
        result = await self.db.execute(
            select(RateLimitConfig).where(RateLimitConfig.agent_id == agent_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            config = RateLimitConfig(agent_id=agent_id)
            self.db.add(config)
            await self.db.flush()

        return config

    async def update_config(
        self,
        agent_id: UUID,
        requests_per_minute: int | None = None,
        requests_per_hour: int | None = None,
        requests_per_day: int | None = None,
        invocations_per_minute: int | None = None,
        invocations_per_hour: int | None = None,
        burst_allowance: int | None = None,
    ) -> RateLimitConfig:
        """Update rate limit config."""
        config = await self.get_config(agent_id)

        if requests_per_minute is not None:
            config.requests_per_minute = requests_per_minute
        if requests_per_hour is not None:
            config.requests_per_hour = requests_per_hour
        if requests_per_day is not None:
            config.requests_per_day = requests_per_day
        if invocations_per_minute is not None:
            config.invocations_per_minute = invocations_per_minute
        if invocations_per_hour is not None:
            config.invocations_per_hour = invocations_per_hour
        if burst_allowance is not None:
            config.burst_allowance = burst_allowance

        config.updated_at = datetime.now(timezone.utc)
        return config

    def _get_window_start(self, window_type: str, now: datetime) -> datetime:
        """Get the start of a time window."""
        if window_type == "minute":
            return now.replace(second=0, microsecond=0)
        elif window_type == "hour":
            return now.replace(minute=0, second=0, microsecond=0)
        elif window_type == "day":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        raise ValueError(f"Unknown window type: {window_type}")

    def _get_window_end(self, window_type: str, window_start: datetime) -> datetime:
        """Get the end of a time window."""
        if window_type == "minute":
            return window_start + timedelta(minutes=1)
        elif window_type == "hour":
            return window_start + timedelta(hours=1)
        elif window_type == "day":
            return window_start + timedelta(days=1)
        raise ValueError(f"Unknown window type: {window_type}")

    async def _get_or_create_counter(
        self,
        agent_id: UUID,
        window_type: str,
        window_start: datetime,
    ) -> RateLimitCounter:
        """Get or create a counter for an agent and time window."""
        result = await self.db.execute(
            select(RateLimitCounter).where(
                and_(
                    RateLimitCounter.agent_id == agent_id,
                    RateLimitCounter.window_type == window_type,
                    RateLimitCounter.window_start == window_start,
                )
            )
        )
        counter = result.scalar_one_or_none()

        if not counter:
            counter = RateLimitCounter(
                agent_id=agent_id,
                window_type=window_type,
                window_start=window_start,
            )
            self.db.add(counter)
            await self.db.flush()

        return counter

    async def check_rate_limit(
        self,
        agent_id: UUID,
        is_invocation: bool = False,
    ) -> RateLimitResult:
        """Check if a request is within rate limits."""
        config = await self.get_config(agent_id)
        now = datetime.now(timezone.utc)

        # Check all windows
        windows = [
            ("minute", config.requests_per_minute, config.invocations_per_minute),
            ("hour", config.requests_per_hour, config.invocations_per_hour),
            ("day", config.requests_per_day, None),
        ]

        for window_type, request_limit, invocation_limit in windows:
            window_start = self._get_window_start(window_type, now)
            counter = await self._get_or_create_counter(agent_id, window_type, window_start)

            # Check request limit
            effective_limit = request_limit + config.burst_allowance
            if counter.request_count >= effective_limit:
                window_end = self._get_window_end(window_type, window_start)
                retry_after = int((window_end - now).total_seconds())
                return RateLimitResult(
                    allowed=False,
                    limit=request_limit,
                    remaining=0,
                    reset_at=window_end,
                    retry_after=max(1, retry_after),
                )

            # Check invocation limit if applicable
            if is_invocation and invocation_limit:
                effective_inv_limit = invocation_limit + config.burst_allowance
                if counter.invocation_count >= effective_inv_limit:
                    window_end = self._get_window_end(window_type, window_start)
                    retry_after = int((window_end - now).total_seconds())
                    return RateLimitResult(
                        allowed=False,
                        limit=invocation_limit,
                        remaining=0,
                        reset_at=window_end,
                        retry_after=max(1, retry_after),
                    )

        # All checks passed - return info for the minute window
        minute_start = self._get_window_start("minute", now)
        minute_counter = await self._get_or_create_counter(agent_id, "minute", minute_start)
        minute_end = self._get_window_end("minute", minute_start)

        return RateLimitResult(
            allowed=True,
            limit=config.requests_per_minute,
            remaining=max(0, config.requests_per_minute - minute_counter.request_count - 1),
            reset_at=minute_end,
            retry_after=None,
        )

    async def record_request(
        self,
        agent_id: UUID,
        is_invocation: bool = False,
    ) -> None:
        """Record a request against rate limits."""
        now = datetime.now(timezone.utc)

        for window_type in ["minute", "hour", "day"]:
            window_start = self._get_window_start(window_type, now)
            counter = await self._get_or_create_counter(agent_id, window_type, window_start)
            counter.request_count += 1
            if is_invocation:
                counter.invocation_count += 1

    async def get_usage(self, agent_id: UUID) -> dict:
        """Get current rate limit usage."""
        config = await self.get_config(agent_id)
        now = datetime.now(timezone.utc)

        usage = {}
        for window_type in ["minute", "hour", "day"]:
            window_start = self._get_window_start(window_type, now)
            counter = await self._get_or_create_counter(agent_id, window_type, window_start)

            limit_key = f"requests_per_{window_type}"
            limit = getattr(config, limit_key)

            usage[window_type] = {
                "requests": counter.request_count,
                "limit": limit,
                "remaining": max(0, limit - counter.request_count),
                "invocations": counter.invocation_count,
            }

        return usage

    async def cleanup_old_counters(self, older_than_days: int = 7) -> int:
        """Clean up old counter records."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        result = await self.db.execute(
            select(RateLimitCounter).where(RateLimitCounter.window_start < cutoff)
        )
        counters = result.scalars().all()
        count = len(counters)
        for counter in counters:
            await self.db.delete(counter)
        return count
