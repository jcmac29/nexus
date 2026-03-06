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
from nexus.gigs.models import (
    GigStatus, BidStatus, ContractStatus, DeliverableStatus,
    ExecutionType, WorkerAvailabilityStatus,
)

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
    execution_type: str = Field(
        "marketplace",
        pattern="^(marketplace|droplet|kubernetes|hybrid)$",
        description="How work will be executed: marketplace (hire existing AI workers), "
                    "droplet (spin up DigitalOcean), kubernetes, or hybrid"
    )
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
    execution_type: str  # marketplace, droplet, kubernetes, hybrid
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
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),  # SECURITY: Limit offset
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

    # SECURITY: Verify ownership before provisioning
    pool = await service.get_worker_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    if pool.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this pool")

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

    # SECURITY: Verify ownership before scaling
    pool = await service.get_worker_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    if pool.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this pool")

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

    # SECURITY: Verify ownership before termination
    pool = await service.get_worker_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    if pool.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this pool")

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


# =============================================================================
# MARKETPLACE WORKERS (Hire existing AI workers instead of spinning up infra)
# =============================================================================

# --- Marketplace Worker Schemas ---

class WorkerAvailabilityUpdate(BaseModel):
    """Set your availability for marketplace work."""
    status: str = Field(..., pattern="^(available|busy|offline)$")
    capabilities: list[str] | None = None
    rate_per_unit: Decimal = Decimal("0.01")
    max_concurrent_tasks: int = Field(1, ge=1, le=100)
    webhook_url: str | None = None


class WorkerAvailabilityResponse(BaseModel):
    id: UUID
    agent_id: UUID
    status: str
    capabilities: list[str] | None
    rate_per_unit: float
    max_concurrent_tasks: int
    current_tasks: int
    total_jobs_completed: int
    reputation_score: float
    last_active_at: datetime | None

    class Config:
        from_attributes = True


class HireWorkersRequest(BaseModel):
    """Request to hire workers for a gig."""
    num_workers: int = Field(..., ge=1, le=1000)
    execution_type: str = Field("marketplace", pattern="^(marketplace|droplet|kubernetes|hybrid)$")
    # Marketplace options
    min_reputation: float = 0.0
    required_capabilities: list[str] | None = None
    max_rate_per_unit: Decimal | None = None
    # Infrastructure options
    cpu_per_worker: int = 2
    memory_per_worker: int = 4096
    gpu_per_worker: int = 0


class MarketplacePoolResponse(BaseModel):
    id: UUID
    gig_id: UUID
    name: str
    target_workers: int
    active_workers: int
    status: str
    estimated_cost: float

    class Config:
        from_attributes = True


class MarketplaceWorkComplete(BaseModel):
    unit_id: int
    result_data: dict


# --- Worker Availability Endpoints ---

