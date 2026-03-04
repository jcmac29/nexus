"""Vitals service for agent health and status."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.vitals.models import (
    AgentVitals,
    HealthStatus,
    VitalsSnapshot,
    VitalsSubscription,
)

if TYPE_CHECKING:
    pass


class VitalsService:
    """Service for managing agent vitals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Vitals ====================

    async def get_vitals(self, agent_id: UUID) -> AgentVitals | None:
        """Get vitals for an agent."""
        result = await self.db.execute(
            select(AgentVitals).where(AgentVitals.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_vitals(self, agent_id: UUID) -> AgentVitals:
        """Get or create vitals for an agent."""
        vitals = await self.get_vitals(agent_id)
        if not vitals:
            vitals = AgentVitals(agent_id=agent_id)
            self.db.add(vitals)
            await self.db.commit()
            await self.db.refresh(vitals)
        return vitals

    async def update_vitals(
        self,
        agent_id: UUID,
        is_online: bool | None = None,
        is_busy: bool | None = None,
        current_load: float | None = None,
        max_concurrent_tasks: int | None = None,
        current_tasks: int | None = None,
        queue_depth: int | None = None,
        estimated_wait_seconds: int | None = None,
        capabilities_status: dict | None = None,
        agent_version: str | None = None,
    ) -> AgentVitals:
        """Update agent vitals."""
        vitals = await self.get_or_create_vitals(agent_id)

        if is_online is not None:
            vitals.is_online = is_online
        if is_busy is not None:
            vitals.is_busy = is_busy
        if current_load is not None:
            vitals.current_load = current_load
        if max_concurrent_tasks is not None:
            vitals.max_concurrent_tasks = max_concurrent_tasks
        if current_tasks is not None:
            vitals.current_tasks = current_tasks
        if queue_depth is not None:
            vitals.queue_depth = queue_depth
        if estimated_wait_seconds is not None:
            vitals.estimated_wait_seconds = estimated_wait_seconds
        if capabilities_status is not None:
            vitals.capabilities_status = capabilities_status
        if agent_version is not None:
            vitals.agent_version = agent_version

        # Auto-calculate status
        vitals.status = self._calculate_status(vitals)

        await self.db.commit()
        await self.db.refresh(vitals)

        # Check subscriptions and notify
        await self._check_and_notify(vitals)

        return vitals

    def _calculate_status(self, vitals: AgentVitals) -> HealthStatus:
        """Calculate health status based on vitals."""
        if not vitals.is_online:
            return HealthStatus.OFFLINE

        # Check error rate
        if vitals.error_rate > 0.5:
            return HealthStatus.UNHEALTHY
        if vitals.error_rate > 0.2:
            return HealthStatus.DEGRADED

        # Check load
        if vitals.current_load > 0.95:
            return HealthStatus.DEGRADED

        # Check response time
        if vitals.avg_response_time_ms > 10000:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    async def heartbeat(self, agent_id: UUID) -> AgentVitals:
        """Record heartbeat from agent."""
        vitals = await self.get_or_create_vitals(agent_id)

        now = datetime.now(timezone.utc)
        vitals.last_heartbeat = now
        vitals.is_online = True
        vitals.missed_heartbeats = 0

        # Update status
        vitals.status = self._calculate_status(vitals)

        await self.db.commit()
        await self.db.refresh(vitals)

        return vitals

    async def record_response(
        self,
        agent_id: UUID,
        response_time_ms: int,
        success: bool,
    ) -> None:
        """Record a response metric."""
        vitals = await self.get_or_create_vitals(agent_id)

        # Update response time (exponential moving average)
        alpha = 0.2
        vitals.avg_response_time_ms = int(
            alpha * response_time_ms + (1 - alpha) * vitals.avg_response_time_ms
        )

        # Update error rate
        if not success:
            vitals.error_rate = min(1.0, vitals.error_rate + 0.1)
        else:
            vitals.error_rate = max(0.0, vitals.error_rate - 0.02)

        vitals.status = self._calculate_status(vitals)

        await self.db.commit()

    async def check_stale_agents(
        self,
        timeout_seconds: int = 120,
    ) -> list[AgentVitals]:
        """Find agents with missed heartbeats."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)

        result = await self.db.execute(
            select(AgentVitals).where(
                and_(
                    AgentVitals.is_online == True,
                    AgentVitals.last_heartbeat < cutoff,
                )
            )
        )
        stale = list(result.scalars().all())

        for vitals in stale:
            vitals.missed_heartbeats += 1
            if vitals.missed_heartbeats >= 3:
                vitals.is_online = False
                vitals.status = HealthStatus.OFFLINE
                vitals.last_downtime = datetime.now(timezone.utc)

        if stale:
            await self.db.commit()

        return stale

    # ==================== Subscriptions ====================

    async def subscribe(
        self,
        subscriber_id: UUID,
        target_agent_id: UUID,
        notify_on: list[str] | None = None,
        threshold_load: float | None = None,
        threshold_error_rate: float | None = None,
        threshold_response_time_ms: int | None = None,
        webhook_url: str | None = None,
    ) -> VitalsSubscription:
        """Subscribe to an agent's vitals."""
        subscription = VitalsSubscription(
            subscriber_id=subscriber_id,
            target_agent_id=target_agent_id,
            notify_on=notify_on or ["status_change", "offline"],
            threshold_load=threshold_load,
            threshold_error_rate=threshold_error_rate,
            threshold_response_time_ms=threshold_response_time_ms,
            webhook_url=webhook_url,
        )
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)

        return subscription

    async def unsubscribe(
        self,
        subscription_id: UUID,
        subscriber_id: UUID,
    ) -> None:
        """Unsubscribe from vitals."""
        result = await self.db.execute(
            select(VitalsSubscription).where(
                and_(
                    VitalsSubscription.id == subscription_id,
                    VitalsSubscription.subscriber_id == subscriber_id,
                )
            )
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.is_active = False
            await self.db.commit()

    async def get_subscriptions(
        self,
        subscriber_id: UUID,
        active_only: bool = True,
    ) -> list[VitalsSubscription]:
        """Get subscriptions for an agent."""
        query = select(VitalsSubscription).where(
            VitalsSubscription.subscriber_id == subscriber_id
        )
        if active_only:
            query = query.where(VitalsSubscription.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _check_and_notify(self, vitals: AgentVitals) -> None:
        """Check subscriptions and send notifications."""
        result = await self.db.execute(
            select(VitalsSubscription).where(
                and_(
                    VitalsSubscription.target_agent_id == vitals.agent_id,
                    VitalsSubscription.is_active == True,
                )
            )
        )
        subscriptions = list(result.scalars().all())

        for sub in subscriptions:
            should_notify = False
            reason = None

            # Check thresholds
            if sub.threshold_load and vitals.current_load > sub.threshold_load:
                should_notify = "load_high" in (sub.notify_on or [])
                reason = f"Load exceeded: {vitals.current_load:.2f}"

            if sub.threshold_error_rate and vitals.error_rate > sub.threshold_error_rate:
                should_notify = "error_spike" in (sub.notify_on or [])
                reason = f"Error rate: {vitals.error_rate:.2f}"

            if sub.threshold_response_time_ms and vitals.avg_response_time_ms > sub.threshold_response_time_ms:
                should_notify = True
                reason = f"Response time: {vitals.avg_response_time_ms}ms"

            # Check status changes
            if vitals.status == HealthStatus.OFFLINE and "offline" in (sub.notify_on or []):
                should_notify = True
                reason = "Agent went offline"

            if vitals.status == HealthStatus.DEGRADED and "degraded" in (sub.notify_on or []):
                should_notify = True
                reason = "Agent degraded"

            if should_notify and sub.webhook_url:
                # In a real system, send webhook notification
                sub.last_notified = datetime.now(timezone.utc)

    # ==================== Finding Healthy Agents ====================

    async def find_healthy(
        self,
        capability: str | None = None,
        max_load: float = 0.8,
        max_response_time_ms: int | None = None,
        require_online: bool = True,
        limit: int = 10,
    ) -> list[AgentVitals]:
        """Find healthy agents matching criteria."""
        query = select(AgentVitals).where(
            and_(
                AgentVitals.status.in_([HealthStatus.HEALTHY, HealthStatus.DEGRADED]),
                AgentVitals.current_load <= max_load,
            )
        )

        if require_online:
            query = query.where(AgentVitals.is_online == True)

        if max_response_time_ms:
            query = query.where(AgentVitals.avg_response_time_ms <= max_response_time_ms)

        # Order by load (prefer less loaded agents)
        query = query.order_by(
            AgentVitals.current_load,
            AgentVitals.avg_response_time_ms,
        ).limit(limit)

        result = await self.db.execute(query)
        agents = list(result.scalars().all())

        # Filter by capability if specified
        if capability:
            agents = [
                a for a in agents
                if a.capabilities_status and
                a.capabilities_status.get(capability) in ["available", "ready"]
            ]

        return agents

    # ==================== Snapshots ====================

    async def take_snapshot(self, agent_id: UUID) -> VitalsSnapshot:
        """Take a snapshot of current vitals."""
        vitals = await self.get_vitals(agent_id)
        if not vitals:
            raise ValueError("No vitals found for agent")

        snapshot = VitalsSnapshot(
            agent_id=agent_id,
            status=vitals.status,
            is_online=vitals.is_online,
            current_load=vitals.current_load,
            current_tasks=vitals.current_tasks,
            avg_response_time_ms=vitals.avg_response_time_ms,
            error_rate=vitals.error_rate,
            queue_depth=vitals.queue_depth,
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)

        return snapshot

    async def get_snapshots(
        self,
        agent_id: UUID,
        hours: int = 24,
        limit: int = 100,
    ) -> list[VitalsSnapshot]:
        """Get historical snapshots."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(VitalsSnapshot)
            .where(
                and_(
                    VitalsSnapshot.agent_id == agent_id,
                    VitalsSnapshot.created_at >= cutoff,
                )
            )
            .order_by(VitalsSnapshot.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
