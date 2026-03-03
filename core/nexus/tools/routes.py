"""Tool API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.tools.models import ToolCategory, AuthType
from nexus.tools.service import ToolService

router = APIRouter(prefix="/tools", tags=["tools"])


class CreateToolRequest(BaseModel):
    name: str
    slug: str
    description: str | None = None
    category: str = "custom"
    input_schema: dict | None = None
    output_schema: dict | None = None
    endpoint_url: str | None = None
    http_method: str = "POST"
    headers: dict | None = None
    query_params: dict | None = None
    auth_type: str = "none"
    auth_config: dict | None = None
    request_template: str | None = None
    response_mapping: dict | None = None
    rate_limit: int | None = None
    timeout: float = 30.0
    cache_enabled: bool = False
    cache_ttl: int = 300


class ExecuteToolRequest(BaseModel):
    input: dict
    conversation_id: str | None = None
    invocation_id: str | None = None


class UpdateToolRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    endpoint_url: str | None = None
    headers: dict | None = None
    auth_config: dict | None = None
    is_active: bool | None = None


@router.post("")
async def create_tool(
    request: CreateToolRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tool definition."""
    service = ToolService(db)

    tool = await service.create_tool(
        name=request.name,
        slug=request.slug,
        description=request.description,
        category=ToolCategory(request.category),
        owner_id=agent.id,
        input_schema=request.input_schema,
        output_schema=request.output_schema,
        endpoint_url=request.endpoint_url,
        http_method=request.http_method,
        headers=request.headers,
        query_params=request.query_params,
        auth_type=AuthType(request.auth_type),
        auth_config=request.auth_config,
        request_template=request.request_template,
        response_mapping=request.response_mapping,
        rate_limit=request.rate_limit,
        timeout=request.timeout,
        cache_enabled=request.cache_enabled,
        cache_ttl=request.cache_ttl,
    )

    return {
        "id": str(tool.id),
        "name": tool.name,
        "slug": tool.slug,
        "category": tool.category.value,
        "created_at": tool.created_at.isoformat(),
    }


@router.get("")
async def list_tools(
    category: str | None = None,
    owner_only: bool = False,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List available tools."""
    service = ToolService(db)

    tools = await service.list_tools(
        owner_id=agent.id if owner_only else None,
        category=ToolCategory(category) if category else None,
        limit=limit,
    )

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "description": t.description,
            "category": t.category.value,
            "input_schema": t.input_schema,
            "is_active": t.is_active,
            "health_status": t.health_status,
            "total_executions": t.total_executions,
            "avg_latency_ms": t.avg_latency_ms,
        }
        for t in tools
    ]


@router.get("/{tool_id}")
async def get_tool(
    tool_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a tool by ID."""
    service = ToolService(db)
    tool = await service.get_tool(UUID(tool_id))

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    return {
        "id": str(tool.id),
        "name": tool.name,
        "slug": tool.slug,
        "description": tool.description,
        "category": tool.category.value,
        "input_schema": tool.input_schema,
        "output_schema": tool.output_schema,
        "endpoint_url": tool.endpoint_url,
        "http_method": tool.http_method,
        "auth_type": tool.auth_type.value,
        "is_active": tool.is_active,
        "health_status": tool.health_status,
        "total_executions": tool.total_executions,
        "successful_executions": tool.successful_executions,
        "avg_latency_ms": tool.avg_latency_ms,
        "version": tool.version,
        "created_at": tool.created_at.isoformat(),
    }


@router.post("/{tool_id}/execute")
async def execute_tool(
    tool_id: str,
    request: ExecuteToolRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Execute a tool."""
    service = ToolService(db)

    try:
        execution = await service.execute_tool(
            tool_id=UUID(tool_id),
            input_data=request.input,
            executor_id=agent.id,
            executor_type="agent",
            conversation_id=UUID(request.conversation_id) if request.conversation_id else None,
            invocation_id=UUID(request.invocation_id) if request.invocation_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "execution_id": str(execution.id),
        "status": execution.status,
        "output": execution.output_data,
        "error": execution.error,
        "duration_ms": execution.duration_ms,
    }


@router.post("/slug/{slug}/execute")
async def execute_tool_by_slug(
    slug: str,
    request: ExecuteToolRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Execute a tool by slug."""
    service = ToolService(db)
    tool = await service.get_tool_by_slug(slug)

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    try:
        execution = await service.execute_tool(
            tool_id=tool.id,
            input_data=request.input,
            executor_id=agent.id,
            executor_type="agent",
            conversation_id=UUID(request.conversation_id) if request.conversation_id else None,
            invocation_id=UUID(request.invocation_id) if request.invocation_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "execution_id": str(execution.id),
        "tool": slug,
        "status": execution.status,
        "output": execution.output_data,
        "error": execution.error,
        "duration_ms": execution.duration_ms,
    }


@router.get("/{tool_id}/executions")
async def list_executions(
    tool_id: str,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List executions for a tool."""
    from sqlalchemy import select
    from nexus.tools.models import ToolExecution

    result = await db.execute(
        select(ToolExecution)
        .where(ToolExecution.tool_id == UUID(tool_id))
        .order_by(ToolExecution.started_at.desc())
        .limit(limit)
    )
    executions = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "executor_id": str(e.executor_id),
            "status": e.status,
            "duration_ms": e.duration_ms,
            "started_at": e.started_at.isoformat(),
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        }
        for e in executions
    ]


@router.post("/{tool_id}/health")
async def health_check_tool(
    tool_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Perform health check on a tool."""
    service = ToolService(db)
    result = await service.health_check(UUID(tool_id))
    return result


@router.put("/{tool_id}")
async def update_tool(
    tool_id: str,
    request: UpdateToolRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update a tool."""
    service = ToolService(db)
    tool = await service.get_tool(UUID(tool_id))

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if tool.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Update fields
    if request.name is not None:
        tool.name = request.name
    if request.description is not None:
        tool.description = request.description
    if request.input_schema is not None:
        tool.input_schema = request.input_schema
    if request.output_schema is not None:
        tool.output_schema = request.output_schema
    if request.endpoint_url is not None:
        tool.endpoint_url = request.endpoint_url
    if request.headers is not None:
        tool.headers = request.headers
    if request.auth_config is not None:
        tool.auth_config = request.auth_config
    if request.is_active is not None:
        tool.is_active = request.is_active

    await db.commit()

    return {"status": "updated", "id": str(tool.id)}


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tool."""
    service = ToolService(db)
    tool = await service.get_tool(UUID(tool_id))

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if tool.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(tool)
    await db.commit()

    return {"status": "deleted"}
