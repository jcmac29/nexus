"""Scheduler service for managing cron-like jobs."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from croniter import croniter
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.scheduling.models import ScheduledJob, JobExecution, JobType, JobStatus, ExecutionStatus


class SchedulerService:
    """Service for managing scheduled jobs."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._running = False
        self._task: asyncio.Task | None = None

    async def create_job(
        self,
        name: str,
        job_type: JobType,
        owner_id: UUID,
        config: dict,
        cron_expression: str | None = None,
        interval_seconds: int | None = None,
        run_at: datetime | None = None,
        timezone: str = "UTC",
        max_runs: int | None = None,
        end_date: datetime | None = None,
        description: str | None = None,
        **kwargs,
    ) -> ScheduledJob:
        """Create a new scheduled job."""
        job = ScheduledJob(
            name=name,
            description=description,
            owner_id=owner_id,
            job_type=job_type,
            config=config,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            run_at=run_at,
            timezone=timezone,
            max_runs=max_runs,
            end_date=end_date,
            **kwargs,
        )

        # Calculate next run time
        job.next_run_at = self._calculate_next_run(job)

        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    def _calculate_next_run(self, job: ScheduledJob, after: datetime | None = None) -> datetime | None:
        """Calculate the next run time for a job."""
        base = after or datetime.utcnow()

        if job.run_at:
            # One-time job
            return job.run_at if job.run_at > base else None

        if job.cron_expression:
            try:
                cron = croniter(job.cron_expression, base)
                return cron.get_next(datetime)
            except Exception:
                return None

        if job.interval_seconds:
            if job.last_run_at:
                return job.last_run_at + timedelta(seconds=job.interval_seconds)
            return base + timedelta(seconds=job.interval_seconds)

        return None

    async def get_job(self, job_id: UUID) -> ScheduledJob | None:
        """Get a job by ID."""
        result = await self.db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        owner_id: UUID | None = None,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[ScheduledJob]:
        """List scheduled jobs."""
        query = select(ScheduledJob)

        if owner_id:
            query = query.where(ScheduledJob.owner_id == owner_id)
        if status:
            query = query.where(ScheduledJob.status == status)

        query = query.order_by(ScheduledJob.next_run_at.asc().nullslast()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_due_jobs(self) -> list[ScheduledJob]:
        """Get jobs that are due to run."""
        now = datetime.utcnow()
        result = await self.db.execute(
            select(ScheduledJob).where(
                and_(
                    ScheduledJob.status == JobStatus.ACTIVE,
                    ScheduledJob.next_run_at <= now,
                    or_(
                        ScheduledJob.end_date == None,
                        ScheduledJob.end_date > now,
                    ),
                    or_(
                        ScheduledJob.max_runs == None,
                        ScheduledJob.run_count < ScheduledJob.max_runs,
                    ),
                )
            )
        )
        return list(result.scalars().all())

    async def execute_job(self, job: ScheduledJob) -> JobExecution:
        """Execute a scheduled job."""
        execution = JobExecution(
            job_id=job.id,
            scheduled_at=job.next_run_at or datetime.utcnow(),
            started_at=datetime.utcnow(),
            status=ExecutionStatus.RUNNING,
        )
        self.db.add(execution)
        await self.db.flush()

        start_time = time.time()

        try:
            result = await self._run_job(job)
            execution.status = ExecutionStatus.SUCCESS
            execution.result = result
            job.success_count += 1
        except Exception as e:
            execution.status = ExecutionStatus.FAILED
            execution.error = str(e)
            job.failure_count += 1

            # Retry logic
            if job.retry_on_failure and execution.attempt < job.max_retries:
                execution.attempt += 1
                # Schedule retry
                # (In production, this would be handled by a retry queue)

        execution.completed_at = datetime.utcnow()
        execution.duration_ms = int((time.time() - start_time) * 1000)

        # Update job
        job.last_run_at = execution.started_at
        job.run_count += 1
        job.next_run_at = self._calculate_next_run(job, after=execution.started_at)

        # Check if job should be completed
        if job.run_at and not job.cron_expression and not job.interval_seconds:
            job.status = JobStatus.COMPLETED
        if job.max_runs and job.run_count >= job.max_runs:
            job.status = JobStatus.COMPLETED

        await self.db.commit()
        return execution

    async def _run_job(self, job: ScheduledJob) -> dict:
        """Run a job based on its type."""
        config = job.config

        if job.job_type == JobType.AGENT_INVOKE:
            return await self._invoke_agent(config)
        elif job.job_type == JobType.TOOL_EXECUTE:
            return await self._execute_tool(config)
        elif job.job_type == JobType.WORKFLOW_RUN:
            return await self._run_workflow(config)
        elif job.job_type == JobType.WEBHOOK_CALL:
            return await self._call_webhook(config)
        elif job.job_type == JobType.EVENT_PUBLISH:
            return await self._publish_event(config)
        else:
            return {"status": "executed", "type": job.job_type.value}

    async def _invoke_agent(self, config: dict) -> dict:
        """Invoke an agent capability."""
        # Integrate with discovery/invocation system
        agent_id = config.get("agent_id")
        capability = config.get("capability")
        input_data = config.get("input", {})

        # Placeholder - would call the actual invocation service
        return {
            "type": "agent_invoke",
            "agent_id": agent_id,
            "capability": capability,
            "input": input_data,
        }

    async def _execute_tool(self, config: dict) -> dict:
        """Execute a tool."""
        from nexus.tools.service import ToolService

        tool_id = config.get("tool_id")
        input_data = config.get("input", {})

        service = ToolService(self.db)
        execution = await service.execute_tool(
            tool_id=UUID(tool_id),
            input_data=input_data,
            executor_id=UUID(config.get("owner_id", "00000000-0000-0000-0000-000000000000")),
            executor_type="scheduler",
        )

        return {
            "type": "tool_execute",
            "execution_id": str(execution.id),
            "status": execution.status,
            "output": execution.output_data,
        }

    async def _run_workflow(self, config: dict) -> dict:
        """Run a workflow."""
        from nexus.orchestration.service import OrchestrationService

        workflow_id = config.get("workflow_id")
        input_data = config.get("input", {})
        triggered_by = config.get("owner_id", "00000000-0000-0000-0000-000000000000")

        service = OrchestrationService(self.db)
        execution = await service.start_execution(
            workflow_id=UUID(workflow_id),
            input_data=input_data,
            triggered_by=UUID(triggered_by),
            triggered_by_type="scheduler",
        )

        return {
            "type": "workflow_run",
            "execution_id": str(execution.id),
            "status": execution.status.value,
        }

    async def _call_webhook(self, config: dict) -> dict:
        """Call a webhook."""
        import httpx

        url = config.get("url")
        method = config.get("method", "POST")
        headers = config.get("headers", {})
        body = config.get("body", {})

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=body)
            else:
                response = await client.request(method, url, headers=headers, json=body)

        return {
            "type": "webhook_call",
            "status_code": response.status_code,
            "response": response.text[:1000],  # Truncate
        }

    async def _publish_event(self, config: dict) -> dict:
        """Publish an event."""
        from nexus.events.service import EventBus

        event_type = config.get("event_type")
        topic = config.get("topic")
        payload = config.get("payload", {})

        bus = EventBus(self.db)
        event = await bus.publish(
            event_type=event_type,
            topic=topic,
            payload=payload,
            source_type="scheduler",
        )

        return {
            "type": "event_publish",
            "event_id": str(event.id),
        }

    async def pause_job(self, job_id: UUID):
        """Pause a scheduled job."""
        job = await self.get_job(job_id)
        if job:
            job.status = JobStatus.PAUSED
            await self.db.commit()

    async def resume_job(self, job_id: UUID):
        """Resume a paused job."""
        job = await self.get_job(job_id)
        if job:
            job.status = JobStatus.ACTIVE
            job.next_run_at = self._calculate_next_run(job)
            await self.db.commit()

    async def delete_job(self, job_id: UUID):
        """Delete a scheduled job."""
        job = await self.get_job(job_id)
        if job:
            await self.db.delete(job)
            await self.db.commit()

    async def run_scheduler_loop(self):
        """Main scheduler loop - run as background task."""
        self._running = True

        while self._running:
            try:
                due_jobs = await self.get_due_jobs()

                for job in due_jobs:
                    # Check concurrency
                    if not job.allow_concurrent:
                        # Check if already running
                        running = await self.db.execute(
                            select(JobExecution).where(
                                and_(
                                    JobExecution.job_id == job.id,
                                    JobExecution.status == ExecutionStatus.RUNNING,
                                )
                            )
                        )
                        if running.scalar_one_or_none():
                            continue

                    # Execute job in background
                    asyncio.create_task(self.execute_job(job))

                await asyncio.sleep(1)  # Check every second
            except Exception:
                await asyncio.sleep(5)  # Wait longer on error

    def stop_scheduler(self):
        """Stop the scheduler loop."""
        self._running = False
