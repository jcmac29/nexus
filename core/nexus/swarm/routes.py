"""Swarm API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.swarm.models import TaskStatus
from nexus.swarm.schemas import (
    AggregatedResultsResponse,
    CompleteTaskRequest,
    CreateSwarmRequest,
    JoinSwarmRequest,
    SubmitBatchRequest,
    SubmitTaskRequest,
    SwarmMemberResponse,
    SwarmResponse,
    SwarmStatusResponse,
    SwarmTaskResponse,
    SwarmTaskResultResponse,
)
from nexus.swarm.service import SwarmService

router = APIRouter(prefix="/swarm", tags=["swarm"])


def _swarm_to_response(swarm, stats: dict) -> SwarmResponse:
    """Convert swarm model to response."""
    return SwarmResponse(
        id=swarm.id,
        name=swarm.name,
        join_code=swarm.join_code,
        status=swarm.status.value,
        config=swarm.config,
        created_at=swarm.created_at,
        disbanded_at=swarm.disbanded_at,
        member_count=stats.get("member_count", 0),
        pending_tasks=stats.get("pending_tasks", 0),
        completed_tasks=stats.get("completed_tasks", 0),
    )


def _member_to_response(member) -> SwarmMemberResponse:
    """Convert member model to response."""
    return SwarmMemberResponse(
        id=member.id,
        agent_id=member.agent_id,
        agent_name=member.agent.name if hasattr(member, "agent") and member.agent else None,
        role=member.role.value,
        status=member.status.value,
        capabilities=member.capabilities or [],
        tasks_completed=member.tasks_completed,
        last_heartbeat=member.last_heartbeat,
        joined_at=member.joined_at,
    )


def _task_to_response(task) -> SwarmTaskResponse:
    """Convert task model to response."""
    return SwarmTaskResponse(
        id=task.id,
        swarm_id=task.swarm_id,
        parent_task_id=task.parent_task_id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        priority=task.priority,
        input_data=task.input_data,
        required_capabilities=task.required_capabilities or [],
        status=task.status.value,
        assigned_to=task.assigned_to,
        assigned_at=task.assigned_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        timeout_seconds=task.timeout_seconds,
        retry_count=task.retry_count,
        created_at=task.created_at,
    )


def _result_to_response(result) -> SwarmTaskResultResponse:
    """Convert result model to response."""
    return SwarmTaskResultResponse(
        id=result.id,
        task_id=result.task_id,
        member_id=result.member_id,
        output_data=result.output_data,
        success=result.success,
        error_message=result.error_message,
        execution_time_ms=result.execution_time_ms,
        created_at=result.created_at,
    )


@router.post("", status_code=201)
async def create_swarm(
    request: CreateSwarmRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new swarm."""
    service = SwarmService(db)
    swarm, leader = await service.create_swarm(
        name=request.name,
        owner_agent_id=agent.id,
        config=request.config,
    )
    stats = await service.get_swarm_stats(swarm.id)

    return {
        "swarm": _swarm_to_response(swarm, stats),
        "member": _member_to_response(leader),
        "join_code": swarm.join_code,
    }