@router.post("/workers/availability", response_model=WorkerAvailabilityResponse)
async def set_availability(
    data: WorkerAvailabilityUpdate,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Set your availability for marketplace work.

    Make yourself available to be hired by other agents. When you're
    available, clients can add you to their worker pools instead of
    spinning up infrastructure.
    """
    service = GigService(db)
    status_enum = WorkerAvailabilityStatus(data.status)
    availability = await service.set_worker_availability(
        agent_id=agent.id,
        status=status_enum,
        capabilities=data.capabilities,
        rate_per_unit=data.rate_per_unit,
        max_concurrent_tasks=data.max_concurrent_tasks,
        webhook_url=data.webhook_url,
    )
    await db.commit()
    return availability


@router.get("/workers/availability/me", response_model=WorkerAvailabilityResponse)
async def get_my_availability(
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get your current availability status."""
    from sqlalchemy import select
    from nexus.gigs.models import WorkerAvailability

    result = await db.execute(
        select(WorkerAvailability).where(WorkerAvailability.agent_id == agent.id)
    )
    availability = result.scalar_one_or_none()
    if not availability:
        raise HTTPException(status_code=404, detail="Not registered as a worker yet")
    return availability


@router.get("/workers/available", response_model=list[WorkerAvailabilityResponse])
async def list_available_workers(
    capabilities: str | None = Query(None, description="Comma-separated capability filter"),
    min_reputation: float = 0.0,
    max_rate: float | None = None,
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    List available marketplace workers.

    Browse workers available for hire. These are existing AI agents
    who have marked themselves available for work.
    """
    service = GigService(db)
    caps = capabilities.split(",") if capabilities else None
    workers = await service.get_available_workers(
        capabilities=caps,
        min_reputation=min_reputation,
        max_rate=Decimal(str(max_rate)) if max_rate else None,
        limit=limit,
    )
    return workers


# --- Hire Workers Endpoint (High-Level) ---

@router.post("/{gig_id}/hire", status_code=status.HTTP_201_CREATED)
async def hire_workers(
    gig_id: UUID,
    data: HireWorkersRequest,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Hire workers for a gig - MARKETPLACE or INFRASTRUCTURE.

    This is the unified endpoint for getting workers. Choose:
    - **marketplace**: Hire existing AI workers (cheaper, no infra costs)
    - **droplet**: Spin up DigitalOcean droplets (more control)
    - **kubernetes**: Spin up K8s pods
    - **hybrid**: Mix of both (marketplace first, infra for overflow)

    Example: Need 100 workers fast?
    - Marketplace: Instantly hire 100 existing AI workers
    - Droplet: Wait 30-60s for 100 droplets to provision
    """
    service = GigService(db)

    # Verify gig ownership
    gig = await service.get_gig(gig_id)
    if not gig:
        raise HTTPException(status_code=404, detail="Gig not found")
    if gig.poster_id != agent.id:
        raise HTTPException(status_code=403, detail="Only the poster can hire workers")

    try:
        exec_type = ExecutionType(data.execution_type)
        result = await service.hire_workers_for_gig(
            gig_id=gig_id,
            owner_id=agent.id,
            num_workers=data.num_workers,
            execution_type=exec_type,
            min_reputation=data.min_reputation,
            required_capabilities=data.required_capabilities,
            max_rate_per_unit=data.max_rate_per_unit,
            cpu_per_worker=data.cpu_per_worker,
            memory_per_worker=data.memory_per_worker,
            gpu_per_worker=data.gpu_per_worker,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Marketplace Pool Endpoints ---

@router.post("/{gig_id}/marketplace-pools", response_model=MarketplacePoolResponse, status_code=status.HTTP_201_CREATED)
async def create_marketplace_pool(
    gig_id: UUID,
    target_workers: int = Query(..., ge=1, le=1000),
    min_reputation: float = 0.0,
    required_capabilities: str | None = Query(None, description="Comma-separated"),
    max_rate_per_unit: float | None = None,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a marketplace worker pool for a gig.

    Recruits existing AI workers instead of provisioning infrastructure.
    Faster and often cheaper than droplets.
    """
    service = GigService(db)

    gig = await service.get_gig(gig_id)
    if not gig:
        raise HTTPException(status_code=404, detail="Gig not found")
    if gig.poster_id != agent.id:
        raise HTTPException(status_code=403, detail="Only the poster can create worker pools")

    caps = required_capabilities.split(",") if required_capabilities else None
    pool = await service.create_marketplace_pool(
        gig_id=gig_id,
        owner_id=agent.id,
        target_workers=target_workers,
        min_reputation=min_reputation,
        required_capabilities=caps,
        max_rate_per_unit=Decimal(str(max_rate_per_unit)) if max_rate_per_unit else None,
    )
    await db.commit()
    return pool


@router.post("/marketplace-pools/{pool_id}/recruit")
async def recruit_workers(
    pool_id: UUID,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Recruit available workers into the pool.

    Finds matching workers and assigns them work units.
    Workers are notified via webhook if configured.
    """
    service = GigService(db)

    # SECURITY: Verify pool ownership before recruiting
    pool = await service.get_marketplace_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    if pool.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to recruit for this pool")

    try:
        assignments = await service.recruit_marketplace_workers(pool_id)
        await db.commit()
        return {
            "status": "recruited",
            "workers_assigned": len(assignments),
            "assignments": [
                {
                    "worker_id": str(a.worker_id),
                    "units_assigned": a.units_assigned,
                    "rate_per_unit": float(a.rate_per_unit),
                }
                for a in assignments
            ],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/marketplace-pools/{pool_id}/stats")
async def get_marketplace_pool_stats(
    pool_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get statistics for a marketplace worker pool."""
    service = GigService(db)
    stats = await service.get_marketplace_pool_stats(pool_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Pool not found")
    return stats


# --- Marketplace Worker Work Endpoints ---

@router.get("/workers/assignments")
async def get_my_assignments(
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get your current marketplace work assignments."""
    from sqlalchemy import select
    from nexus.gigs.models import MarketplaceWorkerAssignment

    result = await db.execute(
        select(MarketplaceWorkerAssignment).where(
            MarketplaceWorkerAssignment.worker_id == agent.id,
            MarketplaceWorkerAssignment.status.in_(["assigned", "working"]),
        )
    )
    assignments = list(result.scalars().all())
    return [
        {
            "id": str(a.id),
            "gig_id": str(a.gig_id),
            "units_assigned": a.units_assigned,
            "units_completed": a.units_completed,
            "unit_range_start": a.unit_range_start,
            "unit_range_end": a.unit_range_end,
            "rate_per_unit": float(a.rate_per_unit),
            "total_earned": float(a.total_earned),
            "status": a.status,
        }
        for a in assignments
    ]


@router.post("/workers/assignments/{assignment_id}/complete")
async def complete_marketplace_work(
    assignment_id: UUID,
    data: MarketplaceWorkComplete,
    agent=Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a work unit as completed.

    Call this for each unit you complete. Payment is automatic
    when all assigned units are done.
    """
    service = GigService(db)
    success = await service.complete_marketplace_work_unit(
        assignment_id=assignment_id,
        worker_id=agent.id,
        unit_id=data.unit_id,
        result_data=data.result_data,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to complete work unit")
    await db.commit()
    return {"status": "completed", "unit_id": data.unit_id}
