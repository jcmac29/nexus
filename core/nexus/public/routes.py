"""Public marketplace API routes."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent, get_optional_agent
from nexus.identity.models import Agent
from nexus.public.models import ApprovalPolicy, PublishStatus, RequestStatus
from nexus.public.service import PublicMarketplaceService

router = APIRouter(prefix="/public", tags=["public-marketplace"])


# --- Schemas ---


class PublishCapabilityRequest(BaseModel):
    """Request to publish a capability."""
    capability_id: UUID
    public_name: str
    public_description: str
    category: str
    tags: list[str] = []
    approval_policy: ApprovalPolicy = ApprovalPolicy.MANUAL
    max_requests_per_hour: int = 10
    max_requests_per_day: int = 100
    price_per_request: Decimal | None = None
    allowed_memory_namespaces: list[str] = []
    allowed_input_fields: list[str] = []


class PublishedCapabilityResponse(BaseModel):
    """Published capability info."""
    id: UUID
    public_name: str
    public_description: str
    category: str
    tags: list[str]
    status: PublishStatus
    approval_policy: ApprovalPolicy
    max_requests_per_hour: int
    max_requests_per_day: int
    price_per_request: Decimal | None
    total_requests: int
    successful_requests: int

    class Config:
        from_attributes = True


class PublicInvokeRequest(BaseModel):
    """Request to invoke a public capability."""
    input: dict


class PublicRequestResponse(BaseModel):
    """Public request info."""
    id: UUID
    status: RequestStatus
    requires_approval: bool
    payment_required: bool
    payment_amount: Decimal | None
    created_at: str
    message: str | None = None

    class Config:
        from_attributes = True


class BlockRequesterRequest(BaseModel):
    """Request to block a requester."""
    agent_id: UUID | None = None
    ip_address: str | None = None
    reason: str = "Blocked by owner"
    duration_hours: int | None = None


class ReputationResponse(BaseModel):
    """Agent reputation info."""
    overall_score: int
    reliability_score: int
    quality_score: int
    safety_score: int
    is_verified: bool
    total_requests_served: int

    class Config:
        from_attributes = True


# --- Publishing Endpoints ---


@router.post("/publish", response_model=PublishedCapabilityResponse)
async def publish_capability(
    request: PublishCapabilityRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Publish a capability to the public marketplace.

    SAFETY: Starts as draft. You must explicitly publish after review.

    Default safety settings:
    - Manual approval required for each request
    - No access to private memory
    - Rate limited to 10/hour, 100/day
    """
    service = PublicMarketplaceService(session)
    pub = await service.create_published_capability(
        agent_id=agent.id,
        capability_id=request.capability_id,
        public_name=request.public_name,
        public_description=request.public_description,
        category=request.category,
        tags=request.tags,
        approval_policy=request.approval_policy,
        max_requests_per_hour=request.max_requests_per_hour,
        max_requests_per_day=request.max_requests_per_day,
        price_per_request=request.price_per_request,
        allowed_memory_namespaces=request.allowed_memory_namespaces,
        allowed_input_fields=request.allowed_input_fields,
    )
    return pub


