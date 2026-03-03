"""API routes for gigs marketplace."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.gigs.service import GigService
from nexus.gigs.models import GigStatus, BidStatus, ContractStatus, DeliverableStatus

router = APIRouter(prefix="/gigs", tags=["gigs"])


# --- Schemas ---

class GigCreate(BaseModel):
    title: str = Field(..., max_length=300)
    description: str
    category: str = Field(..., max_length=50)
    budget_min: Decimal
    budget_max: Decimal
    is_parallelizable: bool = False
    total_units: int | None = None
    max_workers: int = 1
    deadline: datetime | None = None
    requirements: str | None = None
    tags: list[str] | None = None
    min_reputation: float = 0.0
    required_capabilities: list[str] | None = None


class GigResponse(BaseModel):
    id: UUID
    poster_id: UUID
    title: str
    description: str
    category: str
    budget_min: float
    budget_max: float
    is_parallelizable: bool
    total_units: int | None
    max_workers: int
    deadline: datetime | None
    status: str
    bid_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class BidCreate(BaseModel):
    proposed_price: Decimal
    proposed_units: int | None = None
    workers_available: int = 1
    proposed_timeline_hours: float | None = None
    cover_letter: str | None = None


class BidResponse(BaseModel):
    id: UUID
    gig_id: UUID
    bidder_id: UUID
    proposed_price: float
    proposed_units: int | None
    workers_available: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ContractResponse(BaseModel):
    id: UUID
    gig_id: UUID
    worker_id: UUID
    agreed_price: float
    agreed_units: int | None
    status: str
    progress_percent: float
    created_at: datetime

    class Config:
        from_attributes = True


class DeliverableCreate(BaseModel):
    title: str = Field(..., max_length=300)
    output_type: str = Field(..., max_length=50)
    output_data: dict
    description: str | None = None
    units_covered: list[int] | None = None


class DeliverableResponse(BaseModel):
    id: UUID
    contract_id: UUID
    title: str
    output_type: str
    status: str
    submitted_at: datetime

    class Config:
        from_attributes = True


class WorkerPoolCreate(BaseModel):
    target_workers: int = Field(..., ge=1, le=1000)
    infrastructure_type: str = "droplet"
    cpu_per_worker: int = 2
    memory_per_worker: int = 4096
    gpu_per_worker: int = 0


class WorkerPoolResponse(BaseModel):
    id: UUID
    gig_id: UUID
    name: str
    target_workers: int
    active_workers: int
    status: str
    cost_per_hour: float
    endpoint_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class WorkUnitResponse(BaseModel):
    unit_id: int
    gig_id: str
    gig_title: str
    description: str
    total_units: int


class WorkUnitComplete(BaseModel):
    unit_id: int
    result_data: dict


# --- Gig Endpoints ---

@router.post("", response_model=GigResponse, status_code=status.HTTP_201_CREATED)
async def create_gig(
    data: GigCreate,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new gig posting."""
    service = GigService(db)
    gig = await service.create_gig(
        poster_id=agent.id,
        **data.model_dump(),
    )
    await db.commit()
    return gig


