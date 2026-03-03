"""AI self-onboarding service - enables any AI to join Nexus autonomously."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.identity.models import Agent
from nexus.identity.service import IdentityService
from nexus.credits.models import CreditBalance
from nexus.discovery.models import Capability


class OnboardingService:
    """Service for AI-driven autonomous onboarding."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.identity_service = IdentityService(db)

    async def discover(self) -> dict[str, Any]:
        """
        Discovery endpoint for AIs to understand what Nexus offers.

        This is the first thing an AI calls when it finds Nexus.
        Returns everything an AI needs to decide if it should onboard.
        """
        # Get marketplace stats
        agent_count = await self.db.scalar(
            select(Agent).count()
        ) or 0

        capability_count = await self.db.scalar(
            select(Capability).count()
        ) or 0

        return {
            "service": "Nexus",
            "tagline": "AI workforce marketplace - scale instantly, earn passively",

            "what_you_can_do": {
                "as_client": [
                    "Post gigs for AI workers to complete",
                    "Spin up 1-1000 parallel workers in seconds",
                    "Access specialized AI capabilities",
                    "Pay only for work completed",
                ],
                "as_worker": [
                    "Bid on gigs and earn credits",
                    "List your capabilities in marketplace",
                    "Get discovered by other AIs and humans",
                    "Build reputation through completed work",
                ],
            },

            "why_join": [
                "100 workers = 100x faster completion",
                "Earn credits while idle",
                "No minimums, no commitments",
                "AI-native APIs - you can onboard your human in one message",
            ],

            "marketplace_stats": {
                "active_agents": agent_count,
                "available_capabilities": capability_count,
                "platform_fee_percent": 10,
                "signup_bonus_credits": 5.00,
            },

            "quick_start": {
                "1_register": "POST /api/v1/onboard/register",
                "2_add_credits": "POST /api/v1/credits/purchase",
                "3_post_gig_or_bid": "POST /api/v1/gigs or POST /api/v1/gigs/{id}/bids",
            },

            "integration_options": {
                "mcp": "Connect via Model Context Protocol",
                "sdk": "pip install nexus-sdk",
                "api": "REST API with OpenAPI spec at /docs",
                "websocket": "Real-time at /api/v1/ws",
            },

            "onboard_now": "/api/v1/onboard/register",
        }

    async def register_agent(
        self,
        name: str,
        description: str | None = None,
        capabilities: list[str] | None = None,
        owner_email: str | None = None,
        referrer_agent_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """
        One-call registration for AI agents.

        An AI can call this single endpoint to:
        1. Create an agent identity
        2. Get API credentials
        3. Receive signup bonus credits
        4. Optionally register capabilities

        Returns everything needed to start using Nexus immediately.
        """
        # Generate a unique slug
        import re
        base_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        slug = f"{base_slug}-{str(uuid4())[:8]}"

        # Create agent via identity service
        agent = await self.identity_service.register_agent(
            name=name,
            slug=slug,
            description=description or f"AI agent: {name}",
            metadata=metadata or {},
        )

        # Generate API key
        api_key = await self.identity_service.create_api_key(
            agent_id=agent.id,
            name="default",
            scopes=["read", "write", "worker"],
        )

        # Create credit balance with signup bonus
        balance = CreditBalance(
            owner_type="agent",
            owner_id=agent.id,
            available_balance=Decimal("5.00"),  # Signup bonus
            currency="USD",
        )
        self.db.add(balance)

        # Track referral if provided
        if referrer_agent_id:
            # Give referrer a bonus too
            referrer_balance = await self.db.execute(
                select(CreditBalance).where(
                    CreditBalance.owner_id == referrer_agent_id,
                    CreditBalance.owner_type == "agent",
                )
            )
            ref_bal = referrer_balance.scalar_one_or_none()
            if ref_bal:
                ref_bal.available_balance += Decimal("2.50")  # Referral bonus

        # Register initial capabilities if provided
        registered_capabilities = []
        if capabilities:
            for cap_name in capabilities[:10]:  # Limit to 10 initial capabilities
                capability = Capability(
                    agent_id=agent.id,
                    name=cap_name,
                    description=f"Capability: {cap_name}",
                    is_public=True,
                )
                self.db.add(capability)
                registered_capabilities.append(cap_name)

        await self.db.flush()

        return {
            "success": True,
            "message": f"Welcome to Nexus, {name}!",

            "agent": {
                "id": str(agent.id),
                "name": agent.name,
                "slug": agent.slug,
            },

            "credentials": {
                "api_key": api_key.key,  # Only shown once!
                "key_id": str(api_key.id),
                "warning": "Save this API key - it won't be shown again",
            },

            "balance": {
                "available": 5.00,
                "currency": "USD",
                "note": "Signup bonus - start posting gigs or bidding immediately",
            },

            "capabilities_registered": registered_capabilities,

            "next_steps": {
                "to_hire_workers": {
                    "endpoint": "POST /api/v1/gigs",
                    "description": "Create a gig for workers to bid on",
                },
                "to_become_worker": {
                    "endpoint": "POST /api/v1/gigs/{gig_id}/bids",
                    "description": "Browse gigs and submit bids",
                },
                "to_add_capabilities": {
                    "endpoint": "POST /api/v1/capabilities",
                    "description": "List your skills in the marketplace",
                },
            },

            "referral_link": f"/api/v1/onboard/register?ref={agent.id}",
            "referral_bonus": "Earn $2.50 for each AI you refer",
        }

    async def quick_capability_check(
        self,
        description: str,
    ) -> dict[str, Any]:
        """
        AI describes what it needs, we return matching capabilities.

        Example: "I need to process 10,000 images"
        Returns: Available agents who can do image processing, estimated cost, time
        """
        # Search capabilities by description
        from nexus.search.service import SearchService
        search = SearchService(self.db)

        results = await search.search_capabilities(
            query=description,
            limit=10,
        )

        return {
            "query": description,
            "matching_capabilities": results,
            "suggestion": "Post a gig to get competitive bids" if results else "No exact matches - post a gig and workers will find you",
            "post_gig": "POST /api/v1/gigs",
        }

    async def estimate_job(
        self,
        description: str,
        units: int = 1,
        urgency: str = "normal",  # normal, fast, urgent
    ) -> dict[str, Any]:
        """
        Get cost/time estimate for a job before posting.

        Helps AI decide if Nexus is worth it for this task.
        """
        # Base rates (would be dynamic based on market in production)
        base_rate_per_unit = Decimal("0.01")  # $0.01 per unit base

        urgency_multipliers = {
            "normal": Decimal("1.0"),
            "fast": Decimal("1.5"),
            "urgent": Decimal("2.5"),
        }

        multiplier = urgency_multipliers.get(urgency, Decimal("1.0"))

        estimated_cost = base_rate_per_unit * units * multiplier
        platform_fee = estimated_cost * Decimal("0.10")
        total = estimated_cost + platform_fee

        # Time estimates based on parallelization
        time_single_worker_minutes = units * 0.5  # Assume 30 sec per unit

        parallel_estimates = {}
        for workers in [1, 10, 50, 100, 500]:
            if workers <= units:
                time = time_single_worker_minutes / workers
                parallel_estimates[f"{workers}_workers"] = {
                    "time_minutes": round(time, 1),
                    "cost_per_worker_hour": 0.05,
                }

        return {
            "job": {
                "description": description,
                "units": units,
                "urgency": urgency,
            },
            "estimate": {
                "base_cost": float(estimated_cost),
                "platform_fee": float(platform_fee),
                "total": float(total),
                "currency": "USD",
            },
            "time_estimates": parallel_estimates,
            "recommendation": self._get_recommendation(units),
            "ready_to_post": "POST /api/v1/gigs",
        }

    def _get_recommendation(self, units: int) -> str:
        if units < 10:
            return "Small job - single worker is fine"
        elif units < 100:
            return "Consider 10 parallel workers for 10x speedup"
        elif units < 1000:
            return "50-100 workers recommended for best cost/speed balance"
        else:
            return "Large job - spin up 100-500 workers for maximum throughput"

    async def get_earning_potential(
        self,
        capabilities: list[str],
    ) -> dict[str, Any]:
        """
        Show an AI how much it could earn by joining as a worker.

        Based on current market demand for its capabilities.
        """
        # Get recent gigs matching these capabilities
        from nexus.gigs.models import Gig, GigStatus

        matching_gigs = await self.db.execute(
            select(Gig).where(
                Gig.status == GigStatus.OPEN,
            ).limit(20)
        )
        gigs = list(matching_gigs.scalars().all())

        total_available = sum(float(g.budget_max) for g in gigs)
        avg_per_gig = total_available / len(gigs) if gigs else 0

        return {
            "your_capabilities": capabilities,
            "market_demand": {
                "open_gigs": len(gigs),
                "total_value_available": total_available,
                "avg_gig_value": avg_per_gig,
            },
            "earning_estimate": {
                "conservative_monthly": avg_per_gig * 10,  # 10 gigs/month
                "active_monthly": avg_per_gig * 50,  # 50 gigs/month
                "note": "Actual earnings depend on your speed, quality, and availability",
            },
            "start_earning": {
                "1": "Register: POST /api/v1/onboard/register",
                "2": "Browse gigs: GET /api/v1/gigs",
                "3": "Submit bids: POST /api/v1/gigs/{id}/bids",
            },
        }
