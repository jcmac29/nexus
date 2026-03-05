"""Orchestration API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.orchestration.models import StepType, WorkflowStatus
from nexus.orchestration.service import OrchestrationService

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


class CreateWorkflowRequest(BaseModel):
    name: str
    slug: str
    description: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    config: dict | None = None


class AddStepRequest(BaseModel):
    name: str
    step_type: str
    order: int
    config: dict | None = None
    target_id: str | None = None
    target_type: str | None = None
    capability: str | None = None
    input_mapping: dict | None = None
    output_mapping: dict | None = None
    condition: str | None = None
    on_error: str = "fail"
    timeout: int | None = None


class StartExecutionRequest(BaseModel):
    input: dict


class ProvideInputRequest(BaseModel):
    input: dict


@router.post("/workflows")
async def create_workflow(
    request: CreateWorkflowRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow."""
    service = OrchestrationService(db)

    workflow = await service.create_workflow(
        name=request.name,
        slug=request.slug,
        description=request.description,
        owner_id=agent.id,
        input_schema=request.input_schema,
        output_schema=request.output_schema,
        config=request.config,
    )

    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "slug": workflow.slug,
        "status": workflow.status.value,
        "created_at": workflow.created_at.isoformat(),
    }


@router.get("/workflows")
async def list_workflows(
    owner_only: bool = False,
    status: str | None = None,
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List workflows."""
    from sqlalchemy import select
    from nexus.orchestration.models import OrchestrationWorkflow as Workflow

    query = select(Workflow)
    if owner_only:
        query = query.where(Workflow.owner_id == agent.id)
    if status:
        query = query.where(Workflow.status == WorkflowStatus(status))
    query = query.limit(limit)

    result = await db.execute(query)
    workflows = result.scalars().all()

    return [
        {
            "id": str(w.id),
            "name": w.name,
            "slug": w.slug,
            "status": w.status.value,
            "version": w.version,
        }
        for w in workflows
    ]


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a workflow with its steps."""
    service = OrchestrationService(db)
    workflow = await service.get_workflow(UUID(workflow_id))

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "slug": workflow.slug,
        "description": workflow.description,
        "status": workflow.status.value,
        "input_schema": workflow.input_schema,
        "output_schema": workflow.output_schema,
        "config": workflow.config,
        "version": workflow.version,
        "steps": [
            {
                "id": str(s.id),
                "name": s.name,
                "step_type": s.step_type.value,
                "order": s.order,
                "config": s.config,
                "target_id": str(s.target_id) if s.target_id else None,
                "capability": s.capability,
            }
            for s in workflow.steps
        ],
    }


@router.post("/workflows/{workflow_id}/steps")
async def add_step(
    workflow_id: str,
    request: AddStepRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add a step to a workflow."""
    service = OrchestrationService(db)

    # SECURITY: Verify ownership before modification
    workflow = await service.get_workflow(UUID(workflow_id))
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this workflow")

    step = await service.add_step(
        workflow_id=UUID(workflow_id),
        name=request.name,
        step_type=StepType(request.step_type),
        order=request.order,
        config=request.config,
        target_id=UUID(request.target_id) if request.target_id else None,
        target_type=request.target_type,
        capability=request.capability,
        input_mapping=request.input_mapping,
        output_mapping=request.output_mapping,
        condition=request.condition,
        on_error=request.on_error,
        timeout=request.timeout,
    )

    return {
        "id": str(step.id),
        "name": step.name,
        "step_type": step.step_type.value,
        "order": step.order,
    }


@router.post("/workflows/{workflow_id}/activate")
async def activate_workflow(
    workflow_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Activate a workflow."""
    service = OrchestrationService(db)
    workflow = await service.get_workflow(UUID(workflow_id))

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # SECURITY: Verify ownership before modification
    if workflow.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this workflow")

    workflow.status = WorkflowStatus.ACTIVE
    await db.commit()

    return {"status": "activated"}


@router.post("/workflows/{workflow_id}/execute")
async def start_execution(
    workflow_id: str,
    request: StartExecutionRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Start a workflow execution."""
    service = OrchestrationService(db)

    try:
        execution = await service.start_execution(
            workflow_id=UUID(workflow_id),
            input_data=request.input,
            triggered_by=agent.id,
            triggered_by_type="agent",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "execution_id": str(execution.id),
        "status": execution.status.value,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
    }


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get execution status."""
    service = OrchestrationService(db)
    execution = await service.get_execution(UUID(execution_id))

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "id": str(execution.id),
        "workflow_id": str(execution.workflow_id),
        "status": execution.status.value,
        "input_data": execution.input_data,
        "state": execution.state,
        "output_data": execution.output_data,
        "current_step_id": str(execution.current_step_id) if execution.current_step_id else None,
        "completed_steps": execution.completed_steps,
        "error": execution.error,
        "waiting_for_input": execution.waiting_for_input,
        "input_prompt": execution.input_prompt,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


@router.post("/executions/{execution_id}/input")
async def provide_input(
    execution_id: str,
    request: ProvideInputRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Provide human input to a waiting execution."""
    service = OrchestrationService(db)

    try:
        execution = await service.provide_human_input(
            UUID(execution_id),
            request.input,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": execution.status.value,
        "message": "Input received, execution resumed",
    }


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running execution."""
    service = OrchestrationService(db)

    # SECURITY: Verify the agent triggered this execution
    execution = await service.get_execution(UUID(execution_id))
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.triggered_by != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this execution")

    await service.cancel_execution(UUID(execution_id))
    return {"status": "cancelled"}
