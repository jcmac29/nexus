"""Background tasks for analytics aggregation."""

import asyncio
from datetime import datetime, timedelta, timezone, date
from uuid import UUID

from sqlalchemy import select, func, delete, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.analytics.models import (
    DailyMetric,
    EndpointMetric,
    HourlyMetric,
    MetricType,
    StorageUsage,
)
from nexus.database import async_session_maker


async def aggregate_hourly_metrics():
    """
    Roll up Redis counters to hourly PostgreSQL tables.

    Should run every hour via background scheduler.
    """
    from nexus.analytics.collector import metrics_collector
    from nexus.cache import get_cache

    redis = await get_cache()
    if not redis:
        return

    async with async_session_maker() as db:
        # Get all metric keys from Redis
        cursor = 0
        pattern = "metrics:*"

        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)

            for key in keys:
                # Skip dimension keys
                if key.endswith(":dims"):
                    continue

                try:
                    # Parse key: metrics:{agent_id}:{metric_type}:{hour}
                    parts = key.split(":")
                    if len(parts) != 4:
                        continue

                    _, agent_id_str, metric_type_str, hour_str = parts
                    agent_id = UUID(agent_id_str)
                    metric_type = MetricType(metric_type_str)
                    hour = datetime.strptime(hour_str, "%Y%m%d%H").replace(tzinfo=timezone.utc)

                    # Get count from Redis
                    count = await redis.get(key)
                    if not count:
                        continue
                    count = int(count)

                    # Get dimensions if available
                    dims_key = f"{key}:dims"
                    dimensions = await redis.hgetall(dims_key)

                    # Upsert into PostgreSQL
                    stmt = insert(HourlyMetric).values(
                        agent_id=agent_id,
                        metric_type=metric_type,
                        hour=hour,
                        count=count,
                        dimensions=dimensions or {},
                    ).on_conflict_do_update(
                        index_elements=["agent_id", "metric_type", "hour"],
                        set_={"count": count, "dimensions": dimensions or {}},
                    )
                    await db.execute(stmt)

                    # Delete from Redis after successful insert
                    await redis.delete(key, dims_key)

                except Exception as e:
                    print(f"Error processing key {key}: {e}")
                    continue

            if cursor == 0:
                break

        await db.commit()


async def aggregate_endpoint_metrics():
    """
    Roll up Redis endpoint counters to PostgreSQL.

    Should run every hour.
    """
    from nexus.cache import get_cache

    redis = await get_cache()
    if not redis:
        return

    async with async_session_maker() as db:
        cursor = 0
        pattern = "endpoints:*"

        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)

            for key in keys:
                # Skip min/max keys
                if key.endswith(":min") or key.endswith(":max"):
                    continue

                try:
                    # Parse key: endpoints:{agent_id}:{method}:{endpoint}:{hour}
                    parts = key.split(":")
                    if len(parts) != 5:
                        continue

                    _, agent_id_str, method, endpoint_norm, hour_str = parts
                    agent_id = UUID(agent_id_str)
                    endpoint = "/" + endpoint_norm.replace("_", "/")
                    hour = datetime.strptime(hour_str, "%Y%m%d%H").replace(tzinfo=timezone.utc)

                    # Get data from Redis hash
                    data = await redis.hgetall(key)
                    if not data:
                        continue

                    request_count = int(data.get("count", 0))
                    total_latency = int(data.get("total_latency", 0))
                    error_count = int(data.get("errors", 0))

                    # Get min/max
                    min_key = f"{key}:min"
                    max_key = f"{key}:max"
                    min_latency = await redis.get(min_key)
                    max_latency = await redis.get(max_key)

                    # Parse status codes
                    status_codes = {}
                    for k, v in data.items():
                        if k.startswith("status_"):
                            status_codes[k.replace("status_", "")] = int(v)

                    avg_latency = total_latency / request_count if request_count > 0 else None

                    # Upsert into PostgreSQL
                    stmt = insert(EndpointMetric).values(
                        agent_id=agent_id,
                        endpoint=endpoint,
                        method=method,
                        hour=hour,
                        request_count=request_count,
                        error_count=error_count,
                        total_latency_ms=total_latency,
                        min_latency_ms=int(min_latency) if min_latency else None,
                        max_latency_ms=int(max_latency) if max_latency else None,
                        avg_latency_ms=avg_latency,
                        status_codes=status_codes,
                    ).on_conflict_do_update(
                        index_elements=["agent_id", "endpoint", "method", "hour"],
                        set_={
                            "request_count": request_count,
                            "error_count": error_count,
                            "total_latency_ms": total_latency,
                            "avg_latency_ms": avg_latency,
                            "status_codes": status_codes,
                        },
                    )
                    await db.execute(stmt)

                    # Delete from Redis
                    await redis.delete(key, min_key, max_key)

                except Exception as e:
                    print(f"Error processing endpoint key {key}: {e}")
                    continue

            if cursor == 0:
                break

        await db.commit()


