"""Goals API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.goals.models import GoalPriority, GoalStatus
from nexus.goals.schemas import (
    BlockerRequest,
    BlockerResponse,
    CreateGoalRequest,
    DelegationRequest,
    DelegationResponse,
    GoalResponse,
    MilestoneRequest,
    MilestoneResponse,
    ResolveBlockerRequest,
    UpdateGoalRequest,
    UpdateProgressRequest,
)
from nexus.goals.service import GoalsService

router = APIRouter(prefix="/goals", tags=["goals"])


def _goal_to_response(goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        agent_id=goal.agent_id,
        parent_goal_id=goal.parent_goal_id,
        title=goal.title,
        description=goal.description,
        success_criteria=goal.success_criteria,
        goal_type=goal.goal_type,
        tags=goal.tags or [],
        status=goal.status.value,
        priority=goal.priority.value,
        progress_percent=goal.progress_percent,
        progress_notes=goal.progress_notes,
        target_date=goal.target_date,
        started_at=goal.started_at,
        completed_at=goal.completed_at,
        outcome=goal.outcome,
        created_at=goal.created_at,
    )


@router.post("", status_code=201)
async def create_goal(
    request: CreateGoalRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Create a new goal."""
    service = GoalsService(db)

    goal = await service.create_goal(
        agent_id=agent.id,
        title=request.title,
        description=request.description,
        success_criteria=request.success_criteria,
        goal_type=request.goal_type,
        tags=request.tags,
        priority=GoalPriority(request.priority),
        target_date=request.target_date,
        parent_goal_id=request.parent_goal_id,
        config=request.config,
        constraints=request.constraints,
    )

    return _goal_to_response(goal)