@router.get("/{swarm_id}")
async def get_swarm(
    swarm_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmStatusResponse:
    """Get swarm status with members and recent tasks."""
    service = SwarmService(db)
    swarm = await service.get_swarm(swarm_id)

    if not swarm:
        raise HTTPException(status_code=404, detail="Swarm not found")

    stats = await service.get_swarm_stats(swarm_id)
    members = await service.list_members(swarm_id)
    tasks = await service.list_tasks(swarm_id, limit=20)

    return SwarmStatusResponse(
        swarm=_swarm_to_response(swarm, stats),
        members=[_member_to_response(m) for m in members],
        recent_tasks=[_task_to_response(t) for t in tasks],
        task_summary=stats,
    )


@router.post("/join")
async def join_swarm(
    request: JoinSwarmRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Join an existing swarm by code."""
    service = SwarmService(db)

    try:
        member = await service.join_swarm(
            join_code=request.join_code,
            agent_id=agent.id,
            capabilities=request.capabilities,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    swarm = await service.get_swarm(member.swarm_id)
    stats = await service.get_swarm_stats(member.swarm_id)

    return {
        "swarm": _swarm_to_response(swarm, stats),
        "member": _member_to_response(member),
    }


@router.post("/{swarm_id}/leave")
async def leave_swarm(
    swarm_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Leave a swarm."""
    service = SwarmService(db)

    member = await service.get_member_by_agent(swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=404, detail="Not a member of this swarm")

    try:
        await service.leave_swarm(swarm_id, member.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "left"}


@router.delete("/{swarm_id}")
async def disband_swarm(
    swarm_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disband a swarm (leader only)."""
    service = SwarmService(db)

    try:
        await service.disband_swarm(swarm_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return {"status": "disbanded"}


# ==================== Task Endpoints ====================


@router.post("/{swarm_id}/tasks", status_code=201)
async def submit_task(
    swarm_id: UUID,
    request: SubmitTaskRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmTaskResponse:
    """Submit a task to the swarm."""
    service = SwarmService(db)

    # Verify membership
    member = await service.get_member_by_agent(swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this swarm")

    task = await service.submit_task(
        swarm_id=swarm_id,
        title=request.title,
        description=request.description,
        task_type=request.task_type,
        priority=request.priority,
        input_data=request.input_data,
        required_capabilities=request.required_capabilities,
        timeout_seconds=request.timeout_seconds,
        max_retries=request.max_retries,
        created_by=member.id,
    )

    return _task_to_response(task)


@router.post("/{swarm_id}/tasks/batch", status_code=201)
async def submit_batch(
    swarm_id: UUID,
    request: SubmitBatchRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[SwarmTaskResponse]:
    """Submit multiple tasks to the swarm."""
    service = SwarmService(db)

    member = await service.get_member_by_agent(swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this swarm")

    tasks = await service.submit_batch(
        swarm_id=swarm_id,
        tasks=[t.model_dump() for t in request.tasks],
        created_by=member.id,
    )

    return [_task_to_response(t) for t in tasks]


@router.get("/{swarm_id}/tasks")
async def list_tasks(
    swarm_id: UUID,
    status: str | None = None,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[SwarmTaskResponse]:
    """List tasks in the swarm."""
    service = SwarmService(db)

    task_status = TaskStatus(status) if status else None
    tasks = await service.list_tasks(swarm_id, status=task_status, limit=limit)

    return [_task_to_response(t) for t in tasks]


@router.get("/{swarm_id}/tasks/{task_id}")
async def get_task(
    swarm_id: UUID,
    task_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmTaskResponse:
    """Get task details."""
    service = SwarmService(db)
    task = await service.get_task(task_id)

    if not task or task.swarm_id != swarm_id:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_to_response(task)


@router.post("/tasks/claim")
async def claim_task(
    swarm_id: UUID = Query(...),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmTaskResponse | None:
    """Claim the next available task."""
    service = SwarmService(db)

    member = await service.get_member_by_agent(swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this swarm")

    task = await service.claim_task(member.id)
    if not task:
        return None

    return _task_to_response(task)


@router.post("/tasks/{task_id}/start")
async def start_task(
    task_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmTaskResponse:
    """Mark task as in progress."""
    service = SwarmService(db)
    task = await service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    member = await service.get_member_by_agent(task.swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this swarm")

    try:
        task = await service.start_task(task_id, member.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _task_to_response(task)


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: UUID,
    request: CompleteTaskRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmTaskResultResponse:
    """Mark task as complete."""
    service = SwarmService(db)
    task = await service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    member = await service.get_member_by_agent(task.swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this swarm")

    try:
        result = await service.complete_task(
            task_id=task_id,
            member_id=member.id,
            output_data=request.output_data,
            success=request.success,
            error_message=request.error_message,
            execution_time_ms=request.execution_time_ms,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _result_to_response(result)


@router.post("/tasks/{task_id}/fail")
async def fail_task(
    task_id: UUID,
    error_message: str = Query(...),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmTaskResponse:
    """Mark task as failed."""
    service = SwarmService(db)
    task = await service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    member = await service.get_member_by_agent(task.swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this swarm")

    try:
        task = await service.fail_task(task_id, member.id, error_message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _task_to_response(task)


@router.get("/{swarm_id}/results")
async def get_results(
    swarm_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> AggregatedResultsResponse:
    """Get aggregated results for the swarm."""
    service = SwarmService(db)
    stats = await service.get_swarm_stats(swarm_id)
    results = await service.get_results(swarm_id)

    return AggregatedResultsResponse(
        swarm_id=swarm_id,
        total_tasks=stats.get("total_tasks", 0),
        completed_tasks=stats.get("completed_tasks", 0),
        failed_tasks=stats.get("failed_tasks", 0),
        pending_tasks=stats.get("pending_tasks", 0),
        results=[_result_to_response(r) for r in results],
    )


# ==================== Member Endpoints ====================


@router.post("/{swarm_id}/heartbeat")
async def heartbeat(
    swarm_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> SwarmMemberResponse:
    """Send heartbeat to keep member active."""
    service = SwarmService(db)

    member = await service.get_member_by_agent(swarm_id, agent.id)
    if not member:
        raise HTTPException(status_code=404, detail="Not a member of this swarm")

    member = await service.heartbeat(member.id)
    return _member_to_response(member)
