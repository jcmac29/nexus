"""Orchestration service for multi-agent coordination."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nexus.orchestration.models import (
    OrchestrationWorkflow as Workflow,
    OrchestrationStep as WorkflowStep,
    OrchestrationExecution as WorkflowExecution,
    OrchestrationStepExecution as StepExecution,
    WorkflowStatus,
    ExecutionStatus,
    StepType,
)


class OrchestrationService:
    """Service for orchestrating multi-agent workflows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_workflow(
        self,
        name: str,
        slug: str,
        owner_id: UUID,
        description: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        config: dict | None = None,
    ) -> Workflow:
        """Create a new workflow definition."""
        workflow = Workflow(
            name=name,
            slug=slug,
            description=description,
            owner_id=owner_id,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            config=config or {},
        )
        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)
        return workflow

    async def add_step(
        self,
        workflow_id: UUID,
        name: str,
        step_type: StepType,
        order: int,
        config: dict | None = None,
        target_id: UUID | None = None,
        target_type: str | None = None,
        capability: str | None = None,
        input_mapping: dict | None = None,
        output_mapping: dict | None = None,
        condition: str | None = None,
        on_error: str = "fail",
        timeout: int | None = None,
    ) -> WorkflowStep:
        """Add a step to a workflow."""
        step = WorkflowStep(
            workflow_id=workflow_id,
            name=name,
            step_type=step_type,
            order=order,
            config=config or {},
            target_id=target_id,
            target_type=target_type,
            capability=capability,
            input_mapping=input_mapping or {},
            output_mapping=output_mapping or {},
            condition=condition,
            on_error=on_error,
            timeout=timeout,
        )
        self.db.add(step)
        await self.db.commit()
        await self.db.refresh(step)
        return step

    async def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        """Get a workflow with its steps."""
        result = await self.db.execute(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps))
        )
        return result.scalar_one_or_none()

    async def start_execution(
        self,
        workflow_id: UUID,
        input_data: dict,
        triggered_by: UUID,
        triggered_by_type: str = "agent",
    ) -> WorkflowExecution:
        """Start a new workflow execution."""
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Workflow is not active")

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            triggered_by=triggered_by,
            triggered_by_type=triggered_by_type,
            input_data=input_data,
            state={"input": input_data},
            status=ExecutionStatus.RUNNING,
            started_at=datetime.utcnow(),
            timeout_at=datetime.utcnow() + timedelta(seconds=workflow.default_timeout),
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        # Start executing steps in background
        asyncio.create_task(self._execute_workflow(execution.id))

        return execution

    async def _execute_workflow(self, execution_id: UUID):
        """Execute a workflow (runs in background)."""
        from nexus.database import async_session_maker

        async with async_session_maker() as db:
            service = OrchestrationService(db)

            result = await db.execute(
                select(WorkflowExecution)
                .where(WorkflowExecution.id == execution_id)
                .options(selectinload(WorkflowExecution.workflow).selectinload(Workflow.steps))
            )
            execution = result.scalar_one_or_none()

            if not execution:
                return

            try:
                workflow = execution.workflow
                steps = sorted(workflow.steps, key=lambda s: s.order)

                for step in steps:
                    if execution.status != ExecutionStatus.RUNNING:
                        break

                    # Check timeout
                    if execution.timeout_at and datetime.utcnow() > execution.timeout_at:
                        execution.status = ExecutionStatus.FAILED
                        execution.error = "Execution timed out"
                        break

                    # Execute step
                    execution.current_step_id = step.id
                    await db.commit()

                    result = await service._execute_step(execution, step)

                    # Store result
                    execution.step_results[str(step.id)] = result
                    execution.completed_steps.append(str(step.id))

                    # Apply output mapping
                    if step.output_mapping:
                        for target, source in step.output_mapping.items():
                            value = service._extract_value(result, source)
                            execution.state[target] = value

                    await db.commit()

                # Workflow completed
                if execution.status == ExecutionStatus.RUNNING:
                    execution.status = ExecutionStatus.COMPLETED
                    execution.output_data = execution.state
                    execution.completed_at = datetime.utcnow()

            except Exception as e:
                execution.status = ExecutionStatus.FAILED
                execution.error = str(e)
                execution.error_step_id = execution.current_step_id
                execution.completed_at = datetime.utcnow()

            await db.commit()

    async def _execute_step(
        self,
        execution: WorkflowExecution,
        step: WorkflowStep,
    ) -> dict:
        """Execute a single workflow step."""
        # Build input from mapping
        step_input = {}
        for target, source in step.input_mapping.items():
            value = self._extract_value(execution.state, source)
            step_input[target] = value

        # Add step config
        step_input.update(step.config)

        start_time = time.time()

        # Create step execution record
        step_exec = StepExecution(
            workflow_execution_id=execution.id,
            step_id=step.id,
            status=ExecutionStatus.RUNNING,
            input_data=step_input,
            started_at=datetime.utcnow(),
        )
        self.db.add(step_exec)
        await self.db.flush()

        result = {}

        try:
            if step.step_type == StepType.AGENT_CALL:
                result = await self._execute_agent_call(step, step_input)
            elif step.step_type == StepType.TOOL_CALL:
                result = await self._execute_tool_call(step, step_input)
            elif step.step_type == StepType.PARALLEL:
                result = await self._execute_parallel(execution, step)
            elif step.step_type == StepType.CONDITIONAL:
                result = await self._execute_conditional(execution, step)
            elif step.step_type == StepType.TRANSFORM:
                result = await self._execute_transform(step, step_input, execution.state)
            elif step.step_type == StepType.WAIT:
                result = await self._execute_wait(step)
            elif step.step_type == StepType.HUMAN_INPUT:
                result = await self._execute_human_input(execution, step)
            else:
                result = {"step": step.name, "type": step.step_type.value}

            step_exec.status = ExecutionStatus.COMPLETED
            step_exec.output_data = result

        except Exception as e:
            step_exec.status = ExecutionStatus.FAILED
            step_exec.error = str(e)

            if step.on_error == "fail":
                raise
            elif step.on_error == "retry" and step_exec.attempt < step.retry_count:
                await asyncio.sleep(step.retry_delay)
                step_exec.attempt += 1
                return await self._execute_step(execution, step)
            # on_error == "continue" - just continue

        step_exec.completed_at = datetime.utcnow()
        step_exec.duration_ms = (time.time() - start_time) * 1000

        return result

    async def _execute_agent_call(self, step: WorkflowStep, input_data: dict) -> dict:
        """Execute an agent capability call."""
        from nexus.discovery.service import DiscoveryService

        # This would invoke the agent's capability
        # Placeholder - integrate with existing invocation system
        return {"agent_id": str(step.target_id), "capability": step.capability, "input": input_data}

    async def _execute_tool_call(self, step: WorkflowStep, input_data: dict) -> dict:
        """Execute a tool call."""
        from nexus.tools.service import ToolService

        # Execute the tool
        service = ToolService(self.db)
        execution = await service.execute_tool(
            tool_id=step.target_id,
            input_data=input_data,
            executor_id=step.workflow_id,
            executor_type="workflow",
        )
        return execution.output_data or {}

    async def _execute_parallel(self, execution: WorkflowExecution, step: WorkflowStep) -> dict:
        """Execute multiple steps in parallel."""
        # Get parallel steps
        parallel_step_ids = step.parallel_steps or []

        tasks = []
        for step_id in parallel_step_ids:
            result = await self.db.execute(
                select(WorkflowStep).where(WorkflowStep.id == UUID(step_id))
            )
            parallel_step = result.scalar_one_or_none()
            if parallel_step:
                tasks.append(self._execute_step(execution, parallel_step))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return {
                f"step_{i}": r if not isinstance(r, Exception) else {"error": str(r)}
                for i, r in enumerate(results)
            }

        return {}

    async def _execute_conditional(self, execution: WorkflowExecution, step: WorkflowStep) -> dict:
        """Execute conditional branching."""
        if not step.condition:
            return {"branch": "default"}

        # SECURITY: Use safe expression evaluation - no arbitrary code execution
        try:
            result = self._safe_eval_condition(step.condition, execution.state)
            return {"branch": "true" if result else "false", "condition_result": bool(result)}
        except Exception as e:
            return {"branch": "error", "error": str(e)}

    def _safe_eval_condition(self, condition: str, state: dict) -> bool:
        """
        Safely evaluate a condition expression without arbitrary code execution.
        Only allows: comparisons, boolean ops, attribute access, literals.
        """
        import ast
        import operator

        # Whitelist of allowed operations
        ALLOWED_OPS = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
            ast.And: lambda a, b: a and b,
            ast.Or: lambda a, b: a or b,
            ast.Not: operator.not_,
            ast.In: lambda a, b: a in b,
            ast.NotIn: lambda a, b: a not in b,
        }

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            elif isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.Name):
                if node.id == 'state':
                    return state
                raise ValueError(f"Unknown variable: {node.id}")
            elif isinstance(node, ast.Subscript):
                value = _eval(node.value)
                key = _eval(node.slice)
                return value[key]
            elif isinstance(node, ast.Attribute):
                value = _eval(node.value)
                # SECURITY: Restrict attribute access to prevent code execution
                # Disallow dunder attributes which can lead to introspection attacks
                if node.attr.startswith('_'):
                    raise ValueError(f"Access to private attributes is not allowed: {node.attr}")
                # Only allow attribute access on dict-like objects for common methods
                allowed_attrs = {'get', 'keys', 'values', 'items'}
                if isinstance(value, dict) and node.attr in allowed_attrs:
                    return getattr(value, node.attr)
                elif isinstance(value, dict):
                    # For dicts, prefer subscript access - attribute names become key lookups
                    return value.get(node.attr)
                raise ValueError(f"Attribute access not allowed on type: {type(value).__name__}")
            elif isinstance(node, ast.Compare):
                left = _eval(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    op_func = ALLOWED_OPS.get(type(op))
                    if not op_func:
                        raise ValueError(f"Disallowed operation: {type(op).__name__}")
                    right = _eval(comparator)
                    if not op_func(left, right):
                        return False
                    left = right
                return True
            elif isinstance(node, ast.BoolOp):
                op_func = ALLOWED_OPS.get(type(node.op))
                if not op_func:
                    raise ValueError(f"Disallowed operation: {type(node.op).__name__}")
                values = [_eval(v) for v in node.values]
                result = values[0]
                for v in values[1:]:
                    result = op_func(result, v)
                return result
            elif isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.Not):
                    return not _eval(node.operand)
                raise ValueError(f"Disallowed operation: {type(node.op).__name__}")
            else:
                raise ValueError(f"Disallowed expression: {type(node).__name__}")

        try:
            tree = ast.parse(condition, mode='eval')
            return bool(_eval(tree))
        except SyntaxError as e:
            raise ValueError(f"Invalid condition syntax: {e}")

    async def _execute_transform(self, step: WorkflowStep, input_data: dict, state: dict) -> dict:
        """Transform data."""
        # Apply transformations defined in config
        transforms = step.config.get("transforms", {})
        result = {}

        for output_key, transform in transforms.items():
            if isinstance(transform, str):
                # Simple field mapping
                result[output_key] = self._extract_value(state, transform)
            elif isinstance(transform, dict):
                # Complex transform
                transform_type = transform.get("type", "copy")
                if transform_type == "concat":
                    parts = [self._extract_value(state, p) for p in transform.get("parts", [])]
                    result[output_key] = "".join(str(p) for p in parts if p)
                elif transform_type == "template":
                    template = transform.get("template", "")
                    # SECURITY: Use safe string substitution instead of .format()
                    # Only substitute explicitly declared variables to prevent injection
                    for var_name in transform.get("variables", []):
                        if var_name in state:
                            template = template.replace(f"{{{var_name}}}", str(state[var_name]))
                    result[output_key] = template

        return result

    async def _execute_wait(self, step: WorkflowStep) -> dict:
        """Wait for a specified duration or event."""
        wait_seconds = step.config.get("seconds", 0)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        return {"waited_seconds": wait_seconds}

    async def _execute_human_input(self, execution: WorkflowExecution, step: WorkflowStep) -> dict:
        """Wait for human input."""
        execution.status = ExecutionStatus.WAITING
        execution.waiting_for_input = True
        execution.input_prompt = step.config.get("prompt", "Please provide input")
        await self.db.commit()

        # Actual input collection handled by external system
        # This is a placeholder
        return {"awaiting_human_input": True}

    def _extract_value(self, data: dict, path: str) -> Any:
        """Extract a value from nested data using dot notation."""
        parts = path.split(".")
        value = data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit():
                idx = int(part)
                value = value[idx] if idx < len(value) else None
            else:
                return None
        return value

    async def get_execution(self, execution_id: UUID) -> WorkflowExecution | None:
        """Get an execution by ID."""
        result = await self.db.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def provide_human_input(
        self,
        execution_id: UUID,
        input_data: dict,
    ) -> WorkflowExecution:
        """Provide human input to a waiting workflow."""
        execution = await self.get_execution(execution_id)
        if not execution:
            raise ValueError("Execution not found")

        if not execution.waiting_for_input:
            raise ValueError("Execution is not waiting for input")

        # Add input to state
        execution.state["human_input"] = input_data
        execution.waiting_for_input = False
        execution.status = ExecutionStatus.RUNNING

        await self.db.commit()

        # Resume execution
        asyncio.create_task(self._execute_workflow(execution_id))

        return execution

    async def cancel_execution(self, execution_id: UUID):
        """Cancel a running execution."""
        execution = await self.get_execution(execution_id)
        if execution:
            execution.status = ExecutionStatus.CANCELLED
            execution.completed_at = datetime.utcnow()
            await self.db.commit()
