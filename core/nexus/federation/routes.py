"""Federation API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.federation.models import PeerStatus, TrustLevel
from nexus.federation.service import FederationService

router = APIRouter(prefix="/federation", tags=["federation"])


# --- Request/Response Schemas ---


class InitiatePeeringRequest(BaseModel):
    """Request to initiate peering with another instance."""
    peer_name: str
    peer_endpoint: str
    trust_level: TrustLevel = TrustLevel.STANDARD


class InitiatePeeringResponse(BaseModel):
    """Response with peering credentials to share."""
    peer_id: UUID
    your_peer_id: str
    shared_secret: str
    status: str
    message: str


class AcceptPeeringRequest(BaseModel):
    """Request to accept incoming peering."""
    peer_name: str
    peer_endpoint: str
    their_peer_id: str
    their_secret: str
    trust_level: TrustLevel = TrustLevel.STANDARD


class PeerInfo(BaseModel):
    """Information about a federated peer."""
    id: UUID
    name: str
    endpoint_url: str
    status: PeerStatus
    trust_level: TrustLevel
    requests_sent: int
    requests_received: int

    class Config:
        from_attributes = True


class RemoteInvokeRequest(BaseModel):
    """Request to invoke capability on remote peer."""
    agent_slug: str
    capability_name: str
    input: dict
    require_approval: bool = True


# --- Peer Management Endpoints ---


@router.post("/peers/initiate", response_model=InitiatePeeringResponse)
async def initiate_peering(
    request: InitiatePeeringRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Initiate a peering connection with another Nexus instance.

    This generates credentials that you share with the other instance.
    They use these to complete the connection.
    """
    service = FederationService(session)
    peer, secret = await service.initiate_peering(
        owner_agent_id=agent.id,
        peer_name=request.peer_name,
        peer_endpoint=request.peer_endpoint,
        trust_level=request.trust_level,
    )

    return InitiatePeeringResponse(
        peer_id=peer.id,
        your_peer_id=peer.our_peer_id,
        shared_secret=secret,
        status="pending",
        message="Share these credentials with the peer to complete connection",
    )


@router.post("/peers/accept", response_model=PeerInfo)
async def accept_peering(
    request: AcceptPeeringRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Accept an incoming peering request.

    Use the credentials shared by the initiating instance.
    """
    service = FederationService(session)
    peer = await service.accept_peering(
        owner_agent_id=agent.id,
        peer_name=request.peer_name,
        peer_endpoint=request.peer_endpoint,
        their_peer_id=request.their_peer_id,
        their_secret=request.their_secret,
        trust_level=request.trust_level,
    )
    return peer


@router.get("/peers", response_model=list[PeerInfo])
async def list_peers(
    status: PeerStatus | None = None,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """List all federated peers."""
    service = FederationService(session)
    return await service.list_peers(agent.id, status)


@router.get("/peers/{peer_id}", response_model=PeerInfo)
async def get_peer(
    peer_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get details of a specific peer."""
    service = FederationService(session)
    peer = await service.get_peer(peer_id)
    if not peer or peer.owner_agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Peer not found")
    return peer


@router.post("/peers/{peer_id}/suspend")
async def suspend_peer(
    peer_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Temporarily suspend a peer connection."""
    service = FederationService(session)
    peer = await service.get_peer(peer_id)
    if not peer or peer.owner_agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Peer not found")

    await service.update_peer_status(peer_id, PeerStatus.SUSPENDED)
    return {"status": "suspended"}


@router.post("/peers/{peer_id}/activate")
async def activate_peer(
    peer_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Activate a suspended peer connection."""
    service = FederationService(session)
    peer = await service.get_peer(peer_id)
    if not peer or peer.owner_agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Peer not found")

    await service.update_peer_status(peer_id, PeerStatus.ACTIVE)
    return {"status": "active"}


@router.delete("/peers/{peer_id}")
async def revoke_peer(
    peer_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Permanently revoke a peer connection."""
    service = FederationService(session)
    peer = await service.get_peer(peer_id)
    if not peer or peer.owner_agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Peer not found")

    await service.update_peer_status(peer_id, PeerStatus.REVOKED)
    return {"status": "revoked"}


# --- Remote Discovery & Invocation ---


@router.get("/peers/{peer_id}/capabilities")
async def discover_remote_capabilities(
    peer_id: UUID,
    query: str | None = None,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Discover capabilities available on a remote peer."""
    service = FederationService(session)
    peer = await service.get_peer(peer_id)
    if not peer or peer.owner_agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Peer not found")

    capabilities = await service.discover_remote_capabilities(peer_id, query)
    return {"capabilities": capabilities}


@router.post("/peers/{peer_id}/invoke")
async def invoke_remote_capability(
    peer_id: UUID,
    request: RemoteInvokeRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Invoke a capability on a remote peer's agent."""
    service = FederationService(session)
    peer = await service.get_peer(peer_id)
    if not peer or peer.owner_agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Peer not found")

    result = await service.invoke_remote_capability(
        peer_id=peer_id,
        agent_slug=request.agent_slug,
        capability_name=request.capability_name,
        input_data=request.input,
        require_approval=request.require_approval,
    )
    return result


# --- Inbound Endpoints (called by peers) ---


@router.get("/capabilities")
async def federated_capabilities(
    x_nexus_peer_id: str = Header(...),
    x_nexus_signature: str = Header(...),
    session: AsyncSession = Depends(get_db),
):
    """
    [Called by peers] Return published capabilities.

    This endpoint is called by federated peers to discover
    what capabilities this instance exposes.
    """
    service = FederationService(session)
    capabilities = await service.handle_inbound_discovery(
        peer_id=x_nexus_peer_id,
        signature=x_nexus_signature,
    )
    return capabilities


@router.post("/invoke/{agent_slug}/{capability_name}")
async def federated_invoke(
    agent_slug: str,
    capability_name: str,
    request: dict,
    x_nexus_peer_id: str = Header(...),
    x_nexus_signature: str = Header(...),
    session: AsyncSession = Depends(get_db),
):
    """
    [Called by peers] Invoke a capability.

    This endpoint is called by federated peers to invoke
    a published capability on this instance.
    """
    service = FederationService(session)
    result = await service.handle_inbound_invocation(
        peer_id=x_nexus_peer_id,
        signature=x_nexus_signature,
        agent_slug=agent_slug,
        capability_name=capability_name,
        input_data=request.get("input", {}),
    )
    return result
