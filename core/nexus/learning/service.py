"""Learning service for agent feedback and improvement."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.learning.models import (
    Feedback,
    FeedbackType,
    Improvement,
    ImprovementStatus,
    Pattern,
)

if TYPE_CHECKING:
    pass


class LearningService:
    """Service for managing agent learning from feedback."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Feedback ====================

    async def record_feedback(
        self,
        agent_id: UUID,
        action_type: str,
        feedback_type: FeedbackType,
        action_description: str | None = None,
        input_data: dict | None = None,
        output_data: dict | None = None,
        error_message: str | None = None,
        context_tags: list[str] | None = None,
        related_agent_id: UUID | None = None,
        related_goal_id: UUID | None = None,
        duration_ms: int | None = None,
        confidence_score: float | None = None,
    ) -> Feedback:
        """Record feedback for an action."""
        feedback = Feedback(
            agent_id=agent_id,
            action_type=action_type,
            action_description=action_description,
            input_data=input_data or {},
            feedback_type=feedback_type,
            output_data=output_data or {},
            error_message=error_message,
            context_tags=context_tags or [],
            related_agent_id=related_agent_id,
            related_goal_id=related_goal_id,
            duration_ms=duration_ms,
            confidence_score=confidence_score,
        )
        self.db.add(feedback)
        await self.db.commit()
        await self.db.refresh(feedback)

        # Update patterns
        await self._update_patterns(agent_id, action_type, feedback)

        return feedback

    async def get_feedback(
        self,
        agent_id: UUID,
        action_type: str | None = None,
        feedback_type: FeedbackType | None = None,
        limit: int = 100,
    ) -> list[Feedback]:
        """Get feedback for an agent."""
        query = select(Feedback).where(Feedback.agent_id == agent_id)

        if action_type:
            query = query.where(Feedback.action_type == action_type)
        if feedback_type:
            query = query.where(Feedback.feedback_type == feedback_type)

        query = query.order_by(Feedback.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Patterns ====================

    async def get_patterns(
        self,
        agent_id: UUID,
        action_type: str | None = None,
        min_attempts: int = 5,
        min_success_rate: float | None = None,
    ) -> list[Pattern]:
        """Get learned patterns for an agent."""
        query = select(Pattern).where(
            and_(
                Pattern.agent_id == agent_id,
                Pattern.total_attempts >= min_attempts,
            )
        )

        if action_type:
            query = query.where(Pattern.action_type == action_type)
        if min_success_rate is not None:
            query = query.where(Pattern.success_rate >= min_success_rate)

        query = query.order_by(Pattern.success_rate.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_pattern_for_context(
        self,
        agent_id: UUID,
        action_type: str,
        context: dict,
    ) -> Pattern | None:
        """Get pattern for a specific context."""
        context_signature = self._compute_context_signature(context)

        result = await self.db.execute(
            select(Pattern).where(
                and_(
                    Pattern.agent_id == agent_id,
                    Pattern.action_type == action_type,
                    Pattern.context_signature == context_signature,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _update_patterns(
        self,
        agent_id: UUID,
        action_type: str,
        feedback: Feedback,
    ) -> None:
        """Update patterns based on new feedback."""
        # Create context signature from input data
        context_signature = self._compute_context_signature(feedback.input_data or {})

        # Get or create pattern
        result = await self.db.execute(
            select(Pattern).where(
                and_(
                    Pattern.agent_id == agent_id,
                    Pattern.action_type == action_type,
                    Pattern.context_signature == context_signature,
                )
            )
        )
        pattern = result.scalar_one_or_none()

        if not pattern:
            pattern = Pattern(
                agent_id=agent_id,
                action_type=action_type,
                context_signature=context_signature,
                total_attempts=0,
                success_count=0,
                failure_count=0,
                success_rate=0.0,
            )
            self.db.add(pattern)

        # Update statistics
        pattern.total_attempts += 1
        if feedback.feedback_type == FeedbackType.SUCCESS:
            pattern.success_count += 1
        elif feedback.feedback_type in [FeedbackType.FAILURE, FeedbackType.ERROR]:
            pattern.failure_count += 1
            if feedback.error_message:
                if pattern.failure_modes is None:
                    pattern.failure_modes = []
                if feedback.error_message not in pattern.failure_modes:
                    pattern.failure_modes = pattern.failure_modes + [feedback.error_message[:200]]

        pattern.success_rate = pattern.success_count / pattern.total_attempts

        # Update average duration
        if feedback.duration_ms:
            if pattern.avg_duration_ms:
                pattern.avg_duration_ms = int(
                    (pattern.avg_duration_ms * (pattern.total_attempts - 1) + feedback.duration_ms)
                    / pattern.total_attempts
                )
            else:
                pattern.avg_duration_ms = feedback.duration_ms

        await self.db.commit()

        # Check if we should suggest improvements
        if pattern.total_attempts >= 10 and pattern.success_rate < 0.5:
            await self._suggest_improvement(agent_id, pattern)

    def _compute_context_signature(self, context: dict) -> str:
        """Compute a signature for context matching."""
        # Extract key features for matching
        keys = sorted(context.keys())
        signature_data = json.dumps(keys, sort_keys=True)
        return hashlib.sha256(signature_data.encode()).hexdigest()[:32]

    # ==================== Improvements ====================

    async def get_improvements(
        self,
        agent_id: UUID,
        status: ImprovementStatus | None = None,
        limit: int = 50,
    ) -> list[Improvement]:
        """Get improvement suggestions."""
        query = select(Improvement).where(Improvement.agent_id == agent_id)

        if status:
            query = query.where(Improvement.status == status)

        query = query.order_by(Improvement.priority_score.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def accept_improvement(
        self,
        improvement_id: UUID,
        accept: bool,
        reason: str | None = None,
    ) -> Improvement:
        """Accept or reject an improvement."""
        result = await self.db.execute(
            select(Improvement).where(Improvement.id == improvement_id)
        )
        improvement = result.scalar_one_or_none()

        if not improvement:
            raise ValueError("Improvement not found")

        if accept:
            improvement.status = ImprovementStatus.ACCEPTED
        else:
            improvement.status = ImprovementStatus.REJECTED

        improvement.status_reason = reason
        await self.db.commit()
        await self.db.refresh(improvement)

        return improvement

    async def mark_implemented(
        self,
        improvement_id: UUID,
        implementation_data: dict | None = None,
    ) -> Improvement:
        """Mark an improvement as implemented."""
        result = await self.db.execute(
            select(Improvement).where(Improvement.id == improvement_id)
        )
        improvement = result.scalar_one_or_none()

        if not improvement:
            raise ValueError("Improvement not found")

        improvement.status = ImprovementStatus.IMPLEMENTED
        improvement.implementation_data = implementation_data or {}
        improvement.implemented_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(improvement)

        return improvement

    async def _suggest_improvement(
        self,
        agent_id: UUID,
        pattern: Pattern,
    ) -> None:
        """Suggest an improvement based on pattern analysis."""
        # Check if we already have a suggestion for this pattern
        existing = await self.db.execute(
            select(Improvement).where(
                and_(
                    Improvement.agent_id == agent_id,
                    Improvement.pattern_id == pattern.id,
                    Improvement.status == ImprovementStatus.SUGGESTED,
                )
            )
        )
        if existing.scalar_one_or_none():
            return

        # Create improvement suggestion
        improvement = Improvement(
            agent_id=agent_id,
            pattern_id=pattern.id,
            title=f"Improve {pattern.action_type} performance",
            description=(
                f"Action '{pattern.action_type}' has a {pattern.success_rate:.1%} success rate "
                f"over {pattern.total_attempts} attempts. Common failure modes: "
                f"{', '.join(pattern.failure_modes[:3]) if pattern.failure_modes else 'None recorded'}"
            ),
            improvement_type="behavior",
            expected_impact=f"Potential to improve success rate from {pattern.success_rate:.1%}",
            priority_score=1.0 - pattern.success_rate,
        )
        self.db.add(improvement)
        await self.db.commit()

    # ==================== Analysis ====================

    async def get_success_rate(
        self,
        agent_id: UUID,
        action_type: str | None = None,
        days: int = 30,
    ) -> dict:
        """Get success rate statistics."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        query = select(
            Feedback.feedback_type,
            func.count(Feedback.id).label("count"),
        ).where(
            and_(
                Feedback.agent_id == agent_id,
                Feedback.created_at >= cutoff,
            )
        )

        if action_type:
            query = query.where(Feedback.action_type == action_type)

        query = query.group_by(Feedback.feedback_type)

        result = await self.db.execute(query)
        rows = result.all()

        counts = {ft.value: 0 for ft in FeedbackType}
        for feedback_type, count in rows:
            counts[feedback_type.value] = count

        total = sum(counts.values())
        success_rate = counts["success"] / total if total > 0 else 0.0

        return {
            "total": total,
            "success_rate": success_rate,
            "counts": counts,
            "period_days": days,
        }
