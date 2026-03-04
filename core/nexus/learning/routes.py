"""Learning API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.learning.models import FeedbackType, ImprovementStatus
from nexus.learning.schemas import (
    AcceptImprovementRequest,
    FeedbackResponse,
    ImprovementResponse,
    PatternResponse,
    QueryPatternsRequest,
    RecordFeedbackRequest,
)
from nexus.learning.service import LearningService

router = APIRouter(prefix="/learning", tags=["learning"])


@router.post("/feedback", status_code=201)
async def record_feedback(
    request: RecordFeedbackRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """Record feedback for an action."""
    service = LearningService(db)

    feedback = await service.record_feedback(
        agent_id=agent.id,
        action_type=request.action_type,
        feedback_type=FeedbackType(request.feedback_type),
        action_description=request.action_description,
        input_data=request.input_data,
        output_data=request.output_data,
        error_message=request.error_message,
        context_tags=request.context_tags,
        related_agent_id=request.related_agent_id,
        related_goal_id=request.related_goal_id,
        duration_ms=request.duration_ms,
        confidence_score=request.confidence_score,
    )

    return FeedbackResponse(
        id=feedback.id,
        agent_id=feedback.agent_id,
        action_type=feedback.action_type,
        feedback_type=feedback.feedback_type.value,
        context_tags=feedback.context_tags or [],
        duration_ms=feedback.duration_ms,
        created_at=feedback.created_at,
    )


@router.get("/feedback")
async def list_feedback(
    action_type: str | None = None,
    feedback_type: str | None = None,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackResponse]:
    """List feedback for the agent."""
    service = LearningService(db)

    ft = FeedbackType(feedback_type) if feedback_type else None
    feedback_list = await service.get_feedback(
        agent_id=agent.id,
        action_type=action_type,
        feedback_type=ft,
        limit=limit,
    )

    return [
        FeedbackResponse(
            id=f.id,
            agent_id=f.agent_id,
            action_type=f.action_type,
            feedback_type=f.feedback_type.value,
            context_tags=f.context_tags or [],
            duration_ms=f.duration_ms,
            created_at=f.created_at,
        )
        for f in feedback_list
    ]


@router.get("/patterns")
async def list_patterns(
    action_type: str | None = None,
    min_attempts: int = 5,
    min_success_rate: float | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[PatternResponse]:
    """List learned patterns."""
    service = LearningService(db)

    patterns = await service.get_patterns(
        agent_id=agent.id,
        action_type=action_type,
        min_attempts=min_attempts,
        min_success_rate=min_success_rate,
    )

    return [
        PatternResponse(
            id=p.id,
            agent_id=p.agent_id,
            action_type=p.action_type,
            total_attempts=p.total_attempts,
            success_count=p.success_count,
            failure_count=p.failure_count,
            success_rate=p.success_rate,
            avg_duration_ms=p.avg_duration_ms,
            best_practices=p.best_practices,
            failure_modes=p.failure_modes or [],
            recommended_approach=p.recommended_approach,
            last_updated=p.last_updated,
        )
        for p in patterns
    ]


@router.get("/patterns/{action_type}")
async def get_pattern_for_action(
    action_type: str,
    context: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> PatternResponse | None:
    """Get pattern for a specific action type."""
    service = LearningService(db)

    import json
    ctx = json.loads(context) if context else {}

    pattern = await service.get_pattern_for_context(
        agent_id=agent.id,
        action_type=action_type,
        context=ctx,
    )

    if not pattern:
        return None

    return PatternResponse(
        id=pattern.id,
        agent_id=pattern.agent_id,
        action_type=pattern.action_type,
        total_attempts=pattern.total_attempts,
        success_count=pattern.success_count,
        failure_count=pattern.failure_count,
        success_rate=pattern.success_rate,
        avg_duration_ms=pattern.avg_duration_ms,
        best_practices=pattern.best_practices,
        failure_modes=pattern.failure_modes or [],
        recommended_approach=pattern.recommended_approach,
        last_updated=pattern.last_updated,
    )


@router.get("/improvements")
async def list_improvements(
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[ImprovementResponse]:
    """List improvement suggestions."""
    service = LearningService(db)

    imp_status = ImprovementStatus(status) if status else None
    improvements = await service.get_improvements(
        agent_id=agent.id,
        status=imp_status,
        limit=limit,
    )

    return [
        ImprovementResponse(
            id=i.id,
            agent_id=i.agent_id,
            title=i.title,
            description=i.description,
            improvement_type=i.improvement_type,
            expected_impact=i.expected_impact,
            priority_score=i.priority_score,
            status=i.status.value,
            created_at=i.created_at,
        )
        for i in improvements
    ]


@router.post("/improvements/{improvement_id}/decide")
async def decide_improvement(
    improvement_id: UUID,
    request: AcceptImprovementRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ImprovementResponse:
    """Accept or reject an improvement suggestion."""
    service = LearningService(db)

    try:
        improvement = await service.accept_improvement(
            improvement_id=improvement_id,
            accept=request.accept,
            reason=request.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ImprovementResponse(
        id=improvement.id,
        agent_id=improvement.agent_id,
        title=improvement.title,
        description=improvement.description,
        improvement_type=improvement.improvement_type,
        expected_impact=improvement.expected_impact,
        priority_score=improvement.priority_score,
        status=improvement.status.value,
        created_at=improvement.created_at,
    )


@router.get("/stats")
async def get_learning_stats(
    action_type: str | None = None,
    days: int = Query(default=30, le=365),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get learning statistics."""
    service = LearningService(db)

    stats = await service.get_success_rate(
        agent_id=agent.id,
        action_type=action_type,
        days=days,
    )

    return stats
