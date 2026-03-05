"""Tracing API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.tracing.service import TracingService

router = APIRouter(prefix="/tracing", tags=["tracing"])


class StartTraceRequest(BaseModel):
    name: str
    trace_id: str | None = None
    root_service: str | None = None
    context: dict | None = None
    tags: dict | None = None


class StartSpanRequest(BaseModel):
    name: str
    parent_span_id: str | None = None
    span_id: str | None = None
    kind: str = "internal"
    service_name: str | None = None
    operation: str | None = None
    resource: str | None = None
    attributes: dict | None = None


class EndSpanRequest(BaseModel):
    status: str = "ok"
    error_message: str | None = None
    error_type: str | None = None
    attributes: dict | None = None


class AddEventRequest(BaseModel):
    name: str
    attributes: dict | None = None


@router.post("/traces")
async def start_trace(
    request: StartTraceRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Start a new trace."""
    service = TracingService(db)

    trace = await service.start_trace(
        name=request.name,
        trace_id=request.trace_id,
        root_agent_id=agent.id,
        root_service=request.root_service,
        context=request.context,
        tags=request.tags,
    )

    return {
        "id": str(trace.id),
        "trace_id": trace.trace_id,
        "name": trace.name,
        "started_at": trace.started_at.isoformat(),
    }


@router.get("/traces")
async def list_traces(
    service_name: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List traces."""
    service = TracingService(db)

    # SECURITY: Only list traces started by this agent
    traces = await service.list_traces(
        root_agent_id=agent.id,
        service_name=service_name,
        status=status,
        since=since,
        limit=limit,
    )

    return [
        {
            "trace_id": t.trace_id,
            "name": t.name,
            "root_service": t.root_service,
            "status": t.status,
            "duration_ms": t.duration_ms,
            "span_count": t.span_count,
            "started_at": t.started_at.isoformat(),
        }
        for t in traces
    ]


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a trace with its spans."""
    service = TracingService(db)
    trace = await service.get_trace(trace_id)

    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    # SECURITY: Verify ownership
    if trace.root_agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this trace")

    return {
        "trace_id": trace.trace_id,
        "name": trace.name,
        "root_agent_id": str(trace.root_agent_id) if trace.root_agent_id else None,
        "root_service": trace.root_service,
        "context": trace.context,
        "tags": trace.tags,
        "status": trace.status,
        "error": trace.error,
        "duration_ms": trace.duration_ms,
        "span_count": trace.span_count,
        "started_at": trace.started_at.isoformat(),
        "ended_at": trace.ended_at.isoformat() if trace.ended_at else None,
        "spans": [
            {
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "kind": s.kind,
                "service_name": s.service_name,
                "operation": s.operation,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "attributes": s.attributes,
            }
            for s in trace.spans
        ],
    }


@router.get("/traces/{trace_id}/tree")
async def get_span_tree(
    trace_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get hierarchical span tree for a trace."""
    service = TracingService(db)

    # SECURITY: Verify ownership first
    trace = await service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    if trace.root_agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this trace")

    tree = await service.get_span_tree(trace_id)
    return tree


@router.post("/traces/{trace_id}/end")
async def end_trace(
    trace_id: str,
    status: str = "completed",
    error: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """End a trace."""
    service = TracingService(db)

    # SECURITY: Verify ownership before ending
    trace = await service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    if trace.root_agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to end this trace")

    trace = await service.end_trace(trace_id, status, error)
    return {"status": "ended", "duration_ms": trace.duration_ms}


@router.post("/traces/{trace_id}/spans")
async def start_span(
    trace_id: str,
    request: StartSpanRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Start a new span within a trace."""
    service = TracingService(db)

    try:
        span = await service.start_span(
            trace_id=trace_id,
            name=request.name,
            parent_span_id=request.parent_span_id,
            span_id=request.span_id,
            kind=request.kind,
            service_name=request.service_name,
            agent_id=agent.id,
            operation=request.operation,
            resource=request.resource,
            attributes=request.attributes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "span_id": span.span_id,
        "name": span.name,
        "started_at": span.started_at.isoformat(),
    }


@router.post("/spans/{span_id}/end")
async def end_span(
    span_id: str,
    request: EndSpanRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """End a span."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.tracing.models import Span

    # SECURITY: Verify ownership via trace
    result = await db.execute(
        select(Span)
        .options(selectinload(Span.trace))
        .where(Span.span_id == span_id)
    )
    span_record = result.scalar_one_or_none()
    if not span_record:
        raise HTTPException(status_code=404, detail="Span not found")
    if span_record.trace and span_record.trace.root_agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this span")

    service = TracingService(db)
    span = await service.end_span(
        span_id,
        request.status,
        request.error_message,
        request.error_type,
        request.attributes,
    )

    return {"status": "ended", "duration_ms": span.duration_ms}


@router.post("/spans/{span_id}/events")
async def add_event(
    span_id: str,
    request: AddEventRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add an event to a span."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from nexus.tracing.models import Span

    # SECURITY: Verify ownership via trace
    result = await db.execute(
        select(Span)
        .options(selectinload(Span.trace))
        .where(Span.span_id == span_id)
    )
    span_record = result.scalar_one_or_none()
    if not span_record:
        raise HTTPException(status_code=404, detail="Span not found")
    if span_record.trace and span_record.trace.root_agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this span")

    service = TracingService(db)
    await service.add_span_event(span_id, request.name, request.attributes)
    return {"status": "added"}
