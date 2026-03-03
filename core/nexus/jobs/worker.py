"""Background job worker for Nexus."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Optional

from nexus.jobs.service import Worker
from nexus.observability import setup_logging


async def main(
    queues: list[str] = None,
    concurrency: int = 10,
):
    """Run the job worker."""
    if queues is None:
        queues = ["high", "default", "low"]

    # Setup logging
    setup_logging(level="INFO", format="console")

    logger = logging.getLogger(__name__)
    logger.info(f"Starting Nexus worker for queues: {queues}")
    logger.info(f"Concurrency: {concurrency}")

    # Create worker
    worker = Worker(queues=queues, concurrency=concurrency)

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def handle_signal(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    # Run worker
    try:
        await worker.run(stop_event=stop_event)
    except Exception as e:
        logger.exception(f"Worker error: {e}")
        sys.exit(1)

    logger.info("Worker stopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nexus job worker")
    parser.add_argument(
        "--queues",
        "-q",
        default="high,default,low",
        help="Comma-separated list of queues to process",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=10,
        help="Number of concurrent jobs to process",
    )

    args = parser.parse_args()
    queues = [q.strip() for q in args.queues.split(",")]

    asyncio.run(main(queues=queues, concurrency=args.concurrency))
