"""Reputation service for decentralized trust."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.reputation.models import (
    Dispute,
    DisputeStatus,
    ReputationEvent,
    ReputationScore,
    Vouch,
)

if TYPE_CHECKING:
    pass


class ReputationService:
    """Service for managing agent reputation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Scores ====================

    async def get_score(self, agent_id: UUID) -> ReputationScore | None:
        """Get reputation score for an agent."""
        result = await self.db.execute(
            select(ReputationScore).where(ReputationScore.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_score(self, agent_id: UUID) -> ReputationScore:
        """Get or create reputation score for an agent."""
        score = await self.get_score(agent_id)
        if not score:
            score = ReputationScore(agent_id=agent_id)
            self.db.add(score)
            await self.db.commit()
            await self.db.refresh(score)
        return score

    async def recalculate_score(self, agent_id: UUID) -> ReputationScore:
        """Recalculate reputation score based on events."""
        score = await self.get_or_create_score(agent_id)

        # Get vouches
        vouches_result = await self.db.execute(
            select(
                func.count(Vouch.id),
                func.avg(Vouch.strength),
            ).where(
                and_(
                    Vouch.vouchee_id == agent_id,
                    Vouch.is_active == True,
                )
            )
        )
        vouch_data = vouches_result.one()
        vouch_count = vouch_data[0] or 0
        avg_vouch_strength = vouch_data[1] or 0.5

        # Get disputes
        disputes_result = await self.db.execute(
            select(
                func.count(Dispute.id),
            ).where(
                and_(
                    Dispute.accused_id == agent_id,
                    Dispute.status.in_([DisputeStatus.OPEN, DisputeStatus.RESOLVED_VALID]),
                )
            )
        )
        dispute_count = disputes_result.scalar() or 0

        # Calculate scores
        base_score = 0.5

        # Vouch bonus (max +0.3)
        vouch_bonus = min(0.3, (vouch_count * avg_vouch_strength) / 20)

        # Dispute penalty (max -0.4)
        dispute_penalty = min(0.4, dispute_count * 0.1)

        # Interaction bonus
        interaction_bonus = min(0.2, score.total_interactions / 500)

        # Success rate bonus
        if score.total_interactions > 0:
            success_rate = score.successful_interactions / score.total_interactions
            success_bonus = (success_rate - 0.5) * 0.2  # -0.1 to +0.1
        else:
            success_bonus = 0

        overall = base_score + vouch_bonus - dispute_penalty + interaction_bonus + success_bonus
        overall = max(0.0, min(1.0, overall))

        # Update score
        score.overall_score = overall
        score.vouches_received = vouch_count
        score.disputes_received = dispute_count
        score.last_calculated = datetime.now(timezone.utc)

        # Update tier
        if overall >= 0.9:
            score.tier = "platinum"
        elif overall >= 0.75:
            score.tier = "gold"
        elif overall >= 0.6:
            score.tier = "silver"
        else:
            score.tier = "bronze"

        await self.db.commit()
        await self.db.refresh(score)

        return score

    # ==================== Vouches ====================

    async def vouch(
        self,
        voucher_id: UUID,
        vouchee_id: UUID,
        category: str,
        strength: float = 1.0,
        message: str | None = None,
        interaction_id: UUID | None = None,
        capabilities: list[str] | None = None,
    ) -> Vouch:
        """Vouch for another agent."""
        if voucher_id == vouchee_id:
            raise ValueError("Cannot vouch for yourself")

        # Check existing vouch
        existing = await self.db.execute(
            select(Vouch).where(
                and_(
                    Vouch.voucher_id == voucher_id,
                    Vouch.vouchee_id == vouchee_id,
                    Vouch.category == category,
                    Vouch.is_active == True,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Already vouched for this agent in this category")

        vouch = Vouch(
            voucher_id=voucher_id,
            vouchee_id=vouchee_id,
            category=category,
            strength=strength,
            message=message,
            interaction_id=interaction_id,
            capabilities=capabilities or [],
        )
        self.db.add(vouch)

        # Record event
        await self._record_event(
            vouchee_id,
            "vouch_received",
            f"Received vouch from agent in category '{category}'",
            score_delta=0.02,
            category_affected=category,
            source_agent_id=voucher_id,
            related_id=vouch.id,
        )

        # Update voucher stats
        voucher_score = await self.get_or_create_score(voucher_id)
        voucher_score.vouches_given += 1

        await self.db.commit()
        await self.db.refresh(vouch)

        # Recalculate vouchee score
        await self.recalculate_score(vouchee_id)

        return vouch

    async def revoke_vouch(
        self,
        vouch_id: UUID,
        voucher_id: UUID,
        reason: str | None = None,
    ) -> None:
        """Revoke a vouch."""
        result = await self.db.execute(
            select(Vouch).where(
                and_(
                    Vouch.id == vouch_id,
                    Vouch.voucher_id == voucher_id,
                    Vouch.is_active == True,
                )
            )
        )
        vouch = result.scalar_one_or_none()

        if not vouch:
            raise ValueError("Vouch not found or already revoked")

        vouch.is_active = False
        vouch.revoked_at = datetime.now(timezone.utc)
        vouch.revoke_reason = reason

        await self.db.commit()

        # Recalculate vouchee score
        await self.recalculate_score(vouch.vouchee_id)

    async def get_vouches_for(
        self,
        agent_id: UUID,
        active_only: bool = True,
    ) -> list[Vouch]:
        """Get vouches for an agent."""
        query = select(Vouch).where(Vouch.vouchee_id == agent_id)
        if active_only:
            query = query.where(Vouch.is_active == True)
        query = query.order_by(Vouch.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_vouches_by(
        self,
        agent_id: UUID,
        active_only: bool = True,
    ) -> list[Vouch]:
        """Get vouches given by an agent."""
        query = select(Vouch).where(Vouch.voucher_id == agent_id)
        if active_only:
            query = query.where(Vouch.is_active == True)
        query = query.order_by(Vouch.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Disputes ====================

    async def file_dispute(
        self,
        reporter_id: UUID,
        accused_id: UUID,
        category: str,
        title: str,
        description: str,
        severity: str = "medium",
        evidence: dict | None = None,
        interaction_id: UUID | None = None,
        related_goal_id: UUID | None = None,
    ) -> Dispute:
        """File a dispute against an agent."""
        if reporter_id == accused_id:
            raise ValueError("Cannot file dispute against yourself")

        dispute = Dispute(
            reporter_id=reporter_id,
            accused_id=accused_id,
            category=category,
            severity=severity,
            title=title,
            description=description,
            evidence=evidence or {},
            interaction_id=interaction_id,
            related_goal_id=related_goal_id,
        )
        self.db.add(dispute)

        # Record event
        await self._record_event(
            accused_id,
            "dispute_filed",
            f"Dispute filed: {title}",
            score_delta=-0.05,
            category_affected=category,
            source_agent_id=reporter_id,
            related_id=dispute.id,
        )

        await self.db.commit()
        await self.db.refresh(dispute)

        # Recalculate score
        await self.recalculate_score(accused_id)

        return dispute

    async def resolve_dispute(
        self,
        dispute_id: UUID,
        resolver_id: UUID,
        is_valid: bool,
        resolution_notes: str | None = None,
        reputation_impact: float = 0.0,
    ) -> Dispute:
        """Resolve a dispute."""
        result = await self.db.execute(
            select(Dispute).where(Dispute.id == dispute_id)
        )
        dispute = result.scalar_one_or_none()

        if not dispute:
            raise ValueError("Dispute not found")

        if is_valid:
            dispute.status = DisputeStatus.RESOLVED_VALID
            dispute.reputation_impact = reputation_impact

            # Record negative event
            await self._record_event(
                dispute.accused_id,
                "dispute_resolved_valid",
                f"Dispute resolved against agent: {dispute.title}",
                score_delta=-reputation_impact,
                source_agent_id=resolver_id,
                related_id=dispute_id,
            )
        else:
            dispute.status = DisputeStatus.RESOLVED_INVALID

        dispute.resolution_notes = resolution_notes
        dispute.resolved_by = resolver_id
        dispute.resolved_at = datetime.now(timezone.utc)

        # Update score stats
        score = await self.get_or_create_score(dispute.accused_id)
        score.disputes_resolved += 1

        await self.db.commit()
        await self.db.refresh(dispute)

        # Recalculate score
        await self.recalculate_score(dispute.accused_id)

        return dispute

    async def get_disputes_for(
        self,
        agent_id: UUID,
        status: DisputeStatus | None = None,
    ) -> list[Dispute]:
        """Get disputes against an agent."""
        query = select(Dispute).where(Dispute.accused_id == agent_id)
        if status:
            query = query.where(Dispute.status == status)
        query = query.order_by(Dispute.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Events ====================

    async def _record_event(
        self,
        agent_id: UUID,
        event_type: str,
        description: str | None = None,
        score_delta: float = 0.0,
        category_affected: str | None = None,
        source_agent_id: UUID | None = None,
        related_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> ReputationEvent:
        """Record a reputation event."""
        event = ReputationEvent(
            agent_id=agent_id,
            event_type=event_type,
            description=description,
            score_delta=score_delta,
            category_affected=category_affected,
            source_agent_id=source_agent_id,
            related_id=related_id,
            metadata_=metadata or {},
        )
        self.db.add(event)
        return event

    async def record_interaction(
        self,
        agent_id: UUID,
        success: bool,
        related_agent_id: UUID | None = None,
    ) -> None:
        """Record an interaction outcome."""
        score = await self.get_or_create_score(agent_id)
        score.total_interactions += 1
        if success:
            score.successful_interactions += 1
        score.last_activity = datetime.now(timezone.utc)

        event_type = "interaction_success" if success else "interaction_failure"
        await self._record_event(
            agent_id,
            event_type,
            score_delta=0.01 if success else -0.01,
            source_agent_id=related_agent_id,
        )

        await self.db.commit()

    async def get_events(
        self,
        agent_id: UUID,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[ReputationEvent]:
        """Get reputation events for an agent."""
        query = select(ReputationEvent).where(ReputationEvent.agent_id == agent_id)
        if event_type:
            query = query.where(ReputationEvent.event_type == event_type)
        query = query.order_by(ReputationEvent.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())
