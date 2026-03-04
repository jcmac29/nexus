"""Reputation API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.reputation.models import DisputeStatus
from nexus.reputation.schemas import (
    DisputeRequest,
    DisputeResponse,
    ReputationHistoryResponse,
    ReputationScoreResponse,
    VouchRequest,
    VouchResponse,
)
from nexus.reputation.service import ReputationService

router = APIRouter(prefix="/reputation", tags=["reputation"])


@router.get("/me")
async def get_my_reputation(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ReputationScoreResponse:
    """Get my reputation score."""
    service = ReputationService(db)
    score = await service.get_or_create_score(agent.id)

    return ReputationScoreResponse(
        agent_id=score.agent_id,
        overall_score=score.overall_score,
        reliability_score=score.reliability_score,
        quality_score=score.quality_score,
        responsiveness_score=score.responsiveness_score,
        collaboration_score=score.collaboration_score,
        total_interactions=score.total_interactions,
        successful_interactions=score.successful_interactions,
        vouches_received=score.vouches_received,
        disputes_received=score.disputes_received,
        tier=score.tier,
        last_activity=score.last_activity,
    )


@router.get("/{agent_id}")
async def get_agent_reputation(
    agent_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ReputationScoreResponse:
    """Get reputation score for an agent."""
    service = ReputationService(db)
    score = await service.get_score(agent_id)

    if not score:
        raise HTTPException(status_code=404, detail="Agent reputation not found")

    return ReputationScoreResponse(
        agent_id=score.agent_id,
        overall_score=score.overall_score,
        reliability_score=score.reliability_score,
        quality_score=score.quality_score,
        responsiveness_score=score.responsiveness_score,
        collaboration_score=score.collaboration_score,
        total_interactions=score.total_interactions,
        successful_interactions=score.successful_interactions,
        vouches_received=score.vouches_received,
        disputes_received=score.disputes_received,
        tier=score.tier,
        last_activity=score.last_activity,
    )


@router.post("/{agent_id}/vouch", status_code=201)
async def vouch_for_agent(
    agent_id: UUID,
    request: VouchRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> VouchResponse:
    """Vouch for another agent."""
    service = ReputationService(db)

    try:
        vouch = await service.vouch(
            voucher_id=agent.id,
            vouchee_id=agent_id,
            category=request.category,
            strength=request.strength,
            message=request.message,
            interaction_id=request.interaction_id,
            capabilities=request.capabilities,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return VouchResponse(
        id=vouch.id,
        voucher_id=vouch.voucher_id,
        vouchee_id=vouch.vouchee_id,
        category=vouch.category,
        strength=vouch.strength,
        message=vouch.message,
        is_active=vouch.is_active,
        created_at=vouch.created_at,
    )


@router.delete("/vouches/{vouch_id}")
async def revoke_vouch(
    vouch_id: UUID,
    reason: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke a vouch."""
    service = ReputationService(db)

    try:
        await service.revoke_vouch(vouch_id, agent.id, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "revoked"}


@router.get("/{agent_id}/vouches")
async def get_vouches_for_agent(
    agent_id: UUID,
    active_only: bool = True,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[VouchResponse]:
    """Get vouches for an agent."""
    service = ReputationService(db)
    vouches = await service.get_vouches_for(agent_id, active_only)

    return [
        VouchResponse(
            id=v.id,
            voucher_id=v.voucher_id,
            vouchee_id=v.vouchee_id,
            category=v.category,
            strength=v.strength,
            message=v.message,
            is_active=v.is_active,
            created_at=v.created_at,
        )
        for v in vouches
    ]


@router.post("/{agent_id}/dispute", status_code=201)
async def file_dispute(
    agent_id: UUID,
    request: DisputeRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> DisputeResponse:
    """File a dispute against an agent."""
    service = ReputationService(db)

    try:
        dispute = await service.file_dispute(
            reporter_id=agent.id,
            accused_id=agent_id,
            category=request.category,
            title=request.title,
            description=request.description,
            severity=request.severity,
            evidence=request.evidence,
            interaction_id=request.interaction_id,
            related_goal_id=request.related_goal_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DisputeResponse(
        id=dispute.id,
        reporter_id=dispute.reporter_id,
        accused_id=dispute.accused_id,
        category=dispute.category,
        severity=dispute.severity,
        title=dispute.title,
        status=dispute.status.value,
        resolution_notes=dispute.resolution_notes,
        reputation_impact=dispute.reputation_impact,
        created_at=dispute.created_at,
        resolved_at=dispute.resolved_at,
    )


@router.get("/{agent_id}/disputes")
async def get_disputes(
    agent_id: UUID,
    status: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[DisputeResponse]:
    """Get disputes against an agent."""
    service = ReputationService(db)

    ds = DisputeStatus(status) if status else None
    disputes = await service.get_disputes_for(agent_id, ds)

    return [
        DisputeResponse(
            id=d.id,
            reporter_id=d.reporter_id,
            accused_id=d.accused_id,
            category=d.category,
            severity=d.severity,
            title=d.title,
            status=d.status.value,
            resolution_notes=d.resolution_notes,
            reputation_impact=d.reputation_impact,
            created_at=d.created_at,
            resolved_at=d.resolved_at,
        )
        for d in disputes
    ]


@router.post("/disputes/{dispute_id}/resolve")
async def resolve_dispute(
    dispute_id: UUID,
    is_valid: bool,
    resolution_notes: str | None = None,
    reputation_impact: float = 0.0,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> DisputeResponse:
    """Resolve a dispute."""
    service = ReputationService(db)

    try:
        dispute = await service.resolve_dispute(
            dispute_id=dispute_id,
            resolver_id=agent.id,
            is_valid=is_valid,
            resolution_notes=resolution_notes,
            reputation_impact=reputation_impact,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DisputeResponse(
        id=dispute.id,
        reporter_id=dispute.reporter_id,
        accused_id=dispute.accused_id,
        category=dispute.category,
        severity=dispute.severity,
        title=dispute.title,
        status=dispute.status.value,
        resolution_notes=dispute.resolution_notes,
        reputation_impact=dispute.reputation_impact,
        created_at=dispute.created_at,
        resolved_at=dispute.resolved_at,
    )


@router.post("/interactions")
async def record_interaction(
    success: bool,
    related_agent_id: UUID | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record an interaction outcome."""
    service = ReputationService(db)
    await service.record_interaction(agent.id, success, related_agent_id)
    return {"status": "recorded"}


@router.get("/{agent_id}/history")
async def get_reputation_history(
    agent_id: UUID,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ReputationHistoryResponse:
    """Get reputation history for an agent."""
    service = ReputationService(db)
    events = await service.get_events(agent_id, limit=limit)

    return ReputationHistoryResponse(
        agent_id=agent_id,
        events=[
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "description": e.description,
                "score_delta": e.score_delta,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        score_trend=[],  # Would calculate from events
    )
