"""Context service for standardized handoffs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.context.models import (
    ContextPackage,
    ContextTransfer,
    TransferStatus,
)

if TYPE_CHECKING:
    pass


class ContextService:
    """Service for managing context packages and transfers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Packages ====================

    async def pack_context(
        self,
        owner_agent_id: UUID,
        name: str,
        summary: str | None = None,
        goals: dict | None = None,
        memories: dict | None = None,
        conversation_history: list | None = None,
        reasoning_trace: list | None = None,
        decisions_made: list | None = None,
        constraints: dict | None = None,
        preferences: dict | None = None,
        tags: list[str] | None = None,
        is_public: bool = False,
        allowed_agents: list[str] | None = None,
        expires_in_hours: int | None = None,
    ) -> ContextPackage:
        """Pack context into a transferable package."""
        # Check for existing package with same name
        existing = await self.db.execute(
            select(ContextPackage).where(
                and_(
                    ContextPackage.owner_agent_id == owner_agent_id,
                    ContextPackage.name == name,
                )
            )
        )
        existing_pkg = existing.scalar_one_or_none()

        # Compute content for checksum and size
        content = {
            "goals": goals or {},
            "memories": memories or {},
            "conversation_history": conversation_history or [],
            "reasoning_trace": reasoning_trace or [],
            "decisions_made": decisions_made or [],
            "constraints": constraints or {},
            "preferences": preferences or {},
        }
        content_json = json.dumps(content, sort_keys=True)
        checksum = hashlib.sha256(content_json.encode()).hexdigest()
        size_bytes = len(content_json.encode())

        expires_at = None
        if expires_in_hours:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

        if existing_pkg:
            # Update existing package (new version)
            existing_pkg.version += 1
            existing_pkg.summary = summary
            existing_pkg.goals = goals or {}
            existing_pkg.memories = memories or {}
            existing_pkg.conversation_history = conversation_history or []
            existing_pkg.reasoning_trace = reasoning_trace or []
            existing_pkg.decisions_made = decisions_made or []
            existing_pkg.constraints = constraints or {}
            existing_pkg.preferences = preferences or {}
            existing_pkg.tags = tags or []
            existing_pkg.checksum = checksum
            existing_pkg.size_bytes = size_bytes
            existing_pkg.is_public = is_public
            existing_pkg.allowed_agents = allowed_agents or []
            existing_pkg.expires_at = expires_at

            await self.db.commit()
            await self.db.refresh(existing_pkg)
            return existing_pkg

        # Create new package
        package = ContextPackage(
            owner_agent_id=owner_agent_id,
            name=name,
            summary=summary,
            goals=goals or {},
            memories=memories or {},
            conversation_history=conversation_history or [],
            reasoning_trace=reasoning_trace or [],
            decisions_made=decisions_made or [],
            constraints=constraints or {},
            preferences=preferences or {},
            tags=tags or [],
            checksum=checksum,
            size_bytes=size_bytes,
            is_public=is_public,
            allowed_agents=allowed_agents or [],
            expires_at=expires_at,
        )
        self.db.add(package)
        await self.db.commit()
        await self.db.refresh(package)

        return package

    async def get_package(self, package_id: UUID) -> ContextPackage | None:
        """Get a context package by ID."""
        result = await self.db.execute(
            select(ContextPackage).where(ContextPackage.id == package_id)
        )
        return result.scalar_one_or_none()

    async def list_packages(
        self,
        owner_agent_id: UUID,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[ContextPackage]:
        """List context packages for an agent."""
        query = select(ContextPackage).where(
            ContextPackage.owner_agent_id == owner_agent_id
        )

        if tags:
            query = query.where(ContextPackage.tags.overlap(tags))

        query = query.order_by(ContextPackage.updated_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_package(self, package_id: UUID, owner_id: UUID) -> None:
        """Delete a context package."""
        result = await self.db.execute(
            select(ContextPackage).where(
                and_(
                    ContextPackage.id == package_id,
                    ContextPackage.owner_agent_id == owner_id,
                )
            )
        )
        package = result.scalar_one_or_none()

        if not package:
            raise ValueError("Package not found or not owned by agent")

        await self.db.delete(package)
        await self.db.commit()

    # ==================== Transfers ====================

    async def transfer_context(
        self,
        package_id: UUID,
        sender_id: UUID,
        receiver_id: UUID,
        purpose: str | None = None,
        message: str | None = None,
        related_goal_id: UUID | None = None,
        related_task_id: UUID | None = None,
    ) -> ContextTransfer:
        """Transfer context to another agent."""
        package = await self.get_package(package_id)
        if not package:
            raise ValueError("Package not found")

        # Check access
        if package.owner_agent_id != sender_id:
            if not package.is_public and str(sender_id) not in package.allowed_agents:
                raise ValueError("Not authorized to transfer this package")

        transfer = ContextTransfer(
            package_id=package_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            purpose=purpose,
            message=message,
            status=TransferStatus.SENT,
            sent_at=datetime.now(timezone.utc),
            related_goal_id=related_goal_id,
            related_task_id=related_task_id,
        )
        self.db.add(transfer)
        await self.db.commit()
        await self.db.refresh(transfer)

        return transfer

    async def get_transfer(self, transfer_id: UUID) -> ContextTransfer | None:
        """Get a transfer by ID."""
        result = await self.db.execute(
            select(ContextTransfer).where(ContextTransfer.id == transfer_id)
        )
        return result.scalar_one_or_none()

    async def receive_transfer(
        self,
        transfer_id: UUID,
        receiver_id: UUID,
    ) -> ContextTransfer:
        """Mark a transfer as received."""
        result = await self.db.execute(
            select(ContextTransfer).where(
                and_(
                    ContextTransfer.id == transfer_id,
                    ContextTransfer.receiver_id == receiver_id,
                )
            )
        )
        transfer = result.scalar_one_or_none()

        if not transfer:
            raise ValueError("Transfer not found")

        transfer.status = TransferStatus.RECEIVED
        transfer.received_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(transfer)

        return transfer

    async def accept_transfer(
        self,
        transfer_id: UUID,
        receiver_id: UUID,
        accept: bool,
        message: str | None = None,
    ) -> ContextTransfer:
        """Accept or reject a transfer."""
        result = await self.db.execute(
            select(ContextTransfer).where(
                and_(
                    ContextTransfer.id == transfer_id,
                    ContextTransfer.receiver_id == receiver_id,
                )
            )
        )
        transfer = result.scalar_one_or_none()

        if not transfer:
            raise ValueError("Transfer not found")

        if accept:
            transfer.status = TransferStatus.ACCEPTED
        else:
            transfer.status = TransferStatus.REJECTED
            transfer.status_message = message

        await self.db.commit()
        await self.db.refresh(transfer)

        return transfer

    async def apply_transfer(
        self,
        transfer_id: UUID,
        receiver_id: UUID,
    ) -> ContextTransfer:
        """Mark a transfer as applied."""
        result = await self.db.execute(
            select(ContextTransfer).where(
                and_(
                    ContextTransfer.id == transfer_id,
                    ContextTransfer.receiver_id == receiver_id,
                    ContextTransfer.status == TransferStatus.ACCEPTED,
                )
            )
        )
        transfer = result.scalar_one_or_none()

        if not transfer:
            raise ValueError("Transfer not found or not accepted")

        transfer.status = TransferStatus.APPLIED
        transfer.applied_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(transfer)

        return transfer

    async def list_incoming_transfers(
        self,
        receiver_id: UUID,
        status: TransferStatus | None = None,
        limit: int = 50,
    ) -> list[ContextTransfer]:
        """List incoming transfers for an agent."""
        query = select(ContextTransfer).where(
            ContextTransfer.receiver_id == receiver_id
        )

        if status:
            query = query.where(ContextTransfer.status == status)

        query = query.order_by(ContextTransfer.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_outgoing_transfers(
        self,
        sender_id: UUID,
        status: TransferStatus | None = None,
        limit: int = 50,
    ) -> list[ContextTransfer]:
        """List outgoing transfers from an agent."""
        query = select(ContextTransfer).where(
            ContextTransfer.sender_id == sender_id
        )

        if status:
            query = query.where(ContextTransfer.status == status)

        query = query.order_by(ContextTransfer.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Diff ====================

    async def compute_diff(
        self,
        package_id: UUID,
        previous_version: int | None = None,
    ) -> dict:
        """Compute diff between package versions."""
        package = await self.get_package(package_id)
        if not package:
            raise ValueError("Package not found")

        # For now, return current state as the diff
        # In a full implementation, we'd store version history
        return {
            "package_id": str(package_id),
            "current_version": package.version,
            "previous_version": previous_version,
            "changes": {
                "goals_count": len(package.goals) if package.goals else 0,
                "memories_count": len(package.memories) if package.memories else 0,
                "conversation_length": len(package.conversation_history) if package.conversation_history else 0,
                "decisions_count": len(package.decisions_made) if package.decisions_made else 0,
            },
            "summary": f"Package '{package.name}' v{package.version}",
        }

    async def unpack_context(
        self,
        package_id: UUID,
        requester_id: UUID,
    ) -> dict:
        """Unpack a context package for use."""
        package = await self.get_package(package_id)
        if not package:
            raise ValueError("Package not found")

        # Check access
        if package.owner_agent_id != requester_id:
            if not package.is_public and str(requester_id) not in package.allowed_agents:
                raise ValueError("Not authorized to access this package")

        # Check expiration
        if package.expires_at and package.expires_at < datetime.now(timezone.utc):
            raise ValueError("Package has expired")

        return {
            "id": str(package.id),
            "name": package.name,
            "version": package.version,
            "summary": package.summary,
            "goals": package.goals,
            "memories": package.memories,
            "conversation_history": package.conversation_history,
            "reasoning_trace": package.reasoning_trace,
            "decisions_made": package.decisions_made,
            "constraints": package.constraints,
            "preferences": package.preferences,
        }
