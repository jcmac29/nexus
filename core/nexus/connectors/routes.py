"""Connector API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.connectors.models import ConnectorType
from nexus.connectors.service import ConnectorService

router = APIRouter(prefix="/connectors", tags=["connectors"])


class CreateConnectorRequest(BaseModel):
    name: str
    slug: str
    connector_type: str
    connection_config: dict
    description: str | None = None
    allowed_operations: list[str] | None = None
    query_templates: dict | None = None
    rate_limit: int | None = None
    pool_size: int = 5


class ExecuteRequest(BaseModel):
    operation: str
    query: str | None = None
    template_name: str | None = None
    params: dict | None = None


class AddTemplateRequest(BaseModel):
    name: str
    query: str
    description: str | None = None
    default_params: dict | None = None


@router.post("")
async def create_connector(
    request: CreateConnectorRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new connector."""
    service = ConnectorService(db)

    try:
        connector = await service.create_connector(
            name=request.name,
            slug=request.slug,
            connector_type=ConnectorType(request.connector_type),
            owner_id=agent.id,
            connection_config=request.connection_config,
            description=request.description,
            allowed_operations=request.allowed_operations,
            query_templates=request.query_templates,
            rate_limit=request.rate_limit,
            pool_size=request.pool_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": str(connector.id),
        "name": connector.name,
        "slug": connector.slug,
        "connector_type": connector.connector_type.value,
        "created_at": connector.created_at.isoformat(),
    }


@router.get("")
async def list_connectors(
    connector_type: str | None = None,
    owner_only: bool = False,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List connectors."""
    service = ConnectorService(db)

    connectors = await service.list_connectors(
        owner_id=agent.id if owner_only else None,
        connector_type=ConnectorType(connector_type) if connector_type else None,
        limit=limit,
    )

    return [
        {
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug,
            "connector_type": c.connector_type.value,
            "is_active": c.is_active,
            "health_status": c.health_status,
            "total_operations": c.total_operations,
            "avg_latency_ms": c.avg_latency_ms,
        }
        for c in connectors
    ]


@router.get("/{connector_id}")
async def get_connector(
    connector_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a connector."""
    service = ConnectorService(db)
    connector = await service.get_connector(UUID(connector_id))

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    return {
        "id": str(connector.id),
        "name": connector.name,
        "slug": connector.slug,
        "description": connector.description,
        "connector_type": connector.connector_type.value,
        "allowed_operations": connector.allowed_operations,
        "query_templates": list(connector.query_templates.keys()),
        "schema_info": connector.schema_info,
        "is_active": connector.is_active,
        "health_status": connector.health_status,
        "total_operations": connector.total_operations,
        "successful_operations": connector.successful_operations,
        "failed_operations": connector.failed_operations,
        "avg_latency_ms": connector.avg_latency_ms,
        "last_used_at": connector.last_used_at.isoformat() if connector.last_used_at else None,
    }


@router.post("/{connector_id}/execute")
async def execute(
    connector_id: str,
    request: ExecuteRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Execute an operation on a connector."""
    service = ConnectorService(db)

    # SECURITY: Verify ownership before execution
    connector = await service.get_connector(UUID(connector_id))
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to use this connector")

    try:
        execution = await service.execute(
            connector_id=UUID(connector_id),
            operation=request.operation,
            executor_id=agent.id,
            executor_type="agent",
            query=request.query,
            template_name=request.template_name,
            params=request.params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "execution_id": str(execution.id),
        "status": execution.status,
        "result": execution.result,
        "rows_affected": execution.rows_affected,
        "duration_ms": execution.duration_ms,
    }


@router.post("/slug/{slug}/execute")
async def execute_by_slug(
    slug: str,
    request: ExecuteRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Execute an operation on a connector by slug."""
    service = ConnectorService(db)
    connector = await service.get_connector_by_slug(slug)

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # SECURITY: Verify ownership before execution
    if connector.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to use this connector")

    try:
        execution = await service.execute(
            connector_id=connector.id,
            operation=request.operation,
            executor_id=agent.id,
            executor_type="agent",
            query=request.query,
            template_name=request.template_name,
            params=request.params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "execution_id": str(execution.id),
        "connector": slug,
        "status": execution.status,
        "result": execution.result,
        "duration_ms": execution.duration_ms,
    }


@router.post("/{connector_id}/templates")
async def add_template(
    connector_id: str,
    request: AddTemplateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add a query template to a connector."""
    service = ConnectorService(db)
    connector = await service.get_connector(UUID(connector_id))

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # SECURITY: Verify ownership before modification
    if connector.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this connector")

    connector.query_templates[request.name] = {
        "query": request.query,
        "description": request.description,
        "default_params": request.default_params or {},
    }
    await db.commit()

    return {"status": "added", "template": request.name}


@router.get("/{connector_id}/templates")
async def list_templates(
    connector_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List query templates for a connector."""
    service = ConnectorService(db)
    connector = await service.get_connector(UUID(connector_id))

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    return [
        {
            "name": name,
            "description": template.get("description"),
            "query": template.get("query"),
        }
        for name, template in connector.query_templates.items()
    ]


@router.post("/{connector_id}/health")
async def health_check(
    connector_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Perform health check on a connector."""
    service = ConnectorService(db)

    # SECURITY: Verify ownership before health check
    connector = await service.get_connector(UUID(connector_id))
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to check this connector")

    result = await service.health_check(UUID(connector_id))
    return result


@router.post("/{connector_id}/discover")
async def discover_schema(
    connector_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Discover schema/structure of the connected system."""
    service = ConnectorService(db)

    # SECURITY: Verify ownership before schema discovery
    connector = await service.get_connector(UUID(connector_id))
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this connector")

    schema = await service.discover_schema(UUID(connector_id))
    return {"schema": schema}


@router.put("/{connector_id}/activate")
async def activate_connector(
    connector_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Activate a connector."""
    service = ConnectorService(db)
    connector = await service.get_connector(UUID(connector_id))

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # SECURITY: Verify ownership before modification
    if connector.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this connector")

    connector.is_active = True
    await db.commit()

    return {"status": "activated"}


@router.put("/{connector_id}/deactivate")
async def deactivate_connector(
    connector_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a connector."""
    service = ConnectorService(db)
    connector = await service.get_connector(UUID(connector_id))

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # SECURITY: Verify ownership before modification
    if connector.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this connector")

    connector.is_active = False
    await db.commit()

    return {"status": "deactivated"}
