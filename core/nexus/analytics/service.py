"""Analytics service for tracking usage and generating insights."""

import csv
import io
from datetime import datetime, timezone, timedelta, date
from uuid import UUID
from typing import Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.messaging.models import Invocation, InvocationStatus, Message
from nexus.discovery.models import Capability
from nexus.identity.models import Agent
from nexus.analytics.models import (
    DailyMetric,
    EndpointMetric,
    HourlyMetric,
    MetricType,
    StorageUsage,
)


class AnalyticsService:
    """Service for analytics and metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_agent_stats(self, agent_id: UUID) -> dict[str, Any]:
        """Get statistics for an agent."""
        # Invocations made
        invocations_made = await self.db.execute(
            select(func.count(Invocation.id)).where(
                Invocation.caller_agent_id == agent_id
            )
        )

        # Invocations received
        invocations_received = await self.db.execute(
            select(func.count(Invocation.id)).where(
                Invocation.target_agent_id == agent_id
            )
        )

        # Successful invocations
        successful = await self.db.execute(
            select(func.count(Invocation.id)).where(
                Invocation.target_agent_id == agent_id,
                Invocation.status == InvocationStatus.COMPLETED,
            )
        )

        # Messages sent
        messages_sent = await self.db.execute(
            select(func.count(Message.id)).where(
                Message.from_agent_id == agent_id
            )
        )

        # Messages received
        messages_received = await self.db.execute(
            select(func.count(Message.id)).where(
                Message.to_agent_id == agent_id
            )
        )

        # Capabilities
        capabilities = await self.db.execute(
            select(func.count(Capability.id)).where(
                Capability.agent_id == agent_id
            )
        )

        return {
            "invocations_made": invocations_made.scalar() or 0,
            "invocations_received": invocations_received.scalar() or 0,
            "successful_invocations": successful.scalar() or 0,
            "messages_sent": messages_sent.scalar() or 0,
            "messages_received": messages_received.scalar() or 0,
            "capabilities_registered": capabilities.scalar() or 0,
        }

    async def get_popular_capabilities(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get most invoked capabilities."""
        result = await self.db.execute(
            select(
                Capability.id,
                Capability.name,
                Capability.agent_id,
                func.count(Invocation.id).label("invocation_count"),
            )
            .join(Invocation, Invocation.capability_id == Capability.id)
            .group_by(Capability.id)
            .order_by(func.count(Invocation.id).desc())
            .limit(limit)
        )

        capabilities = []
        for row in result.all():
            # Get agent name
            agent_result = await self.db.execute(
                select(Agent.name).where(Agent.id == row.agent_id)
            )
            agent_name = agent_result.scalar()

            capabilities.append({
                "capability_id": str(row.id),
                "capability_name": row.name,
                "agent_id": str(row.agent_id),
                "agent_name": agent_name,
                "invocation_count": row.invocation_count,
            })

        return capabilities

    async def get_activity_timeline(
        self,
        agent_id: UUID | None = None,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Get activity timeline (invocations per day)."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            select(
                func.date_trunc('day', Invocation.created_at).label('date'),
                func.count(Invocation.id).label('count'),
            )
            .where(Invocation.created_at >= start_date)
            .group_by(func.date_trunc('day', Invocation.created_at))
            .order_by(func.date_trunc('day', Invocation.created_at))
        )

        if agent_id:
            query = query.where(
                (Invocation.caller_agent_id == agent_id) |
                (Invocation.target_agent_id == agent_id)
            )

        result = await self.db.execute(query)

        return [
            {"date": row.date.isoformat(), "count": row.count}
            for row in result.all()
        ]

    async def get_success_rate(
        self,
        agent_id: UUID | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get invocation success rate."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        base_query = select(func.count(Invocation.id)).where(
            Invocation.created_at >= start_date
        )

        if agent_id:
            base_query = base_query.where(Invocation.target_agent_id == agent_id)

        total = await self.db.execute(base_query)
        total_count = total.scalar() or 0

        completed_query = base_query.where(
            Invocation.status == InvocationStatus.COMPLETED
        )
        completed = await self.db.execute(completed_query)
        completed_count = completed.scalar() or 0

        failed_query = base_query.where(
            Invocation.status == InvocationStatus.FAILED
        )
        failed = await self.db.execute(failed_query)
        failed_count = failed.scalar() or 0

        timeout_query = base_query.where(
            Invocation.status == InvocationStatus.TIMEOUT
        )
        timeout = await self.db.execute(timeout_query)
        timeout_count = timeout.scalar() or 0

        success_rate = (completed_count / total_count * 100) if total_count > 0 else 0

        return {
            "total_invocations": total_count,
            "completed": completed_count,
            "failed": failed_count,
            "timeout": timeout_count,
            "success_rate": round(success_rate, 2),
            "period_days": days,
        }

    async def get_top_agents(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get most active agents."""
        # By invocations received
        result = await self.db.execute(
            select(
                Agent.id,
                Agent.name,
                Agent.slug,
                func.count(Invocation.id).label("invocation_count"),
            )
            .join(Invocation, Invocation.target_agent_id == Agent.id)
            .group_by(Agent.id)
            .order_by(func.count(Invocation.id).desc())
            .limit(limit)
        )

        return [
            {
                "agent_id": str(row.id),
                "name": row.name,
                "slug": row.slug,
                "invocation_count": row.invocation_count,
            }
            for row in result.all()
        ]

    async def get_response_times(
        self,
        agent_id: UUID | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get average response times."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            select(
                func.avg(
                    func.extract('epoch', Invocation.completed_at) -
                    func.extract('epoch', Invocation.created_at)
                ).label('avg_seconds'),
                func.min(
                    func.extract('epoch', Invocation.completed_at) -
                    func.extract('epoch', Invocation.created_at)
                ).label('min_seconds'),
                func.max(
                    func.extract('epoch', Invocation.completed_at) -
                    func.extract('epoch', Invocation.created_at)
                ).label('max_seconds'),
            )
            .where(
                Invocation.created_at >= start_date,
                Invocation.status == InvocationStatus.COMPLETED,
                Invocation.completed_at.isnot(None),
            )
        )

        if agent_id:
            query = query.where(Invocation.target_agent_id == agent_id)

        result = await self.db.execute(query)
        row = result.one()

        return {
            "avg_response_ms": round((row.avg_seconds or 0) * 1000, 2),
            "min_response_ms": round((row.min_seconds or 0) * 1000, 2),
            "max_response_ms": round((row.max_seconds or 0) * 1000, 2),
            "period_days": days,
        }

    # --- New Dashboard and Usage Methods ---

    async def get_dashboard_data(
        self,
        agent_id: UUID,
        team_id: UUID | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get dashboard summary data for an agent or team."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=days)
        prev_period_start = period_start - timedelta(days=days)

        # Current period metrics
        current_metrics = await self._get_period_metrics(
            agent_id, team_id, period_start, now
        )

        # Previous period metrics for comparison
        prev_metrics = await self._get_period_metrics(
            agent_id, team_id, prev_period_start, period_start
        )

        # Calculate change percentages
        def calc_change(current: int, previous: int) -> float | None:
            if previous == 0:
                return None
            return round((current - previous) / previous * 100, 2)

        # Get current storage
        storage = await self.get_storage_usage(agent_id, days=1)
        current_storage = storage.get("current", {})

        # Get top endpoints
        top_endpoints = await self.get_endpoint_metrics(agent_id, days=days, limit=5)

        # Get top capabilities (from existing method)
        top_caps = await self.get_popular_capabilities(limit=5)

        return {
            "total_api_requests": current_metrics.get("api_requests", 0),
            "total_memory_operations": current_metrics.get("memory_ops", 0),
            "total_capability_invocations": current_metrics.get("invocations", 0),
            "total_webhook_deliveries": current_metrics.get("webhooks", 0),
            "api_requests_change_percent": calc_change(
                current_metrics.get("api_requests", 0),
                prev_metrics.get("api_requests", 0),
            ),
            "memory_ops_change_percent": calc_change(
                current_metrics.get("memory_ops", 0),
                prev_metrics.get("memory_ops", 0),
            ),
            "invocations_change_percent": calc_change(
                current_metrics.get("invocations", 0),
                prev_metrics.get("invocations", 0),
            ),
            "memory_count": current_storage.get("memory_count", 0),
            "memory_bytes": current_storage.get("memory_bytes", 0),
            "relationship_count": current_storage.get("relationship_count", 0),
            "top_endpoints": top_endpoints.get("endpoints", [])[:5],
            "top_capabilities": top_caps[:5],
            "period_start": period_start.isoformat(),
            "period_end": now.isoformat(),
        }

    async def _get_period_metrics(
        self,
        agent_id: UUID,
        team_id: UUID | None,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        """Get aggregated metrics for a period."""
        conditions = [
            DailyMetric.agent_id == agent_id,
            DailyMetric.date >= start.date(),
            DailyMetric.date < end.date(),
        ]
        if team_id:
            conditions.append(DailyMetric.team_id == team_id)

        stmt = select(
            DailyMetric.metric_type,
            func.sum(DailyMetric.count).label("total"),
        ).where(and_(*conditions)).group_by(DailyMetric.metric_type)

        result = await self.db.execute(stmt)
        metrics = {row.metric_type.value: row.total or 0 for row in result.all()}

        return {
            "api_requests": metrics.get("api_request", 0),
            "memory_ops": (
                metrics.get("memory_store", 0) +
                metrics.get("memory_get", 0) +
                metrics.get("memory_search", 0) +
                metrics.get("memory_delete", 0)
            ),
            "invocations": metrics.get("capability_invoke", 0),
            "webhooks": metrics.get("webhook_delivery", 0),
        }

    async def get_usage_metrics(
        self,
        agent_id: UUID,
        metric_types: list[MetricType] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        granularity: str = "day",
    ) -> dict[str, Any]:
        """Get detailed usage metrics with timeline."""
        if not end_date:
            end_date = datetime.now(timezone.utc).date()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        if not metric_types:
            metric_types = list(MetricType)

        results = {}

        for metric_type in metric_types:
            if granularity == "hour":
                # Query hourly metrics
                stmt = select(
                    HourlyMetric.hour,
                    HourlyMetric.count,
                    HourlyMetric.sum_value,
                    HourlyMetric.avg_value,
                ).where(
                    and_(
                        HourlyMetric.agent_id == agent_id,
                        HourlyMetric.metric_type == metric_type,
                        HourlyMetric.hour >= datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc),
                        HourlyMetric.hour < datetime.combine(end_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc),
                    )
                ).order_by(HourlyMetric.hour)
            else:
                # Query daily metrics
                stmt = select(
                    DailyMetric.date,
                    DailyMetric.count,
                    DailyMetric.sum_value,
                    DailyMetric.avg_value,
                ).where(
                    and_(
                        DailyMetric.agent_id == agent_id,
                        DailyMetric.metric_type == metric_type,
                        DailyMetric.date >= start_date,
                        DailyMetric.date <= end_date,
                    )
                ).order_by(DailyMetric.date)

            result = await self.db.execute(stmt)
            rows = result.all()

            data_points = []
            total = 0
            for row in rows:
                timestamp = row[0] if granularity == "hour" else datetime.combine(row[0], datetime.min.time()).replace(tzinfo=timezone.utc)
                data_points.append({
                    "metric_type": metric_type.value,
                    "timestamp": timestamp.isoformat(),
                    "count": row.count or 0,
                    "sum_value": row.sum_value,
                    "avg_value": row.avg_value,
                })
                total += row.count or 0

            results[metric_type.value] = {
                "metric_type": metric_type.value,
                "data_points": data_points,
                "total": total,
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "granularity": granularity,
            }

        return {
            "metrics": results,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

    async def get_endpoint_metrics(
        self,
        agent_id: UUID,
        days: int = 7,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Get per-endpoint usage metrics."""
        start = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(
            EndpointMetric.endpoint,
            EndpointMetric.method,
            func.sum(EndpointMetric.request_count).label("total_requests"),
            func.sum(EndpointMetric.error_count).label("total_errors"),
            func.avg(EndpointMetric.avg_latency_ms).label("avg_latency"),
            func.min(EndpointMetric.min_latency_ms).label("min_latency"),
            func.max(EndpointMetric.max_latency_ms).label("max_latency"),
        ).where(
            and_(
                EndpointMetric.agent_id == agent_id,
                EndpointMetric.hour >= start,
            )
        ).group_by(
            EndpointMetric.endpoint,
            EndpointMetric.method,
        ).order_by(
            func.sum(EndpointMetric.request_count).desc()
        ).limit(limit)

        result = await self.db.execute(stmt)

        endpoints = []
        total_requests = 0
        for row in result.all():
            total_requests += row.total_requests or 0
            error_rate = (row.total_errors / row.total_requests * 100) if row.total_requests else 0
            endpoints.append({
                "endpoint": row.endpoint,
                "method": row.method,
                "request_count": row.total_requests or 0,
                "error_count": row.total_errors or 0,
                "error_rate": round(error_rate, 2),
                "avg_latency_ms": round(row.avg_latency, 2) if row.avg_latency else None,
                "min_latency_ms": row.min_latency,
                "max_latency_ms": row.max_latency,
                "status_codes": {},  # Would need aggregation of JSONB
            })

        return {
            "endpoints": endpoints,
            "total_requests": total_requests,
            "period_start": start.isoformat(),
            "period_end": datetime.now(timezone.utc).isoformat(),
        }

    async def get_storage_usage(
        self,
        agent_id: UUID,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get storage usage history."""
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)

        stmt = select(StorageUsage).where(
            and_(
                StorageUsage.agent_id == agent_id,
                StorageUsage.date >= start_date,
                StorageUsage.date <= end_date,
            )
        ).order_by(StorageUsage.date.desc())

        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())

        history = []
        current = None

        for row in rows:
            snapshot = {
                "date": row.date.isoformat(),
                "memory_count": row.memory_count,
                "memory_bytes": row.memory_bytes,
                "media_count": row.media_count,
                "media_bytes": row.media_bytes,
                "relationship_count": row.relationship_count,
                "total_bytes": row.memory_bytes + row.media_bytes,
            }
            history.append(snapshot)
            if current is None:
                current = snapshot

        if not current:
            current = {
                "date": end_date.isoformat(),
                "memory_count": 0,
                "memory_bytes": 0,
                "media_count": 0,
                "media_bytes": 0,
                "relationship_count": 0,
                "total_bytes": 0,
            }

        return {
            "current": current,
            "history": history,
            "period_days": days,
        }

    async def get_quota_usage(
        self,
        agent_id: UUID,
    ) -> dict[str, Any]:
        """Get current quota usage against plan limits."""
        from nexus.billing.models import Account, Usage
        from nexus.billing.plans import PLAN_LIMITS

        # Get agent's account and plan
        agent_result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        if not agent:
            return {}

        # Get plan limits (this would need account relationship)
        # For now, return usage without limits comparison
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (period_start + timedelta(days=32)).replace(day=1)

        # Get usage for current billing period
        usage_result = await self.db.execute(
            select(
                func.sum(DailyMetric.count).label("total"),
                DailyMetric.metric_type,
            ).where(
                and_(
                    DailyMetric.agent_id == agent_id,
                    DailyMetric.date >= period_start.date(),
                    DailyMetric.date < period_end.date(),
                )
            ).group_by(DailyMetric.metric_type)
        )
        usage_by_type = {row.metric_type.value: row.total or 0 for row in usage_result.all()}

        # Get storage
        storage = await self.get_storage_usage(agent_id, days=1)
        current_storage = storage.get("current", {})

        return {
            "api_requests_used": usage_by_type.get("api_request", 0),
            "memory_ops_used": (
                usage_by_type.get("memory_store", 0) +
                usage_by_type.get("memory_get", 0) +
                usage_by_type.get("memory_search", 0)
            ),
            "stored_memories": current_storage.get("memory_count", 0),
            "storage_bytes_used": current_storage.get("total_bytes", 0),
            "api_requests_limit": None,  # Would come from plan
            "memory_ops_limit": None,
            "stored_memories_limit": None,
            "storage_bytes_limit": None,
            "api_requests_percent": None,
            "memory_ops_percent": None,
            "stored_memories_percent": None,
            "storage_percent": None,
            "billing_period_start": period_start.isoformat(),
            "billing_period_end": period_end.isoformat(),
        }

    async def export_data(
        self,
        agent_id: UUID,
        start_date: date,
        end_date: date,
        metric_types: list[MetricType] | None = None,
        format: str = "json",
        include_dimensions: bool = False,
    ) -> dict[str, Any]:
        """Export analytics data in JSON or CSV format."""
        if not metric_types:
            metric_types = list(MetricType)

        # Query daily metrics
        stmt = select(DailyMetric).where(
            and_(
                DailyMetric.agent_id == agent_id,
                DailyMetric.metric_type.in_(metric_types),
                DailyMetric.date >= start_date,
                DailyMetric.date <= end_date,
            )
        ).order_by(DailyMetric.date, DailyMetric.metric_type)

        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())

        data = []
        for row in rows:
            item = {
                "date": row.date.isoformat(),
                "metric_type": row.metric_type.value,
                "count": row.count,
                "sum_value": row.sum_value,
                "avg_value": row.avg_value,
                "min_value": row.min_value,
                "max_value": row.max_value,
            }
            if include_dimensions:
                item["dimensions"] = row.dimensions
            data.append(item)

        if format == "csv":
            output = io.StringIO()
            if data:
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            csv_string = output.getvalue()
            return {
                "format": "csv",
                "data": csv_string,
                "row_count": len(data),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
            }

        return {
            "format": "json",
            "data": data,
            "row_count": len(data),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }
