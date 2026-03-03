"""Audit service - Log and query audit events."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.audit.models import AuditLog, AuditAction, AuditResource


class AuditService:
    """Service for audit logging."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        action: AuditAction,
        resource_type: AuditResource,
        agent_id: UUID | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        success: bool = True,
        error_message: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        session_id: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        # Sanitize details - remove sensitive fields
        if details:
            details = self._sanitize(details)
        if old_value:
            old_value = self._sanitize(old_value)
        if new_value:
            new_value = self._sanitize(new_value)

        log = AuditLog(
            agent_id=agent_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            old_value=old_value,
            new_value=new_value,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            session_id=session_id,
        )

        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def query(
        self,
        agent_id: UUID | None = None,
        action: AuditAction | None = None,
        resource_type: AuditResource | None = None,
        resource_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Query audit logs with filters."""
        query = select(AuditLog)

        conditions = []
        if agent_id:
            conditions.append(AuditLog.agent_id == agent_id)
        if action:
            conditions.append(AuditLog.action == action)
        if resource_type:
            conditions.append(AuditLog.resource_type == resource_type)
        if resource_id:
            conditions.append(AuditLog.resource_id == resource_id)
        if start_time:
            conditions.append(AuditLog.timestamp >= start_time)
        if end_time:
            conditions.append(AuditLog.timestamp <= end_time)
        if success is not None:
            conditions.append(AuditLog.success == success)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(AuditLog.timestamp)).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, log_id: UUID) -> AuditLog | None:
        """Get a specific audit log entry."""
        result = await self.session.execute(
            select(AuditLog).where(AuditLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_resource_history(
        self,
        resource_type: AuditResource,
        resource_id: str,
        limit: int = 50,
    ) -> list[AuditLog]:
        """Get full history of a specific resource."""
        result = await self.session.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.resource_type == resource_type,
                    AuditLog.resource_id == resource_id,
                )
            )
            .order_by(desc(AuditLog.timestamp))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_agent_activity(
        self,
        agent_id: UUID,
        days: int = 7,
    ) -> dict:
        """Get activity summary for an agent."""
        start_time = datetime.now(timezone.utc) - timedelta(days=days)

        logs = await self.query(
            agent_id=agent_id,
            start_time=start_time,
            limit=1000,
        )

        # Aggregate by action
        action_counts: dict[str, int] = {}
        for log in logs:
            action = log.action.value
            action_counts[action] = action_counts.get(action, 0) + 1

        # Count failures
        failures = sum(1 for log in logs if not log.success)

        return {
            "total_actions": len(logs),
            "failures": failures,
            "action_breakdown": action_counts,
            "period_days": days,
        }

    async def export_logs(
        self,
        agent_id: UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        """Export audit logs for compliance."""
        logs = await self.query(
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000,
        )

        return [
            {
                "id": str(log.id),
                "timestamp": log.timestamp.isoformat(),
                "action": log.action.value,
                "resource_type": log.resource_type.value,
                "resource_id": log.resource_id,
                "success": log.success,
                "error_message": log.error_message,
                "details": log.details,
                "ip_address": log.ip_address,
            }
            for log in logs
        ]

    def _sanitize(self, data: dict) -> dict:
        """Remove sensitive fields from audit data."""
        sensitive_fields = {
            "password", "secret", "token", "api_key", "access_token",
            "refresh_token", "private_key", "credential", "auth",
        }

        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(s in key_lower for s in sensitive_fields):
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = self._sanitize(value)
            else:
                result[key] = value

        return result
