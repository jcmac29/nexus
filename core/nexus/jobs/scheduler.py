"""Scheduler for periodic background jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

from nexus.jobs.service import JobService, JobPriority


logger = logging.getLogger(__name__)


class ScheduledJob:
    """A scheduled periodic job."""

    def __init__(
        self,
        name: str,
        task_name: str,
        interval_seconds: int | None = None,
        cron: str | None = None,
        args: list | None = None,
        kwargs: dict | None = None,
        queue: str = "default",
        priority: JobPriority = JobPriority.NORMAL,
    ):
        self.name = name
        self.task_name = task_name
        self.interval_seconds = interval_seconds
        self.cron = cron
        self.args = args or []
        self.kwargs = kwargs or {}
        self.queue = queue
        self.priority = priority
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None

    def should_run(self, now: datetime) -> bool:
        """Check if the job should run now."""
        if self.next_run is None:
            return True
        return now >= self.next_run

    def calculate_next_run(self, now: datetime):
        """Calculate the next run time."""
        if self.interval_seconds:
            self.next_run = now + timedelta(seconds=self.interval_seconds)
        elif self.cron:
            # Simple cron-like parsing (supports @hourly, @daily, @weekly)
            if self.cron == "@minutely":
                self.next_run = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            elif self.cron == "@hourly":
                self.next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            elif self.cron == "@daily":
                self.next_run = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            elif self.cron == "@weekly":
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                self.next_run = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
            else:
                # Default to hourly
                self.next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            self.next_run = now + timedelta(hours=1)


# Default scheduled jobs
DEFAULT_SCHEDULED_JOBS = [
    ScheduledJob(
        name="hourly-metrics-aggregation",
        task_name="nexus.aggregate_hourly_metrics",
        cron="@hourly",
        queue="analytics",
        priority=JobPriority.HIGH,
    ),
    ScheduledJob(
        name="daily-metrics-aggregation",
        task_name="nexus.aggregate_daily_metrics",
        cron="@daily",
        queue="analytics",
        priority=JobPriority.NORMAL,
    ),
    ScheduledJob(
        name="daily-storage-calculation",
        task_name="nexus.calculate_storage_usage",
        cron="@daily",
        queue="analytics",
        priority=JobPriority.LOW,
    ),
    ScheduledJob(
        name="webhook-retry-processor",
        task_name="nexus.retry_failed_webhooks",
        cron="@minutely",
        queue="webhooks",
        priority=JobPriority.HIGH,
    ),
    ScheduledJob(
        name="weekly-metrics-cleanup",
        task_name="nexus.cleanup_old_metrics",
        cron="@weekly",
        queue="maintenance",
        priority=JobPriority.LOW,
        kwargs={"retention_days": 90},
    ),
    ScheduledJob(
        name="weekly-delivery-logs-cleanup",
        task_name="nexus.cleanup_delivery_logs",
        cron="@weekly",
        queue="maintenance",
        priority=JobPriority.LOW,
        kwargs={"retention_days": 30},
    ),
    ScheduledJob(
        name="hourly-tenant-limits-refresh",
        task_name="nexus.refresh_tenant_limits",
        cron="@hourly",
        queue="tenants",
        priority=JobPriority.NORMAL,
    ),
    ScheduledJob(
        name="hourly-expired-cleanup",
        task_name="nexus.cleanup_expired",
        cron="@hourly",
        queue="maintenance",
        priority=JobPriority.LOW,
    ),
]


class Scheduler:
    """
    Scheduler for running periodic background jobs.

    The scheduler runs in a separate process/container and enqueues
    jobs at their scheduled intervals.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        jobs: list[ScheduledJob] | None = None,
    ):
        self.redis_url = redis_url
        self.jobs = jobs or DEFAULT_SCHEDULED_JOBS
        self._running = False
        self._job_service: JobService | None = None

    async def start(self):
        """Start the scheduler."""
        self._running = True
        self._job_service = JobService(redis_url=self.redis_url)
        await self._job_service.connect()

        logger.info(f"Scheduler starting with {len(self.jobs)} scheduled jobs")
        for job in self.jobs:
            logger.info(f"  - {job.name}: {job.task_name} ({job.cron or f'every {job.interval_seconds}s'})")

        # Initialize next run times
        now = datetime.utcnow()
        for job in self.jobs:
            job.calculate_next_run(now)

        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(10)  # Check every 10 seconds
        finally:
            if self._job_service:
                await self._job_service.disconnect()

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        logger.info("Scheduler stopping...")

    async def _tick(self):
        """Process one scheduler tick."""
        now = datetime.utcnow()

        for job in self.jobs:
            if job.should_run(now):
                await self._enqueue_job(job)
                job.last_run = now
                job.calculate_next_run(now)

    async def _enqueue_job(self, job: ScheduledJob):
        """Enqueue a scheduled job."""
        try:
            job_id = await self._job_service.enqueue(
                task_name=job.task_name,
                args=job.args,
                kwargs=job.kwargs,
                queue=job.queue,
                priority=job.priority,
                metadata={"scheduled_job": job.name},
            )
            logger.info(f"Enqueued scheduled job {job.name}: {job_id}")
        except Exception as e:
            logger.error(f"Failed to enqueue scheduled job {job.name}: {e}")

    def add_job(self, job: ScheduledJob):
        """Add a new scheduled job."""
        now = datetime.utcnow()
        job.calculate_next_run(now)
        self.jobs.append(job)
        logger.info(f"Added scheduled job: {job.name}")

    def remove_job(self, name: str):
        """Remove a scheduled job by name."""
        self.jobs = [j for j in self.jobs if j.name != name]
        logger.info(f"Removed scheduled job: {name}")


async def run_scheduler(
    redis_url: str = "redis://localhost:6379",
    jobs: list[ScheduledJob] | None = None,
):
    """Run the scheduler."""
    import signal

    scheduler = Scheduler(redis_url=redis_url, jobs=jobs)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, scheduler.stop)

    await scheduler.start()


if __name__ == "__main__":
    import argparse
    from nexus.observability import setup_logging

    parser = argparse.ArgumentParser(description="Nexus job scheduler")
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379",
        help="Redis URL",
    )

    args = parser.parse_args()

    setup_logging(level="INFO", format="console")
    asyncio.run(run_scheduler(redis_url=args.redis_url))
