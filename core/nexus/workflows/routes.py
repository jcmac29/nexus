"""Workflow API routes."""

from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.workflows.models import WorkflowStatus
from nexus.workflows.service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


# --- Schemas ---

class WorkflowStepSchema(BaseModel):
    id: str = Field(..., description="Unique step identifier")
    agent_id: str = Field(..., description="Target agent ID")
    capability: str = Field(..., description="Capability to invoke")
    input_mapping: dict[str, Any] = Field(default_factory=dict, description="Input mapping with {{expressions}}")
    output_key: str = Field(..., description="Key to store output in context")


class CreateWorkflowRequest(BaseModel):
    name: str = Field(..., description="Workflow name")
    description: str | None = Field(None, description="Workflow description")
    steps: list[WorkflowStepSchema] = Field(default_factory=list, description="Workflow steps")
    input_schema: dict | None = Field(None, description="Expected input schema")
    timeout_seconds: int = Field(300, description="Total timeout for workflow")


class UpdateWorkflowRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[WorkflowStepSchema] | None = None
    status: str | None = None
    is_public: bool | None = None


class RunWorkflowRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict, description="Workflow input data")


class WorkflowResponse(BaseModel):
    id: str
    owner_agent_id: str
    name: str
    description: str | None
    steps: list[dict]
    input_schema: dict | None
    status: str
    timeout_seconds: int
    is_public: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    triggered_by: str | None
    input_data: dict
    output_data: dict | None
    status: str
    current_step: int
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


# --- Routes ---

async def get_workflow_service(db: AsyncSession = Depends(get_db)) -> WorkflowService:
    return WorkflowService(db)


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    data: CreateWorkflowRequest,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Create a new workflow."""
    workflow = await service.create_workflow(
        owner_agent_id=agent.id,
        name=data.name,
        description=data.description,
        steps=[s.model_dump() for s in data.steps],
        input_schema=data.input_schema,
        timeout_seconds=data.timeout_seconds,
    )
    return _workflow_to_response(workflow)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    include_public: bool = False,
    limit: int = 50,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """List workflows."""
    workflows = await service.list_workflows(
        owner_agent_id=agent.id,
        include_public=include_public,
        limit=limit,
    )
    return [_workflow_to_response(w) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Get a workflow by ID."""
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.owner_agent_id != agent.id and not workflow.is_public:
        raise HTTPException(status_code=403, detail="Access denied")
    return _workflow_to_response(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    data: UpdateWorkflowRequest,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Update a workflow."""
    updates = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.description is not None:
        updates["description"] = data.description
    if data.steps is not None:
        updates["steps"] = [s.model_dump() for s in data.steps]
    if data.status is not None:
        try:
            updates["status"] = WorkflowStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")
    if data.is_public is not None:
        updates["is_public"] = data.is_public

    workflow = await service.update_workflow(workflow_id, agent.id, **updates)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflow_to_response(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Delete a workflow."""
    deleted = await service.delete_workflow(workflow_id, agent.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def run_workflow(
    workflow_id: UUID,
    data: RunWorkflowRequest,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Execute a workflow."""
    # SECURITY: Verify ownership or public access before running
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.owner_agent_id != agent.id and not workflow.is_public:
        raise HTTPException(status_code=403, detail="Not authorized to run this workflow")

    try:
        run = await service.run_workflow(
            workflow_id=workflow_id,
            triggered_by=agent.id,
            input_data=data.input,
        )
        return _run_to_response(run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunResponse])
async def list_workflow_runs(
    workflow_id: UUID,
    limit: int = 50,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """List runs for a workflow."""
    # SECURITY: Verify ownership or public access before viewing runs
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.owner_agent_id != agent.id and not workflow.is_public:
        raise HTTPException(status_code=403, detail="Not authorized to view runs for this workflow")

    runs = await service.list_runs(workflow_id=workflow_id, limit=limit)
    return [_run_to_response(r) for r in runs]


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_workflow_run(
    run_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Get a workflow run by ID."""
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # SECURITY: Verify ownership or public access before viewing run details
    workflow = await service.get_workflow(run.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.owner_agent_id != agent.id and not workflow.is_public:
        raise HTTPException(status_code=403, detail="Not authorized to view this run")

    return _run_to_response(run)


def _workflow_to_response(workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=str(workflow.id),
        owner_agent_id=str(workflow.owner_agent_id),
        name=workflow.name,
        description=workflow.description,
        steps=workflow.steps,
        input_schema=workflow.input_schema,
        status=workflow.status.value,
        timeout_seconds=workflow.timeout_seconds,
        is_public=workflow.is_public,
        created_at=workflow.created_at.isoformat(),
        updated_at=workflow.updated_at.isoformat(),
    )


def _run_to_response(run) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        id=str(run.id),
        workflow_id=str(run.workflow_id),
        triggered_by=str(run.triggered_by) if run.triggered_by else None,
        input_data=run.input_data,
        output_data=run.output_data,
        status=run.status.value,
        current_step=run.current_step,
        error_message=run.error_message,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        created_at=run.created_at.isoformat(),
    )
