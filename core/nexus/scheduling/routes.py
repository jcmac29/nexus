"""Scheduling API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.scheduling.models import JobType, JobStatus
from nexus.scheduling.service import SchedulerService

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


class CreateJobRequest(BaseModel):
    name: str
    job_type: str
    config: dict
    cron_expression: str | None = None
    interval_seconds: int | None = None
    run_at: datetime | None = None
    timezone: str = "UTC"
    max_runs: int | None = None
    end_date: datetime | None = None
    description: str | None = None
    retry_on_failure: bool = True
    max_retries: int = 3
    allow_concurrent: bool = False
    timeout_seconds: int = 300


@router.post("/jobs")
async def create_job(
    request: CreateJobRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new scheduled job."""
    service = SchedulerService(db)

    job = await service.create_job(
        name=request.name,
        job_type=JobType(request.job_type),
        owner_id=agent.id,
        config=request.config,
        cron_expression=request.cron_expression,
        interval_seconds=request.interval_seconds,
        run_at=request.run_at,
        timezone=request.timezone,
        max_runs=request.max_runs,
        end_date=request.end_date,
        description=request.description,
        retry_on_failure=request.retry_on_failure,
        max_retries=request.max_retries,
        allow_concurrent=request.allow_concurrent,
        timeout_seconds=request.timeout_seconds,
    )

    return {
        "id": str(job.id),
        "name": job.name,
        "job_type": job.job_type.value,
        "status": job.status.value,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "created_at": job.created_at.isoformat(),
    }


@router.get("/jobs")
async def list_jobs(
    status: str | None = None,
    owner_only: bool = True,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List scheduled jobs."""
    service = SchedulerService(db)

    jobs = await service.list_jobs(
        owner_id=agent.id if owner_only else None,
        status=JobStatus(status) if status else None,
        limit=limit,
    )

    return [
        {
            "id": str(j.id),
            "name": j.name,
            "job_type": j.job_type.value,
            "status": j.status.value,
            "cron_expression": j.cron_expression,
            "interval_seconds": j.interval_seconds,
            "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
            "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
            "run_count": j.run_count,
            "success_count": j.success_count,
            "failure_count": j.failure_count,
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a scheduled job."""
    service = SchedulerService(db)
    job = await service.get_job(UUID(job_id))

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": str(job.id),
        "name": job.name,
        "description": job.description,
        "job_type": job.job_type.value,
        "config": job.config,
        "status": job.status.value,
        "cron_expression": job.cron_expression,
        "interval_seconds": job.interval_seconds,
        "run_at": job.run_at.isoformat() if job.run_at else None,
        "timezone": job.timezone,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "run_count": job.run_count,
        "success_count": job.success_count,
        "failure_count": job.failure_count,
        "max_runs": job.max_runs,
        "retry_on_failure": job.retry_on_failure,
        "max_retries": job.max_retries,
        "created_at": job.created_at.isoformat(),
    }


@router.post("/jobs/{job_id}/run")
async def run_job_now(
    job_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Run a job immediately."""
    service = SchedulerService(db)
    job = await service.get_job(UUID(job_id))

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # SECURITY: Verify ownership before execution
    if job.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to run this job")

    execution = await service.execute_job(job)

    return {
        "execution_id": str(execution.id),
        "status": execution.status.value,
        "result": execution.result,
        "error": execution.error,
        "duration_ms": execution.duration_ms,
    }


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Pause a scheduled job."""
    service = SchedulerService(db)
    job = await service.get_job(UUID(job_id))

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # SECURITY: Verify ownership before modification
    if job.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this job")

    await service.pause_job(UUID(job_id))
    return {"status": "paused"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused job."""
    service = SchedulerService(db)
    job = await service.get_job(UUID(job_id))

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # SECURITY: Verify ownership before modification
    if job.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this job")

    await service.resume_job(UUID(job_id))
    return {"status": "resumed"}


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Delete a scheduled job."""
    service = SchedulerService(db)
    job = await service.get_job(UUID(job_id))

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # SECURITY: Verify ownership before deletion
    if job.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this job")

    await service.delete_job(UUID(job_id))
    return {"status": "deleted"}


@router.get("/jobs/{job_id}/executions")
async def list_executions(
    job_id: str,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List executions for a job."""
    from sqlalchemy import select
    from nexus.scheduling.models import JobExecution

    result = await db.execute(
        select(JobExecution)
        .where(JobExecution.job_id == UUID(job_id))
        .order_by(JobExecution.started_at.desc())
        .limit(limit)
    )
    executions = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "status": e.status.value,
            "attempt": e.attempt,
            "scheduled_at": e.scheduled_at.isoformat(),
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "duration_ms": e.duration_ms,
            "error": e.error,
        }
        for e in executions
    ]
