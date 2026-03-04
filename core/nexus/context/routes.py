"""Context API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.context.models import TransferStatus
from nexus.context.schemas import (
    AcceptTransferRequest,
    ContextDiffResponse,
    ContextPackageDetailResponse,
    ContextPackageResponse,
    ContextTransferResponse,
    PackContextRequest,
    TransferContextRequest,
)
from nexus.context.service import ContextService

router = APIRouter(prefix="/context", tags=["context"])


def _package_to_response(pkg) -> ContextPackageResponse:
    return ContextPackageResponse(
        id=pkg.id,
        owner_agent_id=pkg.owner_agent_id,
        name=pkg.name,
        version=pkg.version,
        summary=pkg.summary,
        tags=pkg.tags or [],
        size_bytes=pkg.size_bytes,
        is_public=pkg.is_public,
        expires_at=pkg.expires_at,
        created_at=pkg.created_at,
    )


def _transfer_to_response(transfer) -> ContextTransferResponse:
    return ContextTransferResponse(
        id=transfer.id,
        package_id=transfer.package_id,
        sender_id=transfer.sender_id,
        receiver_id=transfer.receiver_id,
        purpose=transfer.purpose,
        status=transfer.status.value,
        diff_summary=transfer.diff_summary,
        sent_at=transfer.sent_at,
        received_at=transfer.received_at,
        applied_at=transfer.applied_at,
        created_at=transfer.created_at,
    )


@router.post("/pack", status_code=201)
async def pack_context(
    request: PackContextRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ContextPackageResponse:
    """Pack context into a transferable package."""
    service = ContextService(db)

    package = await service.pack_context(
        owner_agent_id=agent.id,
        name=request.name,
        summary=request.summary,
        goals=request.goals,
        memories=request.memories,
        conversation_history=request.conversation_history,
        reasoning_trace=request.reasoning_trace,
        decisions_made=request.decisions_made,
        constraints=request.constraints,
        preferences=request.preferences,
        tags=request.tags,
        is_public=request.is_public,
        allowed_agents=request.allowed_agents,
        expires_in_hours=request.expires_in_hours,
    )

    return _package_to_response(package)


@router.get("/packages")
async def list_packages(
    tags: str | None = None,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[ContextPackageResponse]:
    """List my context packages."""
    service = ContextService(db)

    tag_list = tags.split(",") if tags else None
    packages = await service.list_packages(agent.id, tag_list, limit)

    return [_package_to_response(p) for p in packages]


@router.get("/packages/{package_id}")
async def get_package(
    package_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ContextPackageDetailResponse:
    """Get a context package with full details."""
    service = ContextService(db)

    try:
        content = await service.unpack_context(package_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    package = await service.get_package(package_id)

    return ContextPackageDetailResponse(
        id=package.id,
        owner_agent_id=package.owner_agent_id,
        name=package.name,
        version=package.version,
        summary=package.summary,
        tags=package.tags or [],
        size_bytes=package.size_bytes,
        is_public=package.is_public,
        expires_at=package.expires_at,
        created_at=package.created_at,
        goals=content.get("goals"),
        memories=content.get("memories"),
        conversation_history=content.get("conversation_history"),
        reasoning_trace=content.get("reasoning_trace"),
        decisions_made=content.get("decisions_made"),
        constraints=content.get("constraints"),
        preferences=content.get("preferences"),
    )


@router.delete("/packages/{package_id}")
async def delete_package(
    package_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a context package."""
    service = ContextService(db)

    try:
        await service.delete_package(package_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "deleted"}


@router.get("/packages/{package_id}/unpack")
async def unpack_context(
    package_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unpack a context package for use."""
    service = ContextService(db)

    try:
        content = await service.unpack_context(package_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return content


@router.post("/transfer", status_code=201)
async def transfer_context(
    request: TransferContextRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ContextTransferResponse:
    """Transfer context to another agent."""
    service = ContextService(db)

    try:
        transfer = await service.transfer_context(
            package_id=request.package_id,
            sender_id=agent.id,
            receiver_id=request.receiver_id,
            purpose=request.purpose,
            message=request.message,
            related_goal_id=request.related_goal_id,
            related_task_id=request.related_task_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _transfer_to_response(transfer)


@router.get("/transfers/incoming")
async def list_incoming_transfers(
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[ContextTransferResponse]:
    """List incoming context transfers."""
    service = ContextService(db)

    ts = TransferStatus(status) if status else None
    transfers = await service.list_incoming_transfers(agent.id, ts, limit)

    return [_transfer_to_response(t) for t in transfers]


@router.get("/transfers/outgoing")
async def list_outgoing_transfers(
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[ContextTransferResponse]:
    """List outgoing context transfers."""
    service = ContextService(db)

    ts = TransferStatus(status) if status else None
    transfers = await service.list_outgoing_transfers(agent.id, ts, limit)

    return [_transfer_to_response(t) for t in transfers]


@router.post("/transfers/{transfer_id}/receive")
async def receive_transfer(
    transfer_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ContextTransferResponse:
    """Mark a transfer as received."""
    service = ContextService(db)

    try:
        transfer = await service.receive_transfer(transfer_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _transfer_to_response(transfer)


@router.post("/transfers/{transfer_id}/decide")
async def decide_transfer(
    transfer_id: UUID,
    request: AcceptTransferRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ContextTransferResponse:
    """Accept or reject a transfer."""
    service = ContextService(db)

    try:
        transfer = await service.accept_transfer(
            transfer_id, agent.id, request.accept, request.message
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _transfer_to_response(transfer)


@router.post("/transfers/{transfer_id}/apply")
async def apply_transfer(
    transfer_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ContextTransferResponse:
    """Apply a transfer (mark as used)."""
    service = ContextService(db)

    try:
        transfer = await service.apply_transfer(transfer_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _transfer_to_response(transfer)


@router.get("/diff/{package_id}")
async def get_diff(
    package_id: UUID,
    previous_version: int | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ContextDiffResponse:
    """Get diff for a context package."""
    service = ContextService(db)

    try:
        diff = await service.compute_diff(package_id, previous_version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ContextDiffResponse(
        package_id=UUID(diff["package_id"]),
        previous_version=diff["previous_version"],
        current_version=diff["current_version"],
        changes=diff["changes"],
        summary=diff["summary"],
    )
