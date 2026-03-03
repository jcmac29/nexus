"""Resource limits enforcement for multi-tenant system."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.billing.models import Account
from nexus.billing.plans import PLANS, PlanType, get_plan_limits
from nexus.identity.models import Agent
from nexus.memory.models import Memory


class LimitExceededError(Exception):
    """Raised when a resource limit is exceeded."""

    def __init__(self, resource: str, current: int, limit: int):
        self.resource = resource
        self.current = current
        self.limit = limit
        super().__init__(f"{resource} limit exceeded: {current}/{limit}")


class LimitsService:
    """Service for checking and enforcing resource limits per tenant."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_account_limits(self, account_id: UUID) -> dict:
        """Get the resource limits for an account based on their plan."""
        stmt = select(Account).where(Account.id == account_id)
        result = await self.db.execute(stmt)
        account = result.scalar_one_or_none()

        if not account:
            limits = get_plan_limits(PlanType.FREE)
            return {
                "agents": limits.agents,
                "stored_memories": limits.stored_memories,
                "team_members": limits.team_members,
            }

        plan_type = account.plan_type if hasattr(account, 'plan_type') else PlanType.FREE
        limits = get_plan_limits(plan_type)
        plan_limits = {
            "agents": limits.agents,
            "stored_memories": limits.stored_memories,
            "team_members": limits.team_members,
        }

        # Check for custom overrides in tenant settings
        from nexus.tenants.models import TenantSettings

        settings_stmt = select(TenantSettings).where(TenantSettings.account_id == account_id)
        settings_result = await self.db.execute(settings_stmt)
        settings = settings_result.scalar_one_or_none()

        if settings and settings.custom_rate_limits:
            # Merge custom limits with plan limits
            return {**plan_limits, **settings.custom_rate_limits}

        return plan_limits

    async def get_usage_summary(self, account_id: UUID) -> dict:
        """Get current resource usage for an account."""
        # Count agents
        agent_count = await self.db.execute(
            select(func.count()).select_from(Agent).where(Agent.account_id == account_id)
        )

        # Count memories across all agents in the account
        memory_count = await self.db.execute(
            select(func.count()).select_from(Memory).where(Memory.account_id == account_id)
        )

        # Get team member count
        from nexus.teams.models import Team, TeamMember

        team_member_count = await self.db.execute(
            select(func.count(func.distinct(TeamMember.agent_id)))
            .select_from(TeamMember)
            .join(Team)
            .where(Team.account_id == account_id)
        )

        return {
            "agents": agent_count.scalar() or 0,
            "memories": memory_count.scalar() or 0,
            "team_members": team_member_count.scalar() or 0,
        }

    async def check_agent_limit(self, account_id: UUID) -> bool:
        """Check if account can create more agents."""
        limits = await self.get_account_limits(account_id)
        usage = await self.get_usage_summary(account_id)

        agent_limit = limits.get("agents")
        if agent_limit is None:  # No limit
            return True

        return usage["agents"] < agent_limit

    async def check_memory_limit(self, account_id: UUID) -> bool:
        """Check if account can store more memories."""
        limits = await self.get_account_limits(account_id)
        usage = await self.get_usage_summary(account_id)

        memory_limit = limits.get("stored_memories")
        if memory_limit is None:  # No limit
            return True

        return usage["memories"] < memory_limit

    async def check_team_member_limit(self, account_id: UUID) -> bool:
        """Check if account can add more team members."""
        limits = await self.get_account_limits(account_id)
        usage = await self.get_usage_summary(account_id)

        member_limit = limits.get("team_members")
        if member_limit is None:  # No limit
            return True

        return usage["team_members"] < member_limit

    async def enforce_agent_limit(self, account_id: UUID):
        """Enforce agent limit, raising error if exceeded."""
        if not await self.check_agent_limit(account_id):
            limits = await self.get_account_limits(account_id)
            usage = await self.get_usage_summary(account_id)
            raise LimitExceededError(
                resource="agents",
                current=usage["agents"],
                limit=limits.get("agents", 0),
            )

    async def enforce_memory_limit(self, account_id: UUID):
        """Enforce memory limit, raising error if exceeded."""
        if not await self.check_memory_limit(account_id):
            limits = await self.get_account_limits(account_id)
            usage = await self.get_usage_summary(account_id)
            raise LimitExceededError(
                resource="stored_memories",
                current=usage["memories"],
                limit=limits.get("stored_memories", 0),
            )

    async def enforce_team_member_limit(self, account_id: UUID):
        """Enforce team member limit, raising error if exceeded."""
        if not await self.check_team_member_limit(account_id):
            limits = await self.get_account_limits(account_id)
            usage = await self.get_usage_summary(account_id)
            raise LimitExceededError(
                resource="team_members",
                current=usage["team_members"],
                limit=limits.get("team_members", 0),
            )

    async def get_limit_status(self, account_id: UUID) -> dict:
        """Get comprehensive limit status for an account."""
        limits = await self.get_account_limits(account_id)
        usage = await self.get_usage_summary(account_id)

        def calc_percent(current: int, limit: int | None) -> float | None:
            if limit is None or limit == 0:
                return None
            return round(current / limit * 100, 2)

        return {
            "agents": {
                "used": usage["agents"],
                "limit": limits.get("agents"),
                "percent": calc_percent(usage["agents"], limits.get("agents")),
            },
            "memories": {
                "used": usage["memories"],
                "limit": limits.get("stored_memories"),
                "percent": calc_percent(usage["memories"], limits.get("stored_memories")),
            },
            "team_members": {
                "used": usage["team_members"],
                "limit": limits.get("team_members"),
                "percent": calc_percent(usage["team_members"], limits.get("team_members")),
            },
        }
