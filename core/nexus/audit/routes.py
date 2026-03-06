"""Audit log API routes."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.audit.models import AuditAction, AuditResource
from nexus.audit.service import AuditService

import json
import io

router = APIRouter(prefix="/audit", tags=["audit"])


# --- Schemas ---


class AuditLogResponse(BaseModel):
    """Audit log entry response."""
    id: UUID
    timestamp: datetime
    action: AuditAction
    resource_type: AuditResource
    resource_id: str | None
    success: bool
    error_message: str | None
    details: dict
    ip_address: str | None

    class Config:
        from_attributes = True


class ActivitySummary(BaseModel):
    """Activity summary response."""
    total_actions: int
    failures: int
    action_breakdown: dict[str, int]
    period_days: int


# --- Endpoints ---


@router.get("/logs", response_model=list[AuditLogResponse])
async def query_logs(
    action: AuditAction | None = None,
    resource_type: AuditResource | None = None,
    resource_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    success: bool | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=100000),  # SECURITY: Limit offset
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Query your audit logs.

    Filter by action type, resource, time range, or success status.
    """
    service = AuditService(session)
    logs = await service.query(
        agent_id=agent.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        start_time=start_time,
        end_time=end_time,
        success=success,
        limit=limit,
        offset=offset,
    )
    return logs


@router.get("/logs/{log_id}", response_model=AuditLogResponse)
async def get_log(
    log_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get a specific audit log entry."""
    service = AuditService(session)
    log = await service.get_by_id(log_id)
    if not log or log.agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Log not found")
    return log


@router.get("/resource/{resource_type}/{resource_id}", response_model=list[AuditLogResponse])
async def get_resource_history(
    resource_type: AuditResource,
    resource_id: str,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get full audit history of a specific resource."""
    service = AuditService(session)
    logs = await service.get_resource_history(resource_type, resource_id, limit)

    # Filter to only show logs for this agent's resources
    return [log for log in logs if log.agent_id == agent.id]


@router.get("/activity", response_model=ActivitySummary)
async def get_activity_summary(
    days: int = Query(default=7, le=90),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get activity summary for the specified period."""
    service = AuditService(session)
    return await service.get_agent_activity(agent.id, days)


@router.get("/export")
async def export_logs(
    start_time: datetime,
    end_time: datetime,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Export audit logs for compliance.

    Returns a downloadable JSON file.
    """
    service = AuditService(session)
    logs = await service.export_logs(agent.id, start_time, end_time)

    # Create JSON file
    content = json.dumps(logs, indent=2, default=str)
    buffer = io.BytesIO(content.encode())

    filename = f"audit_logs_{start_time.date()}_{end_time.date()}.json"

    return StreamingResponse(
        buffer,
        media_type="application/json",
        # SECURITY: Properly quote filename in Content-Disposition header
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/actions", response_model=list[str])
async def list_actions(
    agent: Agent = Depends(get_current_agent),  # SECURITY: Require authentication
):
    """List all available audit action types."""
    return [a.value for a in AuditAction]


@router.get("/resources", response_model=list[str])
async def list_resources(
    agent: Agent = Depends(get_current_agent),  # SECURITY: Require authentication
):
    """List all available resource types."""
    return [r.value for r in AuditResource]
