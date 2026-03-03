"""Background job service using Redis-based queue."""

from __future__ import annotations

import asyncio
import json
import traceback
import uuid as uuid_module
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine
from uuid import UUID
import signal
import socket

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.jobs.models import BackgroundJob, RecurringJob, JobStatus, JobPriority


# Task registry
_tasks: dict[str, Callable] = {}


def task(
    name: str | None = None,
    queue: str = "default",
    max_retries: int = 3,
    retry_delay: int = 60,
    timeout: int = 300,
):
    """Decorator to register a function as a background task."""
    def decorator(func: Callable) -> Callable:
        task_name = name or f"{func.__module__}.{func.__name__}"
        _tasks[task_name] = {
            "func": func,
            "queue": queue,
            "max_retries": max_retries,
            "retry_delay": retry_delay,
            "timeout": timeout,
        }

        async def delay(*args, **kwargs) -> str:
            """Schedule the task for background execution."""
            from nexus.jobs.service import JobService
            service = JobService(None)  # Will use Redis directly
            job_id = await service.enqueue(
                task_name=task_name,
                args=list(args),
                kwargs=kwargs,
                queue=queue,
            )
            return job_id

        func.delay = delay
        func.task_name = task_name
        return func

    return decorator


class JobService:
    """Service for managing background jobs."""

    def __init__(self, db: AsyncSession | None = None, redis_url: str = "redis://localhost:6379"):
        self.db = db
        self._redis_url = redis_url
        self._redis = None

    async def connect(self):
        """Connect to Redis."""
        import redis.asyncio as redis
        self._redis = redis.from_url(self._redis_url, decode_responses=True)

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()

    async def enqueue(
        self,
        task_name: str,
        args: list | None = None,
        kwargs: dict | None = None,
        queue: str = "default",
        priority: JobPriority = JobPriority.NORMAL,
        scheduled_at: datetime | None = None,
        max_retries: int = 3,
        timeout_seconds: int = 300,
        owner_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Enqueue a job for background processing."""
        job_id = str(uuid_module.uuid4())

        job_data = {
            "job_id": job_id,
            "task_name": task_name,
            "args": args or [],
            "kwargs": kwargs or {},
            "queue": queue,
            "priority": priority.value,
            "status": JobStatus.PENDING.value,
            "max_retries": max_retries,
            "retry_count": 0,
            "timeout_seconds": timeout_seconds,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "created_at": datetime.utcnow().isoformat(),
            "owner_id": str(owner_id) if owner_id else None,
            "metadata": metadata or {},
        }

        # Store in Redis
        if not self._redis:
            await self.connect()

        # Store job data
        await self._redis.hset(f"job:{job_id}", mapping={
            k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) if v is not None else ""
            for k, v in job_data.items()
        })

        # Add to queue (sorted by priority and time)
        score = self._calculate_score(priority, scheduled_at)
        await self._redis.zadd(f"queue:{queue}", {job_id: score})

        # Store in database if available
        if self.db:
            job = BackgroundJob(
                job_id=job_id,
                name=task_name,
                task_name=task_name,
                queue=queue,
                args=args or [],
                kwargs=kwargs or {},
                status=JobStatus.PENDING,
                priority=priority,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                scheduled_at=scheduled_at,
                owner_id=owner_id,
                metadata=metadata or {},
            )
            self.db.add(job)
            await self.db.commit()

        return job_id

    def _calculate_score(self, priority: JobPriority, scheduled_at: datetime | None) -> float:
        """Calculate queue score (lower = higher priority)."""
        priority_scores = {
            JobPriority.CRITICAL: 0,
            JobPriority.HIGH: 1000000,
            JobPriority.NORMAL: 2000000,
            JobPriority.LOW: 3000000,
        }
        base_score = priority_scores.get(priority, 2000000)

        if scheduled_at:
            time_score = scheduled_at.timestamp()
        else:
            time_score = datetime.utcnow().timestamp()

        return base_score + time_score

    async def dequeue(self, queue: str = "default", timeout: int = 5) -> dict | None:
        """Dequeue a job from the queue."""
        if not self._redis:
            await self.connect()

        now = datetime.utcnow().timestamp()

        # Get jobs that are ready to run (scheduled_at <= now)
        max_score = 3000000 + now  # Include all priorities up to now

        # Pop the highest priority job
        result = await self._redis.zpopmin(f"queue:{queue}")
        if not result:
            return None

        job_id, score = result[0]

        # Check if scheduled for later
        if score > max_score:
            # Put it back
            await self._redis.zadd(f"queue:{queue}", {job_id: score})
            return None

        # Get job data
        job_data = await self._redis.hgetall(f"job:{job_id}")
        if not job_data:
            return None

        # Parse job data
        return {
            "job_id": job_id,
            "task_name": job_data.get("task_name", ""),
            "args": json.loads(job_data.get("args", "[]")),
            "kwargs": json.loads(job_data.get("kwargs", "{}")),
            "queue": job_data.get("queue", "default"),
            "max_retries": int(job_data.get("max_retries", 3)),
            "retry_count": int(job_data.get("retry_count", 0)),
            "timeout_seconds": int(job_data.get("timeout_seconds", 300)),
        }

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: str | None = None,
        traceback_str: str | None = None,
        progress: int | None = None,
        progress_message: str | None = None,
    ):
        """Update job status."""
        if not self._redis:
            await self.connect()

        updates = {"status": status.value}
        if result is not None:
            updates["result"] = json.dumps(result)
        if error:
            updates["error"] = error
        if traceback_str:
            updates["traceback"] = traceback_str
        if progress is not None:
            updates["progress"] = str(progress)
        if progress_message:
            updates["progress_message"] = progress_message

        if status == JobStatus.RUNNING:
            updates["started_at"] = datetime.utcnow().isoformat()
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            updates["completed_at"] = datetime.utcnow().isoformat()

        await self._redis.hset(f"job:{job_id}", mapping=updates)

        # Update database
        if self.db:
            result_db = await self.db.execute(
                select(BackgroundJob).where(BackgroundJob.job_id == job_id)
            )
            job = result_db.scalar_one_or_none()
            if job:
                job.status = status
                if result is not None:
                    job.result = result
                if error:
                    job.error = error
                if traceback_str:
                    job.traceback = traceback_str
                if progress is not None:
                    job.progress = progress
                if progress_message:
                    job.progress_message = progress_message
                if status == JobStatus.RUNNING:
                    job.started_at = datetime.utcnow()
                elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                    job.completed_at = datetime.utcnow()
                await self.db.commit()

    async def retry_job(self, job_id: str, queue: str = "default"):
        """Retry a failed job."""
        if not self._redis:
            await self.connect()

        job_data = await self._redis.hgetall(f"job:{job_id}")
        if not job_data:
            return

        retry_count = int(job_data.get("retry_count", 0)) + 1
        max_retries = int(job_data.get("max_retries", 3))

        if retry_count > max_retries:
            await self.update_job_status(job_id, JobStatus.FAILED, error="Max retries exceeded")
            return

        # Update retry count
        await self._redis.hset(f"job:{job_id}", "retry_count", str(retry_count))
        await self._redis.hset(f"job:{job_id}", "status", JobStatus.RETRYING.value)

        # Calculate backoff delay
        delay = int(job_data.get("retry_delay", 60)) * (2 ** (retry_count - 1))
        scheduled_at = datetime.utcnow() + timedelta(seconds=delay)

        # Re-add to queue
        priority = JobPriority(job_data.get("priority", "normal"))
        score = self._calculate_score(priority, scheduled_at)
        await self._redis.zadd(f"queue:{queue}", {job_id: score})

    async def cancel_job(self, job_id: str, queue: str = "default"):
        """Cancel a pending job."""
        if not self._redis:
            await self.connect()

        # Remove from queue
        await self._redis.zrem(f"queue:{queue}", job_id)

        # Update status
        await self.update_job_status(job_id, JobStatus.CANCELLED)

    async def get_job(self, job_id: str) -> dict | None:
        """Get job details."""
        if not self._redis:
            await self.connect()

        job_data = await self._redis.hgetall(f"job:{job_id}")
        if not job_data:
            return None

        return {
            "job_id": job_id,
            "task_name": job_data.get("task_name", ""),
            "status": job_data.get("status", ""),
            "args": json.loads(job_data.get("args", "[]")),
            "kwargs": json.loads(job_data.get("kwargs", "{}")),
            "result": json.loads(job_data.get("result", "null")),
            "error": job_data.get("error"),
            "progress": int(job_data.get("progress", 0)),
            "progress_message": job_data.get("progress_message"),
            "retry_count": int(job_data.get("retry_count", 0)),
            "created_at": job_data.get("created_at"),
            "started_at": job_data.get("started_at"),
            "completed_at": job_data.get("completed_at"),
        }

    async def get_queue_length(self, queue: str = "default") -> int:
        """Get number of jobs in queue."""
        if not self._redis:
            await self.connect()
        return await self._redis.zcard(f"queue:{queue}")

    async def get_queue_stats(self, queue: str = "default") -> dict:
        """Get queue statistics."""
        if not self._redis:
            await self.connect()

        pending = await self._redis.zcard(f"queue:{queue}")

        # Count by status (approximate from recent jobs)
        return {
            "queue": queue,
            "pending": pending,
        }


class Worker:
    """Background job worker."""

    def __init__(
        self,
        queues: list[str] | None = None,
        concurrency: int = 4,
        redis_url: str = "redis://localhost:6379",
    ):
        self.queues = queues or ["default"]
        self.concurrency = concurrency
        self.redis_url = redis_url
        self.worker_id = str(uuid_module.uuid4())[:8]
        self.hostname = socket.gethostname()
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self):
        """Start the worker."""
        self._running = True

        # Handle shutdown signals
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown)

        print(f"Worker {self.worker_id}@{self.hostname} starting...")
        print(f"Queues: {', '.join(self.queues)}")
        print(f"Concurrency: {self.concurrency}")
        print(f"Registered tasks: {', '.join(_tasks.keys())}")

        # Create worker tasks
        workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.concurrency)
        ]

        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            pass

        print("Worker shutdown complete.")

    def _shutdown(self):
        """Handle shutdown signal."""
        print("Shutting down worker...")
        self._running = False

    async def _worker_loop(self, worker_num: int):
        """Main worker loop."""
        service = JobService(redis_url=self.redis_url)
        await service.connect()

        while self._running:
            job = None
            for queue in self.queues:
                job = await service.dequeue(queue)
                if job:
                    break

            if not job:
                await asyncio.sleep(1)
                continue

            await self._process_job(service, job)

        await service.disconnect()

    async def _process_job(self, service: JobService, job: dict):
        """Process a single job."""
        job_id = job["job_id"]
        task_name = job["task_name"]

        print(f"Processing job {job_id}: {task_name}")

        # Get task function
        task_info = _tasks.get(task_name)
        if not task_info:
            await service.update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Unknown task: {task_name}",
            )
            return

        func = task_info["func"]

        # Update status to running
        await service.update_job_status(job_id, JobStatus.RUNNING)

        try:
            # Execute task with timeout
            timeout = job.get("timeout_seconds", 300)

            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(
                    func(*job["args"], **job["kwargs"]),
                    timeout=timeout,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(func, *job["args"], **job["kwargs"]),
                    timeout=timeout,
                )

            await service.update_job_status(
                job_id,
                JobStatus.COMPLETED,
                result=result,
            )
            print(f"Job {job_id} completed successfully")

        except asyncio.TimeoutError:
            await service.update_job_status(
                job_id,
                JobStatus.FAILED,
                error="Job timed out",
            )
            print(f"Job {job_id} timed out")

        except Exception as e:
            tb = traceback.format_exc()
            print(f"Job {job_id} failed: {e}")

            # Check if should retry
            if job["retry_count"] < job["max_retries"]:
                await service.retry_job(job_id, job["queue"])
                print(f"Job {job_id} scheduled for retry")
            else:
                await service.update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error=str(e),
                    traceback_str=tb,
                )


async def run_worker(
    queues: list[str] | None = None,
    concurrency: int = 4,
    redis_url: str = "redis://localhost:6379",
):
    """Run a background job worker."""
    worker = Worker(queues=queues, concurrency=concurrency, redis_url=redis_url)
    await worker.start()