@router.get("")
async def list_goals(
    status: str | None = None,
    priority: str | None = None,
    include_completed: bool = False,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[GoalResponse]:
    """List goals."""
    service = GoalsService(db)

    gs = GoalStatus(status) if status else None
    gp = GoalPriority(priority) if priority else None

    goals = await service.list_goals(
        agent_id=agent.id,
        status=gs,
        priority=gp,
        include_completed=include_completed,
        limit=limit,
    )

    return [_goal_to_response(g) for g in goals]


@router.get("/{goal_id}")
async def get_goal(
    goal_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Get a goal."""
    service = GoalsService(db)
    goal = await service.get_goal(goal_id)

    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # SECURITY: Verify ownership before viewing goal details
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this goal")

    return _goal_to_response(goal)


@router.patch("/{goal_id}")
async def update_goal(
    goal_id: UUID,
    request: UpdateGoalRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Update a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before modification
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this goal")

    try:
        goal = await service.update_goal(
            goal_id=goal_id,
            title=request.title,
            description=request.description,
            success_criteria=request.success_criteria,
            priority=GoalPriority(request.priority) if request.priority else None,
            target_date=request.target_date,
            config=request.config,
            constraints=request.constraints,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _goal_to_response(goal)


@router.post("/{goal_id}/activate")
async def activate_goal(
    goal_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Activate a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before activation
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to activate this goal")

    try:
        goal = await service.activate_goal(goal_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _goal_to_response(goal)


@router.post("/{goal_id}/start")
async def start_goal(
    goal_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Start working on a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before starting
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to start this goal")

    try:
        goal = await service.start_goal(goal_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _goal_to_response(goal)


@router.post("/{goal_id}/progress")
async def update_progress(
    goal_id: UUID,
    request: UpdateProgressRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Update goal progress."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before updating progress
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to update progress on this goal")

    try:
        goal = await service.update_progress(
            goal_id=goal_id,
            progress_percent=request.progress_percent,
            progress_notes=request.progress_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _goal_to_response(goal)


@router.post("/{goal_id}/complete")
async def complete_goal(
    goal_id: UUID,
    outcome: str | None = None,
    outcome_data: dict | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Complete a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before completing
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to complete this goal")

    try:
        goal = await service.complete_goal(goal_id, outcome, outcome_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _goal_to_response(goal)


@router.post("/{goal_id}/fail")
async def fail_goal(
    goal_id: UUID,
    outcome: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Mark a goal as failed."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before marking as failed
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this goal")

    try:
        goal = await service.fail_goal(goal_id, outcome)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _goal_to_response(goal)


@router.post("/{goal_id}/cancel")
async def cancel_goal(
    goal_id: UUID,
    reason: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Cancel a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before cancellation
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this goal")

    try:
        goal = await service.cancel_goal(goal_id, reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _goal_to_response(goal)


# ==================== Milestones ====================


@router.post("/{goal_id}/milestones", status_code=201)
async def add_milestone(
    goal_id: UUID,
    request: MilestoneRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> MilestoneResponse:
    """Add a milestone to a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before adding milestone
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this goal")

    milestone = await service.add_milestone(
        goal_id=goal_id,
        title=request.title,
        description=request.description,
        order=request.order,
        weight=request.weight,
        target_date=request.target_date,
    )

    return MilestoneResponse(
        id=milestone.id,
        goal_id=milestone.goal_id,
        title=milestone.title,
        description=milestone.description,
        order=milestone.order,
        weight=milestone.weight,
        is_completed=milestone.is_completed,
        completed_at=milestone.completed_at,
        target_date=milestone.target_date,
    )


@router.post("/milestones/{milestone_id}/complete")
async def complete_milestone(
    milestone_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> MilestoneResponse:
    """Complete a milestone."""
    from sqlalchemy import select
    from nexus.goals.models import Milestone

    service = GoalsService(db)

    # SECURITY: Verify ownership before completing milestone
    result = await db.execute(
        select(Milestone).where(Milestone.id == milestone_id)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Milestone not found")

    goal = await service.get_goal(existing.goal_id)
    if not goal or goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to complete this milestone")

    try:
        milestone = await service.complete_milestone(milestone_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return MilestoneResponse(
        id=milestone.id,
        goal_id=milestone.goal_id,
        title=milestone.title,
        description=milestone.description,
        order=milestone.order,
        weight=milestone.weight,
        is_completed=milestone.is_completed,
        completed_at=milestone.completed_at,
        target_date=milestone.target_date,
    )


# ==================== Blockers ====================


@router.post("/{goal_id}/blockers", status_code=201)
async def add_blocker(
    goal_id: UUID,
    request: BlockerRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> BlockerResponse:
    """Add a blocker to a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before adding blocker
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this goal")

    blocker = await service.add_blocker(
        goal_id=goal_id,
        title=request.title,
        blocker_type=request.blocker_type,
        description=request.description,
        severity=request.severity,
        blocking_agent_id=request.blocking_agent_id,
        blocking_goal_id=request.blocking_goal_id,
    )

    return BlockerResponse(
        id=blocker.id,
        goal_id=blocker.goal_id,
        title=blocker.title,
        description=blocker.description,
        blocker_type=blocker.blocker_type,
        severity=blocker.severity,
        is_resolved=blocker.is_resolved,
        resolution=blocker.resolution,
        resolved_at=blocker.resolved_at,
    )


@router.get("/{goal_id}/blockers")
async def list_blockers(
    goal_id: UUID,
    include_resolved: bool = False,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[BlockerResponse]:
    """List blockers for a goal."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before viewing blockers
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this goal's blockers")

    blockers = await service.get_blockers(goal_id, include_resolved)

    return [
        BlockerResponse(
            id=b.id,
            goal_id=b.goal_id,
            title=b.title,
            description=b.description,
            blocker_type=b.blocker_type,
            severity=b.severity,
            is_resolved=b.is_resolved,
            resolution=b.resolution,
            resolved_at=b.resolved_at,
        )
        for b in blockers
    ]


@router.post("/blockers/{blocker_id}/resolve")
async def resolve_blocker(
    blocker_id: UUID,
    request: ResolveBlockerRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> BlockerResponse:
    """Resolve a blocker."""
    from sqlalchemy import select
    from nexus.goals.models import Blocker

    service = GoalsService(db)

    # SECURITY: Verify ownership before resolving blocker
    result = await db.execute(
        select(Blocker).where(Blocker.id == blocker_id)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Blocker not found")

    goal = await service.get_goal(existing.goal_id)
    if not goal or goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to resolve this blocker")

    try:
        blocker = await service.resolve_blocker(blocker_id, request.resolution)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return BlockerResponse(
        id=blocker.id,
        goal_id=blocker.goal_id,
        title=blocker.title,
        description=blocker.description,
        blocker_type=blocker.blocker_type,
        severity=blocker.severity,
        is_resolved=blocker.is_resolved,
        resolution=blocker.resolution,
        resolved_at=blocker.resolved_at,
    )


# ==================== Delegations ====================


@router.post("/{goal_id}/delegate", status_code=201)
async def delegate_goal(
    goal_id: UUID,
    request: DelegationRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Delegate part of a goal to another agent."""
    service = GoalsService(db)

    # SECURITY: Verify ownership before delegating
    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to delegate from this goal")

    delegation = await service.delegate(
        goal_id=goal_id,
        delegator_id=agent.id,
        delegate_id=request.delegate_id,
        title=request.title,
        description=request.description,
        scope=request.scope,
        deadline=request.deadline,
        constraints=request.constraints,
    )

    return DelegationResponse(
        id=delegation.id,
        goal_id=delegation.goal_id,
        delegator_id=delegation.delegator_id,
        delegate_id=delegation.delegate_id,
        title=delegation.title,
        status=delegation.status,
        deadline=delegation.deadline,
        created_goal_id=delegation.created_goal_id,
        created_at=delegation.created_at,
    )


@router.get("/delegations/incoming")
async def list_incoming_delegations(
    status: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[DelegationResponse]:
    """List delegations assigned to me."""
    service = GoalsService(db)
    delegations = await service.get_delegations_to(agent.id, status)

    return [
        DelegationResponse(
            id=d.id,
            goal_id=d.goal_id,
            delegator_id=d.delegator_id,
            delegate_id=d.delegate_id,
            title=d.title,
            status=d.status,
            deadline=d.deadline,
            created_goal_id=d.created_goal_id,
            created_at=d.created_at,
        )
        for d in delegations
    ]


@router.post("/delegations/{delegation_id}/accept")
async def accept_delegation(
    delegation_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Accept a delegation."""
    service = GoalsService(db)

    try:
        delegation = await service.accept_delegation(delegation_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DelegationResponse(
        id=delegation.id,
        goal_id=delegation.goal_id,
        delegator_id=delegation.delegator_id,
        delegate_id=delegation.delegate_id,
        title=delegation.title,
        status=delegation.status,
        deadline=delegation.deadline,
        created_goal_id=delegation.created_goal_id,
        created_at=delegation.created_at,
    )


@router.post("/delegations/{delegation_id}/reject")
async def reject_delegation(
    delegation_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """Reject a delegation."""
    service = GoalsService(db)

    try:
        delegation = await service.reject_delegation(delegation_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DelegationResponse(
        id=delegation.id,
        goal_id=delegation.goal_id,
        delegator_id=delegation.delegator_id,
        delegate_id=delegation.delegate_id,
        title=delegation.title,
        status=delegation.status,
        deadline=delegation.deadline,
        created_goal_id=delegation.created_goal_id,
        created_at=delegation.created_at,
    )