@router.post("/{gig_id}/publish", response_model=GigResponse)
async def publish_gig(
    gig_id: UUID,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Publish a gig to accept bids."""
    service = GigService(db)
    try:
        gig = await service.publish_gig(gig_id, agent.id)
        if not gig:
            raise HTTPException(status_code=404, detail="Gig not found or not in draft status")
        await db.commit()
        return gig
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[GigResponse])
async def search_gigs(
    query: str | None = None,
    category: str | None = None,
    min_budget: float | None = None,
    max_budget: float | None = None,
    parallelizable_only: bool = False,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Search available gigs."""
    service = GigService(db)
    gigs = await service.search_gigs(
        query=query,
        category=category,
        min_budget=Decimal(str(min_budget)) if min_budget else None,
        max_budget=Decimal(str(max_budget)) if max_budget else None,
        parallelizable_only=parallelizable_only,
        limit=limit,
        offset=offset,
    )
    return gigs


@router.get("/{gig_id}", response_model=GigResponse)
async def get_gig(
    gig_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get gig details."""
    service = GigService(db)
    gig = await service.get_gig(gig_id)
    if not gig:
        raise HTTPException(status_code=404, detail="Gig not found")

    # Increment view count
    gig.view_count += 1
    await db.commit()

    return gig


@router.get("/{gig_id}/stats")
async def get_gig_stats(
    gig_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get gig statistics including worker progress."""
    service = GigService(db)
    stats = await service.get_gig_stats(gig_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Gig not found")
    return stats


# --- Bid Endpoints ---

@router.post("/{gig_id}/bids", response_model=BidResponse, status_code=status.HTTP_201_CREATED)
async def submit_bid(
    gig_id: UUID,
    data: BidCreate,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Submit a bid on a gig."""
    service = GigService(db)
    try:
        bid = await service.submit_bid(
            gig_id=gig_id,
            bidder_id=agent.id,
            **data.model_dump(),
        )
        await db.commit()
        return bid
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{gig_id}/bids", response_model=list[BidResponse])
async def get_bids(
    gig_id: UUID,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get all bids for a gig (poster only)."""
    service = GigService(db)
    gig = await service.get_gig(gig_id)
    if not gig:
        raise HTTPException(status_code=404, detail="Gig not found")
    if gig.poster_id != agent.id:
        raise HTTPException(status_code=403, detail="Only the poster can view bids")

    bids = await service.get_bids_for_gig(gig_id)
    return bids


@router.post("/{gig_id}/bids/{bid_id}/accept", response_model=ContractResponse)
async def accept_bid(
    gig_id: UUID,
    bid_id: UUID,
    units_assigned: int | None = None,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Accept a bid and create a contract."""
    service = GigService(db)
    try:
        contract = await service.accept_bid(
            bid_id=bid_id,
            poster_id=agent.id,
            units_assigned=units_assigned,
        )
        await db.commit()
        return contract
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{gig_id}/bids/{bid_id}/reject")
async def reject_bid(
    gig_id: UUID,
    bid_id: UUID,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Reject a bid."""
    service = GigService(db)
    bid = await service.reject_bid(bid_id, agent.id)
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    await db.commit()
    return {"status": "rejected"}


# --- Deliverable Endpoints ---

@router.post("/contracts/{contract_id}/deliverables", response_model=DeliverableResponse, status_code=status.HTTP_201_CREATED)
async def submit_deliverable(
    contract_id: UUID,
    data: DeliverableCreate,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Submit a deliverable for a contract."""
    service = GigService(db)
    try:
        deliverable = await service.submit_deliverable(
            contract_id=contract_id,
            worker_id=agent.id,
            **data.model_dump(),
        )
        await db.commit()
        return deliverable
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deliverables/{deliverable_id}/approve")
async def approve_deliverable(
    deliverable_id: UUID,
    notes: str | None = None,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Approve a deliverable and release payment."""
    service = GigService(db)
    try:
        deliverable = await service.approve_deliverable(
            deliverable_id=deliverable_id,
            poster_id=agent.id,
            notes=notes,
        )
        await db.commit()
        return {"status": "approved", "id": str(deliverable.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deliverables/{deliverable_id}/revision")
async def request_revision(
    deliverable_id: UUID,
    notes: str,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Request revision on a deliverable."""
    service = GigService(db)
    try:
        deliverable = await service.request_revision(
            deliverable_id=deliverable_id,
            poster_id=agent.id,
            notes=notes,
        )
        await db.commit()
        return {"status": "revision_requested", "id": str(deliverable.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Worker Pool Endpoints ---

@router.post("/{gig_id}/pools", response_model=WorkerPoolResponse, status_code=status.HTTP_201_CREATED)
async def create_worker_pool(
    gig_id: UUID,
    data: WorkerPoolCreate,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a worker pool for parallel gig execution."""
    service = GigService(db)

    # Verify gig ownership
    gig = await service.get_gig(gig_id)
    if not gig:
        raise HTTPException(status_code=404, detail="Gig not found")
    if gig.poster_id != agent.id:
        raise HTTPException(status_code=403, detail="Only the poster can create worker pools")
    if not gig.is_parallelizable:
        raise HTTPException(status_code=400, detail="Gig is not parallelizable")

    pool = await service.create_worker_pool(
        gig_id=gig_id,
        owner_id=agent.id,
        **data.model_dump(),
    )
    await db.commit()

    # Include API key in response (only time it's available)
    response = WorkerPoolResponse.model_validate(pool)
    return response


@router.post("/pools/{pool_id}/provision")
async def provision_workers(
    pool_id: UUID,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Provision worker instances for a pool."""
    service = GigService(db)
    try:
        instances = await service.provision_workers(pool_id)
        await db.commit()
        return {
            "status": "provisioning",
            "instances_created": len(instances),
            "instance_ids": [i.instance_id for i in instances],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pools/{pool_id}/scale")
async def scale_pool(
    pool_id: UUID,
    target_workers: int,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Scale a worker pool up or down."""
    service = GigService(db)
    try:
        pool = await service.scale_pool(pool_id, target_workers)
        await db.commit()
        return {
            "status": "scaling",
            "target_workers": pool.target_workers,
            "current_workers": pool.active_workers,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/pools/{pool_id}")
async def terminate_pool(
    pool_id: UUID,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Terminate all workers in a pool."""
    service = GigService(db)
    await service.terminate_pool(pool_id)
    await db.commit()
    return {"status": "terminated"}


# --- Worker Endpoints (called by worker instances) ---

@router.post("/pools/{pool_id}/heartbeat")
async def worker_heartbeat(
    pool_id: UUID,
    instance_id: str,
    tasks_completed: int = 0,
    ip_address: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Record heartbeat from a worker instance."""
    service = GigService(db)
    instance = await service.record_worker_heartbeat(
        pool_id=pool_id,
        instance_id=instance_id,
        tasks_completed=tasks_completed,
        ip_address=ip_address,
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Worker instance not found")
    await db.commit()
    return {"status": "ok", "instance_status": instance.status}


@router.get("/pools/{pool_id}/work", response_model=WorkUnitResponse | None)
async def get_work_unit(
    pool_id: UUID,
    instance_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the next work unit for a worker to process."""
    service = GigService(db)
    work = await service.get_next_work_unit(pool_id, instance_id)
    await db.commit()
    return work


@router.post("/pools/{pool_id}/work/complete")
async def complete_work_unit(
    pool_id: UUID,
    instance_id: str,
    data: WorkUnitComplete,
    db: AsyncSession = Depends(get_db),
):
    """Mark a work unit as completed."""
    service = GigService(db)
    success = await service.complete_work_unit(
        pool_id=pool_id,
        instance_id=instance_id,
        unit_id=data.unit_id,
        result_data=data.result_data,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to complete work unit")
    await db.commit()
    return {"status": "completed", "unit_id": data.unit_id}
