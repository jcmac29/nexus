"""Goals service for persistent objectives."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nexus.goals.models import (
    Blocker,
    Delegation,
    Goal,
    GoalPriority,
    GoalStatus,
    Milestone,
)

if TYPE_CHECKING:
    pass


class GoalsService:
    """Service for managing agent goals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Goals ====================

    async def create_goal(
        self,
        agent_id: UUID,
        title: str,
        description: str | None = None,
        success_criteria: str | None = None,
        goal_type: str = "general",
        tags: list[str] | None = None,
        priority: GoalPriority = GoalPriority.MEDIUM,
        target_date: datetime | None = None,
        parent_goal_id: UUID | None = None,
        config: dict | None = None,
        constraints: dict | None = None,
    ) -> Goal:
        """Create a new goal."""
        goal = Goal(
            agent_id=agent_id,
            parent_goal_id=parent_goal_id,
            title=title,
            description=description,
            success_criteria=success_criteria,
            goal_type=goal_type,
            tags=tags or [],
            priority=priority,
            target_date=target_date,
            config=config or {},
            constraints=constraints or {},
            status=GoalStatus.DRAFT,
        )
        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def get_goal(self, goal_id: UUID) -> Goal | None:
        """Get a goal by ID."""
        result = await self.db.execute(
            select(Goal)
            .options(
                selectinload(Goal.milestones),
                selectinload(Goal.blockers),
                selectinload(Goal.delegations),
            )
            .where(Goal.id == goal_id)
        )
        return result.scalar_one_or_none()

    async def list_goals(
        self,
        agent_id: UUID,
        status: GoalStatus | None = None,
        priority: GoalPriority | None = None,
        include_completed: bool = False,
        limit: int = 100,
    ) -> list[Goal]:
        """List goals for an agent."""
        query = select(Goal).where(Goal.agent_id == agent_id)

        if status:
            query = query.where(Goal.status == status)
        elif not include_completed:
            query = query.where(
                Goal.status.not_in([GoalStatus.COMPLETED, GoalStatus.CANCELLED, GoalStatus.FAILED])
            )

        if priority:
            query = query.where(Goal.priority == priority)

        query = query.order_by(Goal.priority.desc(), Goal.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_goal(
        self,
        goal_id: UUID,
        title: str | None = None,
        description: str | None = None,
        success_criteria: str | None = None,
        priority: GoalPriority | None = None,
        target_date: datetime | None = None,
        config: dict | None = None,
        constraints: dict | None = None,
    ) -> Goal:
        """Update a goal."""
        goal = await self.get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found")

        if title:
            goal.title = title
        if description is not None:
            goal.description = description
        if success_criteria is not None:
            goal.success_criteria = success_criteria
        if priority:
            goal.priority = priority
        if target_date is not None:
            goal.target_date = target_date
        if config is not None:
            goal.config = config
        if constraints is not None:
            goal.constraints = constraints

        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def activate_goal(self, goal_id: UUID) -> Goal:
        """Activate a goal (move from draft to active)."""
        goal = await self.get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found")

        goal.status = GoalStatus.ACTIVE
        goal.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def start_goal(self, goal_id: UUID) -> Goal:
        """Start working on a goal."""
        goal = await self.get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found")

        goal.status = GoalStatus.IN_PROGRESS
        if not goal.started_at:
            goal.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def update_progress(
        self,
        goal_id: UUID,
        progress_percent: int,
        progress_notes: str | None = None,
    ) -> Goal:
        """Update goal progress."""
        goal = await self.get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found")

        goal.progress_percent = min(100, max(0, progress_percent))
        if progress_notes:
            goal.progress_notes = progress_notes

        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def complete_goal(
        self,
        goal_id: UUID,
        outcome: str | None = None,
        outcome_data: dict | None = None,
    ) -> Goal:
        """Complete a goal."""
        goal = await self.get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found")

        goal.status = GoalStatus.COMPLETED
        goal.progress_percent = 100
        goal.completed_at = datetime.now(timezone.utc)
        goal.outcome = outcome
        goal.outcome_data = outcome_data or {}

        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def fail_goal(
        self,
        goal_id: UUID,
        outcome: str | None = None,
    ) -> Goal:
        """Mark a goal as failed."""
        goal = await self.get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found")

        goal.status = GoalStatus.FAILED
        goal.completed_at = datetime.now(timezone.utc)
        goal.outcome = outcome

        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def cancel_goal(self, goal_id: UUID, reason: str | None = None) -> Goal:
        """Cancel a goal."""
        goal = await self.get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found")

        goal.status = GoalStatus.CANCELLED
        goal.completed_at = datetime.now(timezone.utc)
        goal.outcome = reason

        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    # ==================== Milestones ====================

    async def add_milestone(
        self,
        goal_id: UUID,
        title: str,
        description: str | None = None,
        order: int = 0,
        weight: float = 1.0,
        target_date: datetime | None = None,
    ) -> Milestone:
        """Add a milestone to a goal."""
        milestone = Milestone(
            goal_id=goal_id,
            title=title,
            description=description,
            order=order,
            weight=weight,
            target_date=target_date,
        )
        self.db.add(milestone)
        await self.db.commit()
        await self.db.refresh(milestone)

        return milestone

    async def complete_milestone(self, milestone_id: UUID) -> Milestone:
        """Complete a milestone."""
        result = await self.db.execute(
            select(Milestone).where(Milestone.id == milestone_id)
        )
        milestone = result.scalar_one_or_none()

        if not milestone:
            raise ValueError("Milestone not found")

        milestone.is_completed = True
        milestone.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(milestone)

        # Update goal progress based on milestones
        await self._update_goal_progress_from_milestones(milestone.goal_id)

        return milestone

    async def _update_goal_progress_from_milestones(self, goal_id: UUID) -> None:
        """Update goal progress based on completed milestones."""
        result = await self.db.execute(
            select(Milestone).where(Milestone.goal_id == goal_id)
        )
        milestones = list(result.scalars().all())

        if not milestones:
            return

        total_weight = sum(m.weight for m in milestones)
        completed_weight = sum(m.weight for m in milestones if m.is_completed)

        if total_weight > 0:
            progress = int((completed_weight / total_weight) * 100)
            await self.update_progress(goal_id, progress)

    # ==================== Blockers ====================

    async def add_blocker(
        self,
        goal_id: UUID,
        title: str,
        blocker_type: str,
        description: str | None = None,
        severity: str = "medium",
        blocking_agent_id: UUID | None = None,
        blocking_goal_id: UUID | None = None,
    ) -> Blocker:
        """Add a blocker to a goal."""
        blocker = Blocker(
            goal_id=goal_id,
            title=title,
            description=description,
            blocker_type=blocker_type,
            severity=severity,
            blocking_agent_id=blocking_agent_id,
            blocking_goal_id=blocking_goal_id,
        )
        self.db.add(blocker)

        # Update goal status
        goal = await self.get_goal(goal_id)
        if goal and goal.status == GoalStatus.IN_PROGRESS:
            goal.status = GoalStatus.BLOCKED

        await self.db.commit()
        await self.db.refresh(blocker)

        return blocker

    async def resolve_blocker(
        self,
        blocker_id: UUID,
        resolution: str,
    ) -> Blocker:
        """Resolve a blocker."""
        result = await self.db.execute(
            select(Blocker).where(Blocker.id == blocker_id)
        )
        blocker = result.scalar_one_or_none()

        if not blocker:
            raise ValueError("Blocker not found")

        blocker.is_resolved = True
        blocker.resolution = resolution
        blocker.resolved_at = datetime.now(timezone.utc)

        # Check if all blockers are resolved
        remaining = await self.db.execute(
            select(func.count(Blocker.id)).where(
                and_(
                    Blocker.goal_id == blocker.goal_id,
                    Blocker.is_resolved == False,
                )
            )
        )
        if remaining.scalar() == 0:
            goal = await self.get_goal(blocker.goal_id)
            if goal and goal.status == GoalStatus.BLOCKED:
                goal.status = GoalStatus.IN_PROGRESS

        await self.db.commit()
        await self.db.refresh(blocker)

        return blocker

    async def get_blockers(
        self,
        goal_id: UUID,
        include_resolved: bool = False,
    ) -> list[Blocker]:
        """Get blockers for a goal."""
        query = select(Blocker).where(Blocker.goal_id == goal_id)
        if not include_resolved:
            query = query.where(Blocker.is_resolved == False)
        query = query.order_by(Blocker.severity.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Delegations ====================

    async def delegate(
        self,
        goal_id: UUID,
        delegator_id: UUID,
        delegate_id: UUID,
        title: str,
        description: str | None = None,
        scope: dict | None = None,
        deadline: datetime | None = None,
        constraints: dict | None = None,
    ) -> Delegation:
        """Delegate part of a goal to another agent."""
        delegation = Delegation(
            goal_id=goal_id,
            delegator_id=delegator_id,
            delegate_id=delegate_id,
            title=title,
            description=description,
            scope=scope or {},
            deadline=deadline,
            constraints=constraints or {},
            status="pending",
        )
        self.db.add(delegation)
        await self.db.commit()
        await self.db.refresh(delegation)

        return delegation

    async def accept_delegation(
        self,
        delegation_id: UUID,
        delegate_id: UUID,
    ) -> Delegation:
        """Accept a delegation."""
        result = await self.db.execute(
            select(Delegation).where(
                and_(
                    Delegation.id == delegation_id,
                    Delegation.delegate_id == delegate_id,
                )
            )
        )
        delegation = result.scalar_one_or_none()

        if not delegation:
            raise ValueError("Delegation not found")

        delegation.status = "accepted"

        # Create a sub-goal for the delegate
        sub_goal = Goal(
            agent_id=delegate_id,
            parent_goal_id=delegation.goal_id,
            title=delegation.title,
            description=delegation.description,
            constraints=delegation.constraints,
            status=GoalStatus.ACTIVE,
        )
        self.db.add(sub_goal)
        await self.db.flush()

        delegation.created_goal_id = sub_goal.id

        await self.db.commit()
        await self.db.refresh(delegation)

        return delegation

    async def reject_delegation(
        self,
        delegation_id: UUID,
        delegate_id: UUID,
    ) -> Delegation:
        """Reject a delegation."""
        result = await self.db.execute(
            select(Delegation).where(
                and_(
                    Delegation.id == delegation_id,
                    Delegation.delegate_id == delegate_id,
                )
            )
        )
        delegation = result.scalar_one_or_none()

        if not delegation:
            raise ValueError("Delegation not found")

        delegation.status = "rejected"
        await self.db.commit()
        await self.db.refresh(delegation)

        return delegation

    async def complete_delegation(
        self,
        delegation_id: UUID,
        result_data: dict | None = None,
    ) -> Delegation:
        """Complete a delegation."""
        result = await self.db.execute(
            select(Delegation).where(Delegation.id == delegation_id)
        )
        delegation = result.scalar_one_or_none()

        if not delegation:
            raise ValueError("Delegation not found")

        delegation.status = "completed"
        delegation.result = result_data or {}
        delegation.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(delegation)

        return delegation

    async def get_delegations_to(
        self,
        agent_id: UUID,
        status: str | None = None,
    ) -> list[Delegation]:
        """Get delegations assigned to an agent."""
        query = select(Delegation).where(Delegation.delegate_id == agent_id)
        if status:
            query = query.where(Delegation.status == status)
        query = query.order_by(Delegation.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_delegations_from(
        self,
        agent_id: UUID,
        status: str | None = None,
    ) -> list[Delegation]:
        """Get delegations created by an agent."""
        query = select(Delegation).where(Delegation.delegator_id == agent_id)
        if status:
            query = query.where(Delegation.status == status)
        query = query.order_by(Delegation.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())
