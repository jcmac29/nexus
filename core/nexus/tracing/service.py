"""Tracing service for distributed observability."""

from __future__ import annotations

import secrets
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nexus.tracing.models import Trace, Span


class TracingService:
    """Service for distributed tracing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def generate_trace_id(self) -> str:
        """Generate a unique trace ID."""
        return secrets.token_hex(16)

    def generate_span_id(self) -> str:
        """Generate a unique span ID."""
        return secrets.token_hex(8)

    async def start_trace(
        self,
        name: str,
        trace_id: str | None = None,
        root_agent_id: UUID | None = None,
        root_service: str | None = None,
        context: dict | None = None,
        tags: dict | None = None,
    ) -> Trace:
        """Start a new trace."""
        trace = Trace(
            trace_id=trace_id or self.generate_trace_id(),
            name=name,
            root_agent_id=root_agent_id,
            root_service=root_service,
            context=context or {},
            tags=tags or {},
        )
        self.db.add(trace)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def end_trace(
        self,
        trace_id: str,
        status: str = "completed",
        error: str | None = None,
    ) -> Trace | None:
        """End a trace."""
        result = await self.db.execute(
            select(Trace).where(Trace.trace_id == trace_id)
        )
        trace = result.scalar_one_or_none()

        if trace:
            trace.ended_at = datetime.utcnow()
            trace.status = status
            trace.error = error
            if trace.started_at:
                trace.duration_ms = (trace.ended_at - trace.started_at).total_seconds() * 1000
            await self.db.commit()

        return trace

    async def start_span(
        self,
        trace_id: str,
        name: str,
        parent_span_id: str | None = None,
        span_id: str | None = None,
        kind: str = "internal",
        service_name: str | None = None,
        agent_id: UUID | None = None,
        operation: str | None = None,
        resource: str | None = None,
        attributes: dict | None = None,
    ) -> Span:
        """Start a new span within a trace."""
        # Get trace
        result = await self.db.execute(
            select(Trace).where(Trace.trace_id == trace_id)
        )
        trace = result.scalar_one_or_none()

        if not trace:
            raise ValueError(f"Trace {trace_id} not found")

        span = Span(
            span_id=span_id or self.generate_span_id(),
            trace_id=trace.id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            service_name=service_name,
            agent_id=agent_id,
            operation=operation,
            resource=resource,
            attributes=attributes or {},
        )
        self.db.add(span)

        trace.span_count += 1
        await self.db.commit()
        await self.db.refresh(span)
        return span

    async def end_span(
        self,
        span_id: str,
        status: str = "ok",
        error_message: str | None = None,
        error_type: str | None = None,
        attributes: dict | None = None,
    ) -> Span | None:
        """End a span."""
        result = await self.db.execute(
            select(Span).where(Span.span_id == span_id)
        )
        span = result.scalar_one_or_none()

        if span:
            span.ended_at = datetime.utcnow()
            span.status = status
            span.error_message = error_message
            span.error_type = error_type
            if attributes:
                span.attributes = {**span.attributes, **attributes}
            if span.started_at:
                span.duration_ms = (span.ended_at - span.started_at).total_seconds() * 1000
            await self.db.commit()

        return span

    async def add_span_event(
        self,
        span_id: str,
        name: str,
        attributes: dict | None = None,
    ):
        """Add an event to a span."""
        result = await self.db.execute(
            select(Span).where(Span.span_id == span_id)
        )
        span = result.scalar_one_or_none()

        if span:
            events = list(span.events or [])
            events.append({
                "name": name,
                "timestamp": datetime.utcnow().isoformat(),
                "attributes": attributes or {},
            })
            span.events = events
            await self.db.commit()

    async def get_trace(self, trace_id: str, include_spans: bool = True) -> Trace | None:
        """Get a trace by ID."""
        query = select(Trace).where(Trace.trace_id == trace_id)
        if include_spans:
            query = query.options(selectinload(Trace.spans))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_traces(
        self,
        service_name: str | None = None,
        agent_id: UUID | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Trace]:
        """List traces with filters."""
        query = select(Trace).order_by(Trace.started_at.desc()).limit(limit)

        if service_name:
            query = query.where(Trace.root_service == service_name)
        if agent_id:
            query = query.where(Trace.root_agent_id == agent_id)
        if status:
            query = query.where(Trace.status == status)
        if since:
            query = query.where(Trace.started_at >= since)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_span_tree(self, trace_id: str) -> dict:
        """Get hierarchical span tree for a trace."""
        trace = await self.get_trace(trace_id, include_spans=True)
        if not trace:
            return {}

        # Build span tree
        spans_by_id = {s.span_id: s for s in trace.spans}
        root_spans = []
        children: dict[str, list] = {}

        for span in trace.spans:
            if span.parent_span_id:
                if span.parent_span_id not in children:
                    children[span.parent_span_id] = []
                children[span.parent_span_id].append(span)
            else:
                root_spans.append(span)

        def build_tree(span: Span) -> dict:
            return {
                "span_id": span.span_id,
                "name": span.name,
                "kind": span.kind,
                "service": span.service_name,
                "agent_id": str(span.agent_id) if span.agent_id else None,
                "duration_ms": span.duration_ms,
                "status": span.status,
                "children": [build_tree(c) for c in children.get(span.span_id, [])],
            }

        return {
            "trace_id": trace.trace_id,
            "name": trace.name,
            "duration_ms": trace.duration_ms,
            "status": trace.status,
            "spans": [build_tree(s) for s in root_spans],
        }
