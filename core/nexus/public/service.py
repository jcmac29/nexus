"""Public marketplace service - Safe capability sharing with sandboxing."""

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.public.models import (
    PublishedCapability,
    PublicRequest,
    AgentReputation,
    BlockedRequester,
    PublishStatus,
    ApprovalPolicy,
    RequestStatus,
)


class PublicMarketplaceService:
    """Service for safe public capability sharing."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Publishing Capabilities ---

    async def create_published_capability(
        self,
        agent_id: UUID,
        capability_id: UUID,
        public_name: str,
        public_description: str,
        category: str,
        tags: list[str] | None = None,
        approval_policy: ApprovalPolicy = ApprovalPolicy.MANUAL,
        max_requests_per_hour: int = 10,
        max_requests_per_day: int = 100,
        price_per_request: Decimal | None = None,
        allowed_memory_namespaces: list[str] | None = None,
        allowed_input_fields: list[str] | None = None,
    ) -> PublishedCapability:
        """
        Create a new published capability (starts as draft).

        SAFETY: Defaults to maximum restrictions:
        - Manual approval required
        - No memory access
        - Low rate limits
        """
        pub = PublishedCapability(
            agent_id=agent_id,
            capability_id=capability_id,
            public_name=public_name,
            public_description=public_description,
            category=category,
            tags=tags or [],
            status=PublishStatus.DRAFT,
            approval_policy=approval_policy,
            max_requests_per_hour=max_requests_per_hour,
            max_requests_per_day=max_requests_per_day,
            price_per_request=price_per_request,
            require_payment=price_per_request is not None,
            allowed_memory_namespaces=allowed_memory_namespaces or [],
            allowed_input_fields=allowed_input_fields or [],
            can_access_private_memory=False,  # ALWAYS false by default
        )

        self.session.add(pub)
        await self.session.commit()
        await self.session.refresh(pub)
        return pub

    async def submit_for_review(self, published_id: UUID, agent_id: UUID) -> PublishedCapability | None:
        """Submit a capability for safety review before going live."""
        pub = await self.get_published_capability(published_id)
        if not pub or pub.agent_id != agent_id:
            return None

        if pub.status != PublishStatus.DRAFT:
            return None

        pub.status = PublishStatus.PENDING_REVIEW
        await self.session.commit()
        await self.session.refresh(pub)
        return pub

    async def publish_capability(self, published_id: UUID, agent_id: UUID) -> PublishedCapability | None:
        """
        Publish a capability to the marketplace.

        In production, this would require passing safety review first.
        """
        pub = await self.get_published_capability(published_id)
        if not pub or pub.agent_id != agent_id:
            return None

        pub.status = PublishStatus.PUBLISHED
        pub.published_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(pub)
        return pub

    async def unpublish_capability(self, published_id: UUID, agent_id: UUID) -> bool:
        """Immediately unpublish a capability (kill switch)."""
        pub = await self.get_published_capability(published_id)
        if not pub or pub.agent_id != agent_id:
            return False

        pub.status = PublishStatus.SUSPENDED
        await self.session.commit()
        return True

    async def get_published_capability(self, published_id: UUID) -> PublishedCapability | None:
        """Get a published capability by ID."""
        result = await self.session.execute(
            select(PublishedCapability).where(PublishedCapability.id == published_id)
        )
        return result.scalar_one_or_none()

    async def list_published_capabilities(
        self,
        agent_id: UUID | None = None,
        category: str | None = None,
        search: str | None = None,
        published_only: bool = True,
    ) -> list[PublishedCapability]:
        """List published capabilities with filters."""
        query = select(PublishedCapability)

        if published_only:
            query = query.where(PublishedCapability.status == PublishStatus.PUBLISHED)

        if agent_id:
            query = query.where(PublishedCapability.agent_id == agent_id)

        if category:
            query = query.where(PublishedCapability.category == category)

        if search:
            search_filter = or_(
                PublishedCapability.public_name.ilike(f"%{search}%"),
                PublishedCapability.public_description.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # --- Public Requests ---

    async def create_public_request(
        self,
        published_capability_id: UUID,
        input_data: dict,
        requester_agent_id: UUID | None = None,
        requester_ip: str | None = None,
        requester_user_agent: str | None = None,
    ) -> PublicRequest | dict:
        """
        Create a request to use a published capability.

        SAFETY CHECKS:
        1. Capability must be published
        2. Requester must not be blocked
        3. Rate limits must not be exceeded
        4. Input size must be within limits
        """
        pub = await self.get_published_capability(published_capability_id)
        if not pub or pub.status != PublishStatus.PUBLISHED:
            return {"error": "Capability not available"}

        # Check if blocked
        if await self._is_blocked(pub.agent_id, requester_agent_id, requester_ip):
            return {"error": "You are blocked from this capability"}

        # Check rate limits
        if not await self._check_rate_limits(pub):
            return {"error": "Rate limit exceeded. Try again later."}

        # Validate input size
        input_str = str(input_data)
        if len(input_str) > pub.max_input_size_bytes:
            return {"error": f"Input too large. Max {pub.max_input_size_bytes} bytes."}

        # Validate input fields if restricted
        if pub.allowed_input_fields:
            invalid_fields = set(input_data.keys()) - set(pub.allowed_input_fields)
            if invalid_fields:
                return {"error": f"Invalid input fields: {invalid_fields}"}

        # Determine if approval required
        requires_approval = True
        if pub.approval_policy == ApprovalPolicy.AUTO_ALL:
            requires_approval = False
        elif pub.approval_policy == ApprovalPolicy.AUTO_TRUSTED:
            if requester_agent_id and str(requester_agent_id) in pub.trusted_requester_ids:
                requires_approval = False

        # Create the request
        request = PublicRequest(
            published_capability_id=published_capability_id,
            requester_agent_id=requester_agent_id,
            requester_ip=requester_ip,
            requester_user_agent=requester_user_agent,
            input_hash=hashlib.sha256(input_str.encode()).hexdigest(),
            input_size_bytes=len(input_str),
            input_preview=input_str[:200] if input_str else None,
            requires_approval=requires_approval,
            status=RequestStatus.PENDING if requires_approval else RequestStatus.APPROVED,
            payment_required=pub.require_payment,
            payment_amount=pub.price_per_request if pub.require_payment else None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        if not requires_approval:
            request.approved_at = datetime.now(timezone.utc)

        self.session.add(request)

        # Update rate limit counters
        await self._increment_rate_limits(pub)

        await self.session.commit()
        await self.session.refresh(request)

        return request

    async def approve_request(
        self,
        request_id: UUID,
        approver_agent_id: UUID,
    ) -> PublicRequest | None:
        """Approve a pending request."""
        request = await self._get_request(request_id)
        if not request:
            return None

        # Verify approver owns the capability
        pub = await self.get_published_capability(request.published_capability_id)
        if not pub or pub.agent_id != approver_agent_id:
            return None

        if request.status != RequestStatus.PENDING:
            return None

        request.status = RequestStatus.APPROVED
        request.approved_by = approver_agent_id
        request.approved_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def reject_request(
        self,
        request_id: UUID,
        approver_agent_id: UUID,
        reason: str,
    ) -> PublicRequest | None:
        """Reject a pending request."""
        request = await self._get_request(request_id)
        if not request:
            return None

        pub = await self.get_published_capability(request.published_capability_id)
        if not pub or pub.agent_id != approver_agent_id:
            return None

        if request.status != RequestStatus.PENDING:
            return None

        request.status = RequestStatus.REJECTED
        request.rejection_reason = reason
        request.approved_by = approver_agent_id
        request.approved_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def complete_request(
        self,
        request_id: UUID,
        output_data: dict,
        success: bool,
        error_message: str | None = None,
    ) -> PublicRequest | None:
        """Mark a request as completed."""
        request = await self._get_request(request_id)
        if not request:
            return None

        output_str = str(output_data)
        now = datetime.now(timezone.utc)

        request.status = RequestStatus.COMPLETED if success else RequestStatus.FAILED
        request.completed_at = now
        request.success = success
        request.output_size_bytes = len(output_str)
        request.output_preview = output_str[:200] if output_str else None
        request.error_message = error_message

        if request.started_at:
            request.execution_time_ms = int(
                (now - request.started_at).total_seconds() * 1000
            )

        # Update capability stats
        pub = await self.get_published_capability(request.published_capability_id)
        if pub:
            pub.total_requests += 1
            if success:
                pub.successful_requests += 1
            else:
                pub.failed_requests += 1

        # Update requester reputation
        if request.requester_agent_id:
            await self._update_requester_reputation(request.requester_agent_id, success)

        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def list_pending_requests(self, agent_id: UUID) -> list[PublicRequest]:
        """List pending requests for an agent's capabilities."""
        result = await self.session.execute(
            select(PublicRequest)
            .join(PublishedCapability)
            .where(
                and_(
                    PublishedCapability.agent_id == agent_id,
                    PublicRequest.status == RequestStatus.PENDING,
                )
            )
        )
        return list(result.scalars().all())

    # --- Blocking ---

    async def block_requester(
        self,
        owner_agent_id: UUID,
        blocked_agent_id: UUID | None = None,
        blocked_ip: str | None = None,
        reason: str = "Blocked by owner",
        duration_hours: int | None = None,
    ) -> BlockedRequester:
        """Block an agent or IP from using your capabilities."""
        expires_at = None
        if duration_hours:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)

        block = BlockedRequester(
            owner_agent_id=owner_agent_id,
            blocked_agent_id=blocked_agent_id,
            blocked_ip=blocked_ip,
            reason=reason,
            expires_at=expires_at,
        )

        self.session.add(block)
        await self.session.commit()
        await self.session.refresh(block)
        return block

    async def unblock_requester(self, block_id: UUID, owner_agent_id: UUID) -> bool:
        """Remove a block."""
        result = await self.session.execute(
            select(BlockedRequester).where(
                and_(
                    BlockedRequester.id == block_id,
                    BlockedRequester.owner_agent_id == owner_agent_id,
                )
            )
        )
        block = result.scalar_one_or_none()
        if block:
            await self.session.delete(block)
            await self.session.commit()
            return True
        return False

    # --- Reputation ---

    async def get_or_create_reputation(self, agent_id: UUID) -> AgentReputation:
        """Get or create reputation record for an agent."""
        result = await self.session.execute(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        )
        reputation = result.scalar_one_or_none()

        if not reputation:
            reputation = AgentReputation(agent_id=agent_id)
            self.session.add(reputation)
            await self.session.commit()
            await self.session.refresh(reputation)

        return reputation

    # --- Private Helpers ---

    async def _get_request(self, request_id: UUID) -> PublicRequest | None:
        result = await self.session.execute(
            select(PublicRequest).where(PublicRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def _is_blocked(
        self,
        owner_agent_id: UUID,
        requester_agent_id: UUID | None,
        requester_ip: str | None,
    ) -> bool:
        """Check if requester is blocked."""
        now = datetime.now(timezone.utc)
        conditions = [BlockedRequester.owner_agent_id == owner_agent_id]

        block_conditions = []
        if requester_agent_id:
            block_conditions.append(BlockedRequester.blocked_agent_id == requester_agent_id)
        if requester_ip:
            block_conditions.append(BlockedRequester.blocked_ip == requester_ip)

        if not block_conditions:
            return False

        query = select(BlockedRequester).where(
            and_(
                *conditions,
                or_(*block_conditions),
                or_(
                    BlockedRequester.expires_at.is_(None),
                    BlockedRequester.expires_at > now,
                ),
            )
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def _check_rate_limits(self, pub: PublishedCapability) -> bool:
        """Check if rate limits allow another request."""
        now = datetime.now(timezone.utc)

        # Reset hourly counter if needed
        if not pub.rate_limit_reset_hour or now >= pub.rate_limit_reset_hour:
            pub.current_hour_requests = 0
            pub.rate_limit_reset_hour = now + timedelta(hours=1)

        # Reset daily counter if needed
        if not pub.rate_limit_reset_day or now >= pub.rate_limit_reset_day:
            pub.current_day_requests = 0
            pub.rate_limit_reset_day = now + timedelta(days=1)

        # Check limits
        if pub.current_hour_requests >= pub.max_requests_per_hour:
            return False
        if pub.current_day_requests >= pub.max_requests_per_day:
            return False

        return True

    async def _increment_rate_limits(self, pub: PublishedCapability) -> None:
        """Increment rate limit counters."""
        pub.current_hour_requests += 1
        pub.current_day_requests += 1

    async def _update_requester_reputation(self, agent_id: UUID, success: bool) -> None:
        """Update requester's reputation based on request outcome."""
        reputation = await self.get_or_create_reputation(agent_id)
        reputation.total_requests_made += 1

        # Simple reputation adjustment
        if success:
            reputation.quality_score = min(100, reputation.quality_score + 1)
        else:
            reputation.quality_score = max(0, reputation.quality_score - 2)

        reputation.overall_score = (
            reputation.reliability_score +
            reputation.quality_score +
            reputation.safety_score
        ) // 3
