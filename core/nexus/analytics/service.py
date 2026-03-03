"""Analytics service for tracking usage and generating insights."""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.messaging.models import Invocation, InvocationStatus, Message
from nexus.discovery.models import Capability
from nexus.identity.models import Agent


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
