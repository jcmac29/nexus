"""Health monitoring service."""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.health.models import AgentHealth, HealthCheck, HealthAlert, HealthStatus
from nexus.messaging.models import Invocation, InvocationStatus


class HealthService:
    """Service for monitoring agent health."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health(self, agent_id: UUID) -> AgentHealth:
        """Get health status for an agent, creating if needed."""
        result = await self.db.execute(
            select(AgentHealth).where(AgentHealth.agent_id == agent_id)
        )
        health = result.scalar_one_or_none()

        if not health:
            health = AgentHealth(agent_id=agent_id)
            self.db.add(health)
            await self.db.flush()

        return health

    async def record_heartbeat(self, agent_id: UUID) -> AgentHealth:
        """Record a heartbeat from an agent."""
        health = await self.get_health(agent_id)
        health.last_heartbeat = datetime.now(timezone.utc)
        health.updated_at = datetime.now(timezone.utc)

        # Record check
        check = HealthCheck(
            agent_id=agent_id,
            check_type="heartbeat",
            status=HealthStatus.HEALTHY,
        )
        self.db.add(check)

        # Update status based on recent activity
        await self._update_status(health)

        return health

    async def record_invocation_result(
        self,
        agent_id: UUID,
        success: bool,
        response_time_ms: float | None = None,
        error_message: str | None = None,
    ) -> AgentHealth:
        """Record an invocation result for health tracking."""
        health = await self.get_health(agent_id)
        now = datetime.now(timezone.utc)

        health.last_invocation_received = now
        if success:
            health.last_invocation_completed = now
            health.consecutive_failures = 0
        else:
            health.consecutive_failures += 1
            health.total_failures_24h += 1

        # Update rolling average response time
        if response_time_ms is not None:
            if health.avg_response_time_ms == 0:
                health.avg_response_time_ms = response_time_ms
            else:
                # Exponential moving average
                alpha = 0.1
                health.avg_response_time_ms = (
                    alpha * response_time_ms + (1 - alpha) * health.avg_response_time_ms
                )

        # Record check
        check = HealthCheck(
            agent_id=agent_id,
            check_type="invocation",
            status=HealthStatus.HEALTHY if success else HealthStatus.UNHEALTHY,
            response_time_ms=response_time_ms,
            error_message=error_message,
        )
        self.db.add(check)

        # Update overall status
        await self._update_status(health)

        return health

    async def _update_status(self, health: AgentHealth) -> None:
        """Update overall health status based on metrics."""
        old_status = health.status
        now = datetime.now(timezone.utc)

        # Calculate success rate from recent invocations
        day_ago = now - timedelta(days=1)
        result = await self.db.execute(
            select(
                func.count(Invocation.id).label("total"),
                func.count(Invocation.id).filter(
                    Invocation.status == InvocationStatus.COMPLETED
                ).label("completed"),
            ).where(
                Invocation.target_agent_id == health.agent_id,
                Invocation.created_at >= day_ago,
            )
        )
        row = result.one()
        if row.total > 0:
            health.success_rate = (row.completed / row.total) * 100

        # Determine status
        if health.consecutive_failures >= 5:
            health.status = HealthStatus.UNHEALTHY
        elif health.consecutive_failures >= 2 or health.success_rate < 90:
            health.status = HealthStatus.DEGRADED
        elif health.last_heartbeat:
            # Check if heartbeat is recent (within 5 minutes)
            if (now - health.last_heartbeat).total_seconds() < 300:
                health.status = HealthStatus.HEALTHY
            elif (now - health.last_heartbeat).total_seconds() < 900:
                health.status = HealthStatus.DEGRADED
            else:
                health.status = HealthStatus.UNHEALTHY
        else:
            health.status = HealthStatus.UNKNOWN

        health.updated_at = now

        # Create alert if status changed
        if old_status != health.status:
            await self._create_alert(health, old_status)

    async def _create_alert(self, health: AgentHealth, old_status: HealthStatus) -> None:
        """Create an alert for status change."""
        if health.status == HealthStatus.UNHEALTHY:
            alert_type = "unhealthy"
            message = f"Agent became unhealthy. Consecutive failures: {health.consecutive_failures}"
        elif health.status == HealthStatus.DEGRADED:
            alert_type = "degraded"
            message = f"Agent health degraded. Success rate: {health.success_rate:.1f}%"
        elif health.status == HealthStatus.HEALTHY and old_status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]:
            alert_type = "recovered"
            message = "Agent recovered to healthy status"
        else:
            return

        alert = HealthAlert(
            agent_id=health.agent_id,
            alert_type=alert_type,
            message=message,
        )
        self.db.add(alert)

    async def get_alerts(
        self,
        agent_id: UUID,
        unacknowledged_only: bool = False,
        limit: int = 50,
    ) -> list[HealthAlert]:
        """Get health alerts for an agent."""
        query = select(HealthAlert).where(HealthAlert.agent_id == agent_id)
        if unacknowledged_only:
            query = query.where(HealthAlert.acknowledged == False)
        query = query.order_by(HealthAlert.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def acknowledge_alert(self, alert_id: UUID) -> HealthAlert | None:
        """Acknowledge a health alert."""
        result = await self.db.execute(
            select(HealthAlert).where(HealthAlert.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if alert:
            alert.acknowledged = True
            alert.acknowledged_at = datetime.now(timezone.utc)
        return alert

    async def get_health_history(
        self,
        agent_id: UUID,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get health check history."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(HealthCheck)
            .where(
                HealthCheck.agent_id == agent_id,
                HealthCheck.created_at >= since,
            )
            .order_by(HealthCheck.created_at.desc())
            .limit(limit)
        )
        checks = result.scalars().all()
        return [
            {
                "id": str(c.id),
                "check_type": c.check_type,
                "status": c.status.value,
                "response_time_ms": c.response_time_ms,
                "error_message": c.error_message,
                "created_at": c.created_at.isoformat(),
            }
            for c in checks
        ]

    async def get_system_health(self) -> dict[str, Any]:
        """Get overall system health summary."""
        result = await self.db.execute(
            select(
                AgentHealth.status,
                func.count(AgentHealth.id).label("count"),
            ).group_by(AgentHealth.status)
        )

        status_counts = {status.value: 0 for status in HealthStatus}
        for row in result.all():
            status_counts[row.status.value] = row.count

        total = sum(status_counts.values())
        healthy_pct = (status_counts["healthy"] / total * 100) if total > 0 else 0

        return {
            "total_agents": total,
            "healthy": status_counts["healthy"],
            "degraded": status_counts["degraded"],
            "unhealthy": status_counts["unhealthy"],
            "unknown": status_counts["unknown"],
            "overall_health_percentage": round(healthy_pct, 2),
        }

    async def reset_daily_counters(self) -> int:
        """Reset 24h failure counters (call daily)."""
        result = await self.db.execute(select(AgentHealth))
        healths = result.scalars().all()
        count = 0
        for health in healths:
            if health.total_failures_24h > 0:
                health.total_failures_24h = 0
                count += 1
        return count
