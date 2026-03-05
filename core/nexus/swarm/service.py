"""Swarm service for multi-terminal coordination."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nexus.swarm.models import (
    MemberRole,
    MemberStatus,
    Swarm,
    SwarmMember,
    SwarmStatus,
    SwarmTask,
    SwarmTaskResult,
    TaskStatus,
)

if TYPE_CHECKING:
    pass


class SwarmService:
    """Service for managing swarms and task distribution."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Swarm Management ====================

    async def create_swarm(
        self,
        name: str,
        owner_agent_id: UUID,
        config: dict | None = None,
    ) -> tuple[Swarm, SwarmMember]:
        """Create a new swarm and add the owner as leader."""
        swarm = Swarm(
            name=name,
            owner_agent_id=owner_agent_id,
            config=config or {},
            status=SwarmStatus.ACTIVE,
        )
        self.db.add(swarm)
        await self.db.flush()

        # Add owner as leader
        leader = SwarmMember(
            swarm_id=swarm.id,
            agent_id=owner_agent_id,
            role=MemberRole.LEADER,
            status=MemberStatus.IDLE,
            capabilities=[],
        )
        self.db.add(leader)
        await self.db.commit()
        await self.db.refresh(swarm)
        await self.db.refresh(leader)

        return swarm, leader

    async def get_swarm(self, swarm_id: UUID) -> Swarm | None:
        """Get a swarm by ID."""
        result = await self.db.execute(
            select(Swarm)
            .options(selectinload(Swarm.members), selectinload(Swarm.tasks))
            .where(Swarm.id == swarm_id)
        )
        return result.scalar_one_or_none()

    async def get_swarm_by_code(self, join_code: str) -> Swarm | None:
        """Get a swarm by join code."""
        result = await self.db.execute(
            select(Swarm)
            .options(selectinload(Swarm.members))
            .where(Swarm.join_code == join_code)  # Join codes are case-sensitive
        )
        return result.scalar_one_or_none()

    async def join_swarm(
        self,
        join_code: str,
        agent_id: UUID,
        capabilities: list[str] | None = None,
    ) -> SwarmMember:
        """Join an existing swarm."""
        swarm = await self.get_swarm_by_code(join_code)
        if not swarm:
            raise ValueError("Invalid join code")

        if swarm.status != SwarmStatus.ACTIVE:
            raise ValueError(f"Swarm is {swarm.status.value}")

        # Check if already a member
        existing = await self.db.execute(
            select(SwarmMember).where(
                and_(
                    SwarmMember.swarm_id == swarm.id,
                    SwarmMember.agent_id == agent_id,
                    SwarmMember.left_at.is_(None),
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Already a member of this swarm")

        # Check max members
        max_members = swarm.config.get("max_members", 100) if swarm.config else 100
        active_count = await self._count_active_members(swarm.id)
        if active_count >= max_members:
            raise ValueError("Swarm is full")

        member = SwarmMember(
            swarm_id=swarm.id,
            agent_id=agent_id,
            role=MemberRole.WORKER,
            status=MemberStatus.IDLE,
            capabilities=capabilities or [],
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)

        return member

    async def leave_swarm(self, swarm_id: UUID, member_id: UUID) -> None:
        """Leave a swarm."""
        member = await self._get_member(member_id)
        if not member or member.swarm_id != swarm_id:
            raise ValueError("Member not found in swarm")

        # Reassign any current task
        if member.current_task_id:
            await self._reassign_task(member.current_task_id)

        member.status = MemberStatus.DISCONNECTED
        member.left_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def disband_swarm(self, swarm_id: UUID, agent_id: UUID) -> None:
        """Disband a swarm (leader only)."""
        swarm = await self.get_swarm(swarm_id)
        if not swarm:
            raise ValueError("Swarm not found")

        if swarm.owner_agent_id != agent_id:
            raise ValueError("Only the swarm owner can disband")

        swarm.status = SwarmStatus.DISBANDED
        swarm.disbanded_at = datetime.now(timezone.utc)

        # Mark all members as disconnected
        await self.db.execute(
            update(SwarmMember)
            .where(
                and_(
                    SwarmMember.swarm_id == swarm_id,
                    SwarmMember.left_at.is_(None),
                )
            )
            .values(
                status=MemberStatus.DISCONNECTED,
                left_at=datetime.now(timezone.utc),
            )
        )

        # Cancel pending tasks
        await self.db.execute(
            update(SwarmTask)
            .where(
                and_(
                    SwarmTask.swarm_id == swarm_id,
                    SwarmTask.status.in_([TaskStatus.PENDING, TaskStatus.ASSIGNED]),
                )
            )
            .values(status=TaskStatus.FAILED)
        )

        await self.db.commit()

    # ==================== Task Management ====================

    async def submit_task(
        self,
        swarm_id: UUID,
        title: str,
        description: str | None = None,
        task_type: str = "general",
        priority: int = 5,
        input_data: dict | None = None,
        required_capabilities: list[str] | None = None,
        timeout_seconds: int = 300,
        max_retries: int = 3,
        parent_task_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> SwarmTask:
        """Submit a task to the swarm."""
        task = SwarmTask(
            swarm_id=swarm_id,
            parent_task_id=parent_task_id,
            title=title,
            description=description,
            task_type=task_type,
            priority=priority,
            input_data=input_data or {},
            required_capabilities=required_capabilities or [],
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            created_by=created_by,
            status=TaskStatus.PENDING,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        return task

    async def submit_batch(
        self,
        swarm_id: UUID,
        tasks: list[dict],
        created_by: UUID | None = None,
    ) -> list[SwarmTask]:
        """Submit multiple tasks at once."""
        created_tasks = []
        for task_data in tasks:
            task = await self.submit_task(
                swarm_id=swarm_id,
                created_by=created_by,
                **task_data,
            )
            created_tasks.append(task)
        return created_tasks

    async def claim_task(self, member_id: UUID) -> SwarmTask | None:
        """Claim the next available task for a member."""
        member = await self._get_member(member_id)
        if not member:
            raise ValueError("Member not found")

        if member.status == MemberStatus.BUSY:
            return None

        # Find best matching task
        task = await self._find_best_task(member)
        if not task:
            return None

        # Assign task to member
        task.status = TaskStatus.ASSIGNED
        task.assigned_to = member_id
        task.assigned_at = datetime.now(timezone.utc)

        member.status = MemberStatus.BUSY
        member.current_task_id = task.id

        await self.db.commit()
        await self.db.refresh(task)

        return task

    async def start_task(self, task_id: UUID, member_id: UUID) -> SwarmTask:
        """Mark a task as in progress."""
        task = await self._get_task(task_id)
        if not task:
            raise ValueError("Task not found")

        if task.assigned_to != member_id:
            raise ValueError("Task not assigned to this member")

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)

        return task

    async def complete_task(
        self,
        task_id: UUID,
        member_id: UUID,
        output_data: dict | None = None,
        success: bool = True,
        error_message: str | None = None,
        execution_time_ms: int = 0,
    ) -> SwarmTaskResult:
        """Mark a task as complete."""
        task = await self._get_task(task_id)
        if not task:
            raise ValueError("Task not found")

        if task.assigned_to != member_id:
            raise ValueError("Task not assigned to this member")

        member = await self._get_member(member_id)

        # Update task
        task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        task.completed_at = datetime.now(timezone.utc)

        # Create result
        result = SwarmTaskResult(
            task_id=task_id,
            member_id=member_id,
            output_data=output_data or {},
            success=success,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
        )
        self.db.add(result)

        # Update member
        if member:
            member.status = MemberStatus.IDLE
            member.current_task_id = None
            member.tasks_completed += 1

        await self.db.commit()
        await self.db.refresh(result)

        return result

    async def fail_task(
        self,
        task_id: UUID,
        member_id: UUID,
        error_message: str,
    ) -> SwarmTask:
        """Mark a task as failed, potentially retry."""
        task = await self._get_task(task_id)
        if not task:
            raise ValueError("Task not found")

        member = await self._get_member(member_id)

        # Clear member assignment
        if member:
            member.status = MemberStatus.IDLE
            member.current_task_id = None

        # Check if can retry
        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.REASSIGNED
            task.assigned_to = None
            task.assigned_at = None
            task.started_at = None
            # Will be picked up by next claim
            task.status = TaskStatus.PENDING
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(timezone.utc)
            # Create failure result
            result = SwarmTaskResult(
                task_id=task_id,
                member_id=member_id,
                output_data={},
                success=False,
                error_message=error_message,
                execution_time_ms=0,
            )
            self.db.add(result)

        await self.db.commit()
        await self.db.refresh(task)

        return task

    async def get_task(self, task_id: UUID) -> SwarmTask | None:
        """Get a task by ID."""
        return await self._get_task(task_id)

    async def list_tasks(
        self,
        swarm_id: UUID,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[SwarmTask]:
        """List tasks in a swarm."""
        query = select(SwarmTask).where(SwarmTask.swarm_id == swarm_id)
        if status:
            query = query.where(SwarmTask.status == status)
        query = query.order_by(SwarmTask.priority.desc(), SwarmTask.created_at)
        query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_results(self, swarm_id: UUID) -> list[SwarmTaskResult]:
        """Get all results for a swarm."""
        result = await self.db.execute(
            select(SwarmTaskResult)
            .join(SwarmTask)
            .where(SwarmTask.swarm_id == swarm_id)
            .order_by(SwarmTaskResult.created_at)
        )
        return list(result.scalars().all())

    # ==================== Member Management ====================

    async def heartbeat(self, member_id: UUID) -> SwarmMember:
        """Update member heartbeat."""
        member = await self._get_member(member_id)
        if not member:
            raise ValueError("Member not found")

        member.last_heartbeat = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(member)

        return member

    async def check_stale_members(
        self,
        swarm_id: UUID,
        timeout_seconds: int = 60,
    ) -> list[SwarmMember]:
        """Find and mark stale members, reassign their tasks."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)

        result = await self.db.execute(
            select(SwarmMember).where(
                and_(
                    SwarmMember.swarm_id == swarm_id,
                    SwarmMember.status != MemberStatus.DISCONNECTED,
                    SwarmMember.last_heartbeat < cutoff,
                    SwarmMember.left_at.is_(None),
                )
            )
        )
        stale_members = list(result.scalars().all())

        for member in stale_members:
            member.status = MemberStatus.DISCONNECTED
            if member.current_task_id:
                await self._reassign_task(member.current_task_id)

        if stale_members:
            await self.db.commit()

        return stale_members

    async def get_member(self, member_id: UUID) -> SwarmMember | None:
        """Get a member by ID."""
        return await self._get_member(member_id)

    async def get_member_by_agent(
        self,
        swarm_id: UUID,
        agent_id: UUID,
    ) -> SwarmMember | None:
        """Get a member by agent ID."""
        result = await self.db.execute(
            select(SwarmMember).where(
                and_(
                    SwarmMember.swarm_id == swarm_id,
                    SwarmMember.agent_id == agent_id,
                    SwarmMember.left_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_members(self, swarm_id: UUID) -> list[SwarmMember]:
        """List all active members of a swarm."""
        result = await self.db.execute(
            select(SwarmMember).where(
                and_(
                    SwarmMember.swarm_id == swarm_id,
                    SwarmMember.left_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    # ==================== Stats ====================

    async def get_swarm_stats(self, swarm_id: UUID) -> dict:
        """Get statistics for a swarm."""
        # Count tasks by status
        task_counts = await self.db.execute(
            select(SwarmTask.status, func.count(SwarmTask.id))
            .where(SwarmTask.swarm_id == swarm_id)
            .group_by(SwarmTask.status)
        )
        status_counts = {status.value: count for status, count in task_counts.all()}

        # Count active members
        member_count = await self._count_active_members(swarm_id)

        return {
            "member_count": member_count,
            "pending_tasks": status_counts.get("pending", 0),
            "assigned_tasks": status_counts.get("assigned", 0),
            "in_progress_tasks": status_counts.get("in_progress", 0),
            "completed_tasks": status_counts.get("completed", 0),
            "failed_tasks": status_counts.get("failed", 0),
            "total_tasks": sum(status_counts.values()),
        }

    # ==================== Private Helpers ====================

    async def _get_member(self, member_id: UUID) -> SwarmMember | None:
        """Get a member by ID."""
        result = await self.db.execute(
            select(SwarmMember).where(SwarmMember.id == member_id)
        )
        return result.scalar_one_or_none()

    async def _get_task(self, task_id: UUID) -> SwarmTask | None:
        """Get a task by ID."""
        result = await self.db.execute(
            select(SwarmTask)
            .options(selectinload(SwarmTask.result))
            .where(SwarmTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def _count_active_members(self, swarm_id: UUID) -> int:
        """Count active members in a swarm."""
        result = await self.db.execute(
            select(func.count(SwarmMember.id)).where(
                and_(
                    SwarmMember.swarm_id == swarm_id,
                    SwarmMember.left_at.is_(None),
                    SwarmMember.status != MemberStatus.DISCONNECTED,
                )
            )
        )
        return result.scalar() or 0

    async def _find_best_task(self, member: SwarmMember) -> SwarmTask | None:
        """Find the best task for a member based on capabilities and load balancing."""
        # Build query for pending tasks
        query = (
            select(SwarmTask)
            .where(
                and_(
                    SwarmTask.swarm_id == member.swarm_id,
                    SwarmTask.status == TaskStatus.PENDING,
                )
            )
            .order_by(SwarmTask.priority.desc(), SwarmTask.created_at)
        )

        result = await self.db.execute(query)
        tasks = list(result.scalars().all())

        # Filter by capabilities
        for task in tasks:
            if not task.required_capabilities:
                return task
            if all(cap in member.capabilities for cap in task.required_capabilities):
                return task

        return None

    async def _reassign_task(self, task_id: UUID) -> None:
        """Reassign a task back to pending."""
        task = await self._get_task(task_id)
        if task and task.status in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]:
            task.status = TaskStatus.PENDING
            task.assigned_to = None
            task.assigned_at = None
            task.started_at = None
            task.retry_count += 1