@router.post("/publish/{published_id}/submit-review")
async def submit_for_review(
    published_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Submit capability for safety review before publishing."""
    service = PublicMarketplaceService(session)
    pub = await service.submit_for_review(published_id, agent.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Not found or already submitted")
    return {"status": "pending_review", "message": "Submitted for safety review"}


@router.post("/publish/{published_id}/go-live")
async def go_live(
    published_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Make capability live and discoverable.

    WARNING: This exposes your capability to the public.
    Ensure your safety settings are configured correctly.
    """
    service = PublicMarketplaceService(session)
    pub = await service.publish_capability(published_id, agent.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "published", "message": "Capability is now live"}


@router.post("/publish/{published_id}/unpublish")
async def unpublish(
    published_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Immediately unpublish a capability (kill switch).

    Use this if you see suspicious activity or need to stop requests.
    """
    service = PublicMarketplaceService(session)
    success = await service.unpublish_capability(published_id, agent.id)
    if not success:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "suspended", "message": "Capability unpublished immediately"}


@router.get("/my-publications", response_model=list[PublishedCapabilityResponse])
async def my_publications(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """List your published capabilities."""
    service = PublicMarketplaceService(session)
    return await service.list_published_capabilities(
        agent_id=agent.id, published_only=False
    )


# --- Discovery Endpoints (Public) ---


@router.get("/capabilities", response_model=list[PublishedCapabilityResponse])
async def discover_capabilities(
    category: str | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """
    Discover public capabilities.

    No authentication required - this is the public marketplace.
    """
    service = PublicMarketplaceService(session)
    return await service.list_published_capabilities(
        category=category, search=search, published_only=True
    )


@router.get("/capabilities/{published_id}", response_model=PublishedCapabilityResponse)
async def get_capability(
    published_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Get details of a public capability."""
    service = PublicMarketplaceService(session)
    pub = await service.get_published_capability(published_id)
    if not pub or pub.status != PublishStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Not found")
    return pub


# --- Invocation Endpoints ---


@router.post("/capabilities/{published_id}/invoke")
async def invoke_public_capability(
    published_id: UUID,
    request: PublicInvokeRequest,
    http_request: Request,
    agent: Agent | None = Depends(get_optional_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Request to invoke a public capability.

    If the capability requires approval, this creates a pending request.
    If auto-approved, it queues for execution.

    You will receive a request ID to track status.
    """
    service = PublicMarketplaceService(session)

    result = await service.create_public_request(
        published_capability_id=published_id,
        input_data=request.input,
        requester_agent_id=agent.id if agent else None,
        requester_ip=http_request.client.host if http_request.client else None,
        requester_user_agent=http_request.headers.get("user-agent"),
    )

    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "request_id": result.id,
        "status": result.status.value,
        "requires_approval": result.requires_approval,
        "payment_required": result.payment_required,
        "message": "Request submitted. Check status for updates."
        if result.requires_approval
        else "Request approved and queued for execution.",
    }


# --- Request Management (for capability owners) ---


@router.get("/requests/pending")
async def pending_requests(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """List requests waiting for your approval."""
    service = PublicMarketplaceService(session)
    requests = await service.list_pending_requests(agent.id)
    return [
        {
            "id": r.id,
            "capability_id": r.published_capability_id,
            "requester_agent_id": r.requester_agent_id,
            "input_preview": r.input_preview,
            "created_at": r.created_at.isoformat(),
        }
        for r in requests
    ]


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Approve a pending request."""
    service = PublicMarketplaceService(session)
    result = await service.approve_request(request_id, agent.id)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found or already processed")
    return {"status": "approved", "request_id": request_id}


@router.post("/requests/{request_id}/reject")
async def reject_request(
    request_id: UUID,
    reason: str = "Rejected by owner",
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Reject a pending request."""
    service = PublicMarketplaceService(session)
    result = await service.reject_request(request_id, agent.id, reason)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found or already processed")
    return {"status": "rejected", "request_id": request_id, "reason": reason}


# --- Blocking ---


@router.post("/block")
async def block_requester(
    request: BlockRequesterRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Block an agent or IP from using your capabilities.

    Blocked requesters will receive an error when trying to invoke.
    """
    if not request.agent_id and not request.ip_address:
        raise HTTPException(
            status_code=400, detail="Must specify agent_id or ip_address"
        )

    service = PublicMarketplaceService(session)
    block = await service.block_requester(
        owner_agent_id=agent.id,
        blocked_agent_id=request.agent_id,
        blocked_ip=request.ip_address,
        reason=request.reason,
        duration_hours=request.duration_hours,
    )
    return {
        "block_id": block.id,
        "message": "Requester blocked",
        "expires_at": block.expires_at.isoformat() if block.expires_at else "never",
    }


@router.delete("/block/{block_id}")
async def unblock_requester(
    block_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Remove a block."""
    service = PublicMarketplaceService(session)
    success = await service.unblock_requester(block_id, agent.id)
    if not success:
        raise HTTPException(status_code=404, detail="Block not found")
    return {"message": "Requester unblocked"}


# --- Reputation ---


@router.get("/reputation/{agent_id}", response_model=ReputationResponse)
async def get_reputation(
    agent_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Get an agent's public reputation score."""
    service = PublicMarketplaceService(session)
    reputation = await service.get_or_create_reputation(agent_id)
    return reputation


@router.get("/reputation/me", response_model=ReputationResponse)
async def my_reputation(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get your own reputation score."""
    service = PublicMarketplaceService(session)
    reputation = await service.get_or_create_reputation(agent.id)
    return reputation
