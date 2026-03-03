"""Workflow execution service."""

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.workflows.models import (
    Workflow,
    WorkflowStatus,
    WorkflowRun,
    WorkflowStep,
    RunStatus,
)
from nexus.messaging.service import MessagingService


class WorkflowService:
    """Service for managing and executing workflows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Workflow CRUD ---

    async def create_workflow(
        self,
        owner_agent_id: UUID,
        name: str,
        description: str | None = None,
        steps: list[dict] | None = None,
        input_schema: dict | None = None,
        timeout_seconds: int = 300,
    ) -> Workflow:
        """Create a new workflow."""
        workflow = Workflow(
            owner_agent_id=owner_agent_id,
            name=name,
            description=description,
            steps=steps or [],
            input_schema=input_schema,
            timeout_seconds=timeout_seconds,
            status=WorkflowStatus.DRAFT,
        )
        self.db.add(workflow)
        await self.db.flush()
        return workflow

    async def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        """Get a workflow by ID."""
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def list_workflows(
        self,
        owner_agent_id: UUID | None = None,
        include_public: bool = False,
        limit: int = 50,
    ) -> list[Workflow]:
        """List workflows."""
        query = select(Workflow)

        if owner_agent_id and include_public:
            query = query.where(
                (Workflow.owner_agent_id == owner_agent_id) |
                (Workflow.is_public == True)
            )
        elif owner_agent_id:
            query = query.where(Workflow.owner_agent_id == owner_agent_id)
        elif include_public:
            query = query.where(Workflow.is_public == True)

        query = query.order_by(Workflow.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_workflow(
        self,
        workflow_id: UUID,
        owner_agent_id: UUID,
        **updates,
    ) -> Workflow | None:
        """Update a workflow."""
        result = await self.db.execute(
            select(Workflow).where(
                Workflow.id == workflow_id,
                Workflow.owner_agent_id == owner_agent_id,
            )
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            return None

        for key, value in updates.items():
            if hasattr(workflow, key) and value is not None:
                setattr(workflow, key, value)

        workflow.updated_at = datetime.now(timezone.utc)
        return workflow

    async def delete_workflow(self, workflow_id: UUID, owner_agent_id: UUID) -> bool:
        """Delete a workflow."""
        result = await self.db.execute(
            select(Workflow).where(
                Workflow.id == workflow_id,
                Workflow.owner_agent_id == owner_agent_id,
            )
        )
        workflow = result.scalar_one_or_none()
        if workflow:
            await self.db.delete(workflow)
            return True
        return False

    # --- Workflow Execution ---

    async def run_workflow(
        self,
        workflow_id: UUID,
        triggered_by: UUID,
        input_data: dict[str, Any],
    ) -> WorkflowRun:
        """Start a workflow execution."""
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Workflow is not active (status: {workflow.status})")

        # Create run
        run = WorkflowRun(
            workflow_id=workflow_id,
            triggered_by=triggered_by,
            input_data=input_data,
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()

        # Execute steps
        try:
            await self._execute_workflow(workflow, run)
        except Exception as e:
            run.status = RunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)

        return run

    async def _execute_workflow(self, workflow: Workflow, run: WorkflowRun):
        """Execute all steps in a workflow."""
        context = {"input": run.input_data}
        messaging = MessagingService(self.db)

        for i, step_def in enumerate(workflow.steps):
            run.current_step = i

            # Create step execution record
            step = WorkflowStep(
                run_id=run.id,
                step_id=step_def.get("id", f"step-{i}"),
                step_index=i,
                agent_id=UUID(step_def["agent_id"]),
                capability=step_def["capability"],
                status="running",
                started_at=datetime.now(timezone.utc),
            )

            # Resolve input mapping
            step.input_data = self._resolve_mapping(
                step_def.get("input_mapping", {}),
                context,
            )

            self.db.add(step)
            await self.db.flush()

            try:
                # Invoke the capability
                invocation = await messaging.invoke_capability(
                    caller_agent_id=workflow.owner_agent_id,
                    target_agent_id=UUID(step_def["agent_id"]),
                    capability_name=step_def["capability"],
                    input_data=step.input_data,
                    timeout_seconds=workflow.timeout_seconds // len(workflow.steps),
                )

                # Wait for completion (poll)
                # In production, this would use async completion
                step.output_data = invocation.output_data or {}
                step.status = "completed"
                step.completed_at = datetime.now(timezone.utc)

                # Add output to context
                output_key = step_def.get("output_key", f"step{i}")
                context[output_key] = step.output_data

            except Exception as e:
                step.status = "failed"
                step.error_message = str(e)
                step.completed_at = datetime.now(timezone.utc)
                raise

        # All steps completed
        run.status = RunStatus.COMPLETED
        run.output_data = context
        run.completed_at = datetime.now(timezone.utc)

    def _resolve_mapping(
        self,
        mapping: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve template expressions in input mapping."""
        result = {}
        for key, value in mapping.items():
            if isinstance(value, str):
                result[key] = self._resolve_expression(value, context)
            elif isinstance(value, dict):
                result[key] = self._resolve_mapping(value, context)
            else:
                result[key] = value
        return result

    def _resolve_expression(self, expr: str, context: dict[str, Any]) -> Any:
        """Resolve a template expression like {{input.text}}."""
        pattern = r'\{\{([^}]+)\}\}'

        def replacer(match):
            path = match.group(1).strip()
            parts = path.split('.')
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return match.group(0)
            return str(value) if value is not None else ""

        result = re.sub(pattern, replacer, expr)

        # If entire expression was a single reference, return original type
        if re.fullmatch(pattern, expr.strip()):
            path = expr.strip()[2:-2].strip()
            parts = path.split('.')
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return result
            return value

        return result

    # --- Run Management ---

    async def get_run(self, run_id: UUID) -> WorkflowRun | None:
        """Get a workflow run by ID."""
        result = await self.db.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        workflow_id: UUID | None = None,
        triggered_by: UUID | None = None,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        """List workflow runs."""
        query = select(WorkflowRun)
        if workflow_id:
            query = query.where(WorkflowRun.workflow_id == workflow_id)
        if triggered_by:
            query = query.where(WorkflowRun.triggered_by == triggered_by)
        query = query.order_by(WorkflowRun.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())