async def aggregate_daily_metrics():
    """
    Roll up hourly tables to daily summaries.

    Should run once per day (e.g., at 1 AM UTC).
    """
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    async with async_session_maker() as db:
        # Get all hourly metrics for yesterday
        start = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        stmt = select(
            HourlyMetric.agent_id,
            HourlyMetric.team_id,
            HourlyMetric.metric_type,
            func.sum(HourlyMetric.count).label("total_count"),
            func.sum(HourlyMetric.sum_value).label("total_sum"),
            func.min(HourlyMetric.min_value).label("min_val"),
            func.max(HourlyMetric.max_value).label("max_val"),
            func.avg(HourlyMetric.avg_value).label("avg_val"),
        ).where(
            and_(
                HourlyMetric.hour >= start,
                HourlyMetric.hour < end,
            )
        ).group_by(
            HourlyMetric.agent_id,
            HourlyMetric.team_id,
            HourlyMetric.metric_type,
        )

        result = await db.execute(stmt)

        for row in result.all():
            # Upsert daily metric
            insert_stmt = insert(DailyMetric).values(
                agent_id=row.agent_id,
                team_id=row.team_id,
                metric_type=row.metric_type,
                date=yesterday,
                count=row.total_count or 0,
                sum_value=row.total_sum,
                min_value=row.min_val,
                max_value=row.max_val,
                avg_value=row.avg_val,
            ).on_conflict_do_update(
                index_elements=["agent_id", "metric_type", "date"],
                set_={
                    "count": row.total_count or 0,
                    "sum_value": row.total_sum,
                    "min_value": row.min_val,
                    "max_value": row.max_val,
                    "avg_value": row.avg_val,
                },
            )
            await db.execute(insert_stmt)

        await db.commit()


async def snapshot_storage_usage():
    """
    Take daily snapshot of storage usage per agent.

    Should run once per day.
    """
    from nexus.memory.models import Memory
    from nexus.graph.models import MemoryRelationship
    from nexus.identity.models import Agent

    today = datetime.now(timezone.utc).date()

    async with async_session_maker() as db:
        # Get all agents
        agents_result = await db.execute(select(Agent.id))
        agent_ids = [row[0] for row in agents_result.all()]

        for agent_id in agent_ids:
            # Count memories
            memory_count_result = await db.execute(
                select(func.count()).select_from(Memory).where(Memory.agent_id == agent_id)
            )
            memory_count = memory_count_result.scalar() or 0

            # Estimate memory bytes (rough estimate based on JSONB size)
            # In production, you might want to use pg_column_size
            memory_bytes = memory_count * 1024  # Rough estimate

            # Count relationships
            rel_count_result = await db.execute(
                select(func.count()).select_from(MemoryRelationship).where(
                    MemoryRelationship.created_by_agent_id == agent_id
                )
            )
            relationship_count = rel_count_result.scalar() or 0

            # Upsert storage usage
            insert_stmt = insert(StorageUsage).values(
                agent_id=agent_id,
                date=today,
                memory_count=memory_count,
                memory_bytes=memory_bytes,
                relationship_count=relationship_count,
                peak_memory_count=memory_count,
                peak_memory_bytes=memory_bytes,
            ).on_conflict_do_update(
                index_elements=["agent_id", "date"],
                set_={
                    "memory_count": memory_count,
                    "memory_bytes": memory_bytes,
                    "relationship_count": relationship_count,
                },
            )
            await db.execute(insert_stmt)

        await db.commit()


async def cleanup_old_metrics(retention_days: int = 90):
    """
    Remove metrics older than retention period.

    Should run periodically (e.g., weekly).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_date = cutoff.date()

    async with async_session_maker() as db:
        # Clean hourly metrics (keep only 7 days)
        hourly_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        await db.execute(
            delete(HourlyMetric).where(HourlyMetric.hour < hourly_cutoff)
        )

        # Clean endpoint metrics (keep only 7 days)
        await db.execute(
            delete(EndpointMetric).where(EndpointMetric.hour < hourly_cutoff)
        )

        # Clean daily metrics (keep retention_days)
        await db.execute(
            delete(DailyMetric).where(DailyMetric.date < cutoff_date)
        )

        # Clean storage usage (keep retention_days)
        await db.execute(
            delete(StorageUsage).where(StorageUsage.date < cutoff_date)
        )

        await db.commit()


# Scheduler entry points
async def run_hourly_aggregation():
    """Run all hourly aggregation tasks."""
    await aggregate_hourly_metrics()
    await aggregate_endpoint_metrics()


async def run_daily_aggregation():
    """Run all daily aggregation tasks."""
    await aggregate_daily_metrics()
    await snapshot_storage_usage()


async def run_weekly_cleanup():
    """Run weekly cleanup tasks."""
    await cleanup_old_metrics()
