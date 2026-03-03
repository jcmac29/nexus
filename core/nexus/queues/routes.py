"""Queue API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.queues.models import Priority
from nexus.queues.service import QueueService

router = APIRouter(prefix="/queues", tags=["queues"])


class CreateQueueRequest(BaseModel):
    name: str
    description: str | None = None
    max_size: int | None = None
    max_retries: int = 3
    visibility_timeout_seconds: int = 300
    deduplication_enabled: bool = False


class EnqueueRequest(BaseModel):
    payload: dict
    priority: int = 2  # NORMAL
    metadata: dict | None = None
    delay_seconds: int = 0
    dedup_key: str | None = None
    ttl_seconds: int | None = None


class CompleteRequest(BaseModel):
    lock_token: str
    result: dict | None = None


class FailRequest(BaseModel):
    lock_token: str
    error: str
    retry: bool = True


@router.post("")
async def create_queue(
    request: CreateQueueRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new queue."""
    service = QueueService(db)

    queue = await service.create_queue(
        name=request.name,
        owner_id=agent.id,
        description=request.description,
        max_size=request.max_size,
        max_retries=request.max_retries,
        visibility_timeout_seconds=request.visibility_timeout_seconds,
        deduplication_enabled=request.deduplication_enabled,
    )

    return {
        "id": str(queue.id),
        "name": queue.name,
        "status": queue.status.value,
        "created_at": queue.created_at.isoformat(),
    }


@router.get("")
async def list_queues(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List queues."""
    from sqlalchemy import select
    from nexus.queues.models import Queue

    result = await db.execute(select(Queue))
    queues = result.scalars().all()

    return [
        {
            "id": str(q.id),
            "name": q.name,
            "status": q.status.value,
            "total_enqueued": q.total_enqueued,
            "total_processed": q.total_processed,
        }
        for q in queues
    ]


@router.get("/{queue_id}/stats")
async def get_queue_stats(
    queue_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get queue statistics."""
    service = QueueService(db)
    stats = await service.get_queue_stats(UUID(queue_id))

    if not stats:
        raise HTTPException(status_code=404, detail="Queue not found")

    return stats


@router.post("/{queue_id}/enqueue")
async def enqueue(
    queue_id: str,
    request: EnqueueRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add an item to a queue."""
    service = QueueService(db)

    try:
        item = await service.enqueue(
            queue_id=UUID(queue_id),
            payload=request.payload,
            priority=Priority(request.priority),
            metadata=request.metadata,
            delay_seconds=request.delay_seconds,
            dedup_key=request.dedup_key,
            ttl_seconds=request.ttl_seconds,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not item:
        raise HTTPException(status_code=400, detail="Failed to enqueue item")

    return {
        "id": str(item.id),
        "priority": item.priority,
        "visible_at": item.visible_at.isoformat(),
        "enqueued_at": item.enqueued_at.isoformat(),
    }


@router.post("/{queue_id}/dequeue")
async def dequeue(
    queue_id: str,
    count: int = Query(default=1, le=10),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get items from a queue for processing."""
    service = QueueService(db)

    items = await service.dequeue(
        queue_id=UUID(queue_id),
        processor_id=agent.id,
        processor_type="agent",
        count=count,
    )

    return [
        {
            "id": str(item.id),
            "payload": item.payload,
            "metadata": item.metadata,
            "priority": item.priority,
            "lock_token": item.lock_token,
            "attempts": item.attempts,
            "lock_expires_at": item.lock_expires_at.isoformat() if item.lock_expires_at else None,
        }
        for item in items
    ]


@router.post("/items/{item_id}/complete")
async def complete_item(
    item_id: str,
    request: CompleteRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Mark an item as completed."""
    service = QueueService(db)

    success = await service.complete(
        item_id=UUID(item_id),
        lock_token=request.lock_token,
        result=request.result,
    )

    if not success:
        raise HTTPException(status_code=400, detail="Invalid item or lock token")

    return {"status": "completed"}


@router.post("/items/{item_id}/fail")
async def fail_item(
    item_id: str,
    request: FailRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Mark an item as failed."""
    service = QueueService(db)

    success = await service.fail(
        item_id=UUID(item_id),
        lock_token=request.lock_token,
        error=request.error,
        retry=request.retry,
    )

    if not success:
        raise HTTPException(status_code=400, detail="Invalid item or lock token")

    return {"status": "failed", "will_retry": request.retry}


@router.post("/items/{item_id}/release")
async def release_item(
    item_id: str,
    lock_token: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Release an item back to the queue."""
    service = QueueService(db)

    success = await service.release(
        item_id=UUID(item_id),
        lock_token=lock_token,
    )

    if not success:
        raise HTTPException(status_code=400, detail="Invalid item or lock token")

    return {"status": "released"}


@router.post("/items/{item_id}/extend")
async def extend_lock(
    item_id: str,
    lock_token: str,
    extension_seconds: int = 300,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Extend the lock on a processing item."""
    service = QueueService(db)

    success = await service.extend_lock(
        item_id=UUID(item_id),
        lock_token=lock_token,
        extension_seconds=extension_seconds,
    )

    if not success:
        raise HTTPException(status_code=400, detail="Invalid item or lock token")

    return {"status": "extended"}


@router.post("/{queue_id}/dead-letters/requeue")
async def requeue_dead_letters(
    queue_id: str,
    limit: int = Query(default=100, le=1000),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Requeue items from the dead letter queue."""
    service = QueueService(db)
    count = await service.requeue_dead_letters(UUID(queue_id), limit)
    return {"requeued": count}


@router.post("/{queue_id}/cleanup")
async def cleanup_queue(
    queue_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Clean up expired items and recover stale locks."""
    service = QueueService(db)

    expired = await service.cleanup_expired(UUID(queue_id))
    recovered = await service.recover_stale_items(UUID(queue_id))

    return {"expired_removed": expired, "stale_recovered": recovered}
