"""Queue service for priority task handling with conflict resolution."""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.queues.models import Queue, QueueItem, DeadLetter, QueueStatus, ItemStatus, Priority


class QueueService:
    """Service for managing priority queues."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_queue(
        self,
        name: str,
        owner_id: UUID,
        description: str | None = None,
        max_size: int | None = None,
        max_retries: int = 3,
        visibility_timeout_seconds: int = 300,
        deduplication_enabled: bool = False,
        **kwargs,
    ) -> Queue:
        """Create a new queue."""
        queue = Queue(
            name=name,
            owner_id=owner_id,
            description=description,
            max_size=max_size,
            max_retries=max_retries,
            visibility_timeout_seconds=visibility_timeout_seconds,
            deduplication_enabled=deduplication_enabled,
            **kwargs,
        )
        self.db.add(queue)
        await self.db.commit()
        await self.db.refresh(queue)
        return queue

    async def get_queue(self, queue_id: UUID) -> Queue | None:
        """Get a queue by ID."""
        result = await self.db.execute(select(Queue).where(Queue.id == queue_id))
        return result.scalar_one_or_none()

    async def get_queue_by_name(self, name: str) -> Queue | None:
        """Get a queue by name."""
        result = await self.db.execute(select(Queue).where(Queue.name == name))
        return result.scalar_one_or_none()

    async def enqueue(
        self,
        queue_id: UUID,
        payload: dict,
        priority: Priority = Priority.NORMAL,
        metadata: dict | None = None,
        delay_seconds: int = 0,
        dedup_key: str | None = None,
        ttl_seconds: int | None = None,
    ) -> QueueItem | None:
        """Add an item to a queue."""
        queue = await self.get_queue(queue_id)
        if not queue or queue.status != QueueStatus.ACTIVE:
            return None

        # Check queue size limit
        if queue.max_size:
            count = await self._get_pending_count(queue_id)
            if count >= queue.max_size:
                raise ValueError("Queue is full")

        # Handle deduplication
        if queue.deduplication_enabled and dedup_key:
            existing = await self._find_duplicate(queue_id, dedup_key, queue.deduplication_window_seconds)
            if existing:
                return existing  # Return existing item instead of creating duplicate

        # Calculate timing
        now = datetime.utcnow()
        visible_at = now + timedelta(seconds=delay_seconds) if delay_seconds > 0 else now
        expires_at = now + timedelta(seconds=ttl_seconds) if ttl_seconds else None

        item = QueueItem(
            queue_id=queue_id,
            priority=priority.value if isinstance(priority, Priority) else priority,
            payload=payload,
            metadata=metadata or {},
            dedup_key=dedup_key,
            visible_at=visible_at,
            expires_at=expires_at,
        )
        self.db.add(item)

        queue.total_enqueued += 1
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def dequeue(
        self,
        queue_id: UUID,
        processor_id: UUID,
        processor_type: str = "agent",
        count: int = 1,
    ) -> list[QueueItem]:
        """Get items from a queue for processing."""
        queue = await self.get_queue(queue_id)
        if not queue or queue.status == QueueStatus.PAUSED:
            return []

        now = datetime.utcnow()

        # Find available items (pending, visible, not expired)
        query = (
            select(QueueItem)
            .where(
                and_(
                    QueueItem.queue_id == queue_id,
                    QueueItem.status == ItemStatus.PENDING,
                    QueueItem.visible_at <= now,
                    or_(
                        QueueItem.expires_at == None,
                        QueueItem.expires_at > now,
                    ),
                )
            )
            .order_by(QueueItem.priority.asc(), QueueItem.enqueued_at.asc())
            .limit(count)
            .with_for_update(skip_locked=True)  # Optimistic locking
        )

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        # Lock items for processing
        for item in items:
            item.status = ItemStatus.PROCESSING
            item.processor_id = processor_id
            item.processor_type = processor_type
            item.started_at = now
            item.attempts += 1
            item.lock_token = secrets.token_hex(32)
            item.locked_at = now
            item.lock_expires_at = now + timedelta(seconds=queue.visibility_timeout_seconds)

        await self.db.commit()
        return items

    async def complete(
        self,
        item_id: UUID,
        lock_token: str,
        result: dict | None = None,
    ) -> bool:
        """Mark an item as completed."""
        item = await self._get_item(item_id)
        if not item or item.lock_token != lock_token:
            return False

        item.status = ItemStatus.COMPLETED
        item.completed_at = datetime.utcnow()
        item.result = result

        queue = await self.get_queue(item.queue_id)
        if queue:
            queue.total_processed += 1

        await self.db.commit()
        return True

    async def fail(
        self,
        item_id: UUID,
        lock_token: str,
        error: str,
        retry: bool = True,
    ) -> bool:
        """Mark an item as failed, optionally retrying."""
        item = await self._get_item(item_id)
        if not item or item.lock_token != lock_token:
            return False

        queue = await self.get_queue(item.queue_id)
        max_attempts = item.max_attempts or (queue.max_retries if queue else 3)

        item.last_error = error

        if retry and item.attempts < max_attempts:
            # Retry with exponential backoff
            delay = (queue.retry_delay_seconds if queue else 60) * (2 ** (item.attempts - 1))
            item.status = ItemStatus.PENDING
            item.visible_at = datetime.utcnow() + timedelta(seconds=delay)
            item.processor_id = None
            item.lock_token = None
        else:
            # Move to dead letter queue
            item.status = ItemStatus.DEAD
            await self._move_to_dead_letter(item, error)

            if queue:
                queue.total_failed += 1

        await self.db.commit()
        return True

    async def extend_lock(
        self,
        item_id: UUID,
        lock_token: str,
        extension_seconds: int = 300,
    ) -> bool:
        """Extend the lock on a processing item."""
        item = await self._get_item(item_id)
        if not item or item.lock_token != lock_token:
            return False

        item.lock_expires_at = datetime.utcnow() + timedelta(seconds=extension_seconds)
        await self.db.commit()
        return True

    async def release(
        self,
        item_id: UUID,
        lock_token: str,
    ) -> bool:
        """Release an item back to the queue."""
        item = await self._get_item(item_id)
        if not item or item.lock_token != lock_token:
            return False

        item.status = ItemStatus.PENDING
        item.processor_id = None
        item.lock_token = None
        item.visible_at = datetime.utcnow()
        await self.db.commit()
        return True

    async def get_queue_stats(self, queue_id: UUID) -> dict:
        """Get queue statistics."""
        queue = await self.get_queue(queue_id)
        if not queue:
            return {}

        # Count by status
        result = await self.db.execute(
            select(QueueItem.status, func.count(QueueItem.id))
            .where(QueueItem.queue_id == queue_id)
            .group_by(QueueItem.status)
        )
        status_counts = {row[0].value: row[1] for row in result}

        # Count by priority
        result = await self.db.execute(
            select(QueueItem.priority, func.count(QueueItem.id))
            .where(
                and_(
                    QueueItem.queue_id == queue_id,
                    QueueItem.status == ItemStatus.PENDING,
                )
            )
            .group_by(QueueItem.priority)
        )
        priority_counts = {str(row[0]): row[1] for row in result}

        return {
            "queue_id": str(queue_id),
            "name": queue.name,
            "status": queue.status.value,
            "total_enqueued": queue.total_enqueued,
            "total_processed": queue.total_processed,
            "total_failed": queue.total_failed,
            "status_counts": status_counts,
            "priority_counts": priority_counts,
        }

    async def requeue_dead_letters(
        self,
        queue_id: UUID,
        limit: int = 100,
    ) -> int:
        """Requeue items from the dead letter queue."""
        result = await self.db.execute(
            select(DeadLetter)
            .where(DeadLetter.original_queue_id == queue_id)
            .limit(limit)
        )
        dead_letters = list(result.scalars().all())

        requeued = 0
        for dl in dead_letters:
            item = QueueItem(
                queue_id=queue_id,
                payload=dl.payload,
                metadata={**dl.metadata, "requeued_from_dead_letter": str(dl.id)},
                attempts=0,
            )
            self.db.add(item)

            dl.requeued_at = datetime.utcnow()
            dl.requeue_count += 1
            requeued += 1

        await self.db.commit()
        return requeued

    async def cleanup_expired(self, queue_id: UUID) -> int:
        """Clean up expired items."""
        now = datetime.utcnow()
        result = await self.db.execute(
            update(QueueItem)
            .where(
                and_(
                    QueueItem.queue_id == queue_id,
                    QueueItem.expires_at < now,
                    QueueItem.status == ItemStatus.PENDING,
                )
            )
            .values(status=ItemStatus.DEAD)
        )
        await self.db.commit()
        return result.rowcount

    async def recover_stale_items(self, queue_id: UUID) -> int:
        """Recover items with expired locks."""
        now = datetime.utcnow()
        result = await self.db.execute(
            update(QueueItem)
            .where(
                and_(
                    QueueItem.queue_id == queue_id,
                    QueueItem.status == ItemStatus.PROCESSING,
                    QueueItem.lock_expires_at < now,
                )
            )
            .values(
                status=ItemStatus.PENDING,
                processor_id=None,
                lock_token=None,
                visible_at=now,
            )
        )
        await self.db.commit()
        return result.rowcount

    async def _get_item(self, item_id: UUID) -> QueueItem | None:
        """Get a queue item by ID."""
        result = await self.db.execute(select(QueueItem).where(QueueItem.id == item_id))
        return result.scalar_one_or_none()

    async def _get_pending_count(self, queue_id: UUID) -> int:
        """Get count of pending items in a queue."""
        result = await self.db.execute(
            select(func.count(QueueItem.id))
            .where(
                and_(
                    QueueItem.queue_id == queue_id,
                    QueueItem.status == ItemStatus.PENDING,
                )
            )
        )
        return result.scalar() or 0

    async def _find_duplicate(
        self,
        queue_id: UUID,
        dedup_key: str,
        window_seconds: int,
    ) -> QueueItem | None:
        """Find a duplicate item within the deduplication window."""
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        result = await self.db.execute(
            select(QueueItem)
            .where(
                and_(
                    QueueItem.queue_id == queue_id,
                    QueueItem.dedup_key == dedup_key,
                    QueueItem.enqueued_at >= cutoff,
                    QueueItem.status.in_([ItemStatus.PENDING, ItemStatus.PROCESSING]),
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _move_to_dead_letter(self, item: QueueItem, error: str):
        """Move an item to the dead letter queue."""
        dead_letter = DeadLetter(
            original_queue_id=item.queue_id,
            original_item_id=item.id,
            payload=item.payload,
            metadata=item.metadata,
            failure_reason=error,
            attempts=item.attempts,
            errors=[item.last_error] if item.last_error else [],
        )
        self.db.add(dead_letter)
