"""Billing service for usage tracking and subscription management."""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.billing.models import (
    Account,
    Subscription,
    SubscriptionStatus,
    Usage,
    UsageSummary,
    UsageType,
)
from nexus.billing.plans import PLANS, PlanType, get_plan_limits


class BillingService:
    """Service for billing operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Account Management ---

    async def create_account(
        self,
        email: str,
        name: str,
        plan_type: PlanType = PlanType.FREE,
    ) -> Account:
        """Create a new billing account."""
        account = Account(
            email=email,
            name=name,
            plan_type=plan_type,
        )
        self.db.add(account)
        await self.db.flush()
        return account

    async def get_account_by_email(self, email: str) -> Account | None:
        """Get account by email."""
        result = await self.db.execute(
            select(Account).where(Account.email == email)
        )
        return result.scalar_one_or_none()

    async def get_account_by_id(self, account_id: UUID) -> Account | None:
        """Get account by ID."""
        result = await self.db.execute(
            select(Account).where(Account.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_account_by_stripe_customer(self, stripe_customer_id: str) -> Account | None:
        """Get account by Stripe customer ID."""
        result = await self.db.execute(
            select(Account).where(Account.stripe_customer_id == stripe_customer_id)
        )
        return result.scalar_one_or_none()

    async def update_account_plan(
        self,
        account_id: UUID,
        plan_type: PlanType,
    ) -> Account | None:
        """Update account's plan."""
        account = await self.get_account_by_id(account_id)
        if account:
            account.plan_type = plan_type
            account.updated_at = datetime.now(timezone.utc)
        return account

    async def set_stripe_customer_id(
        self,
        account_id: UUID,
        stripe_customer_id: str,
    ) -> Account | None:
        """Set Stripe customer ID for account."""
        account = await self.get_account_by_id(account_id)
        if account:
            account.stripe_customer_id = stripe_customer_id
            account.updated_at = datetime.now(timezone.utc)
        return account

    # --- Usage Tracking ---

    async def track_usage(
        self,
        account_id: UUID,
        usage_type: UsageType,
        count: int = 1,
        agent_id: UUID | None = None,
    ) -> Usage:
        """
        Track usage for an account.

        Aggregates by day and usage type.
        """
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Get billing period start (1st of current month)
        billing_period_start = today.replace(day=1)

        # Check for existing record
        result = await self.db.execute(
            select(Usage).where(
                Usage.account_id == account_id,
                Usage.usage_type == usage_type,
                Usage.date == today,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.count += count
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        else:
            usage = Usage(
                account_id=account_id,
                agent_id=agent_id,
                usage_type=usage_type,
                count=count,
                date=today,
                billing_period_start=billing_period_start,
            )
            self.db.add(usage)
            await self.db.flush()
            return usage

    async def get_usage_for_period(
        self,
        account_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[UsageType, int]:
        """Get total usage for a billing period."""
        result = await self.db.execute(
            select(Usage.usage_type, func.sum(Usage.count))
            .where(
                Usage.account_id == account_id,
                Usage.date >= period_start,
                Usage.date < period_end,
            )
            .group_by(Usage.usage_type)
        )

        usage = {ut: 0 for ut in UsageType}
        for usage_type, count in result.all():
            usage[usage_type] = count or 0

        return usage

    async def get_current_month_usage(self, account_id: UUID) -> dict[str, Any]:
        """Get usage for current billing period with limits."""
        account = await self.get_account_by_id(account_id)
        if not account:
            return {}

        # Current billing period (1st of month to now)
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = now

        usage = await self.get_usage_for_period(account_id, period_start, period_end)
        limits = get_plan_limits(account.plan_type)

        # Calculate memory ops (store + get + search + delete)
        memory_ops = (
            usage[UsageType.MEMORY_STORE] +
            usage[UsageType.MEMORY_GET] +
            usage[UsageType.MEMORY_SEARCH] +
            usage[UsageType.MEMORY_DELETE]
        )

        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "plan": account.plan_type.value,
            "usage": {
                "memory_ops": {
                    "used": memory_ops,
                    "limit": limits.memory_ops_per_month,
                    "percentage": round(memory_ops / limits.memory_ops_per_month * 100, 1) if limits.memory_ops_per_month > 0 else 0,
                },
                "discovery_queries": {
                    "used": usage[UsageType.DISCOVERY_QUERY],
                    "limit": limits.discovery_queries_per_month,
                    "percentage": round(usage[UsageType.DISCOVERY_QUERY] / limits.discovery_queries_per_month * 100, 1) if limits.discovery_queries_per_month > 0 else 0,
                },
                "api_requests": {
                    "used": usage[UsageType.API_REQUEST],
                    "limit": limits.api_requests_per_month,
                    "percentage": round(usage[UsageType.API_REQUEST] / limits.api_requests_per_month * 100, 1) if limits.api_requests_per_month > 0 else 0,
                },
            },
        }

    # --- Limit Checking ---

    async def check_limit(
        self,
        account_id: UUID,
        usage_type: UsageType,
    ) -> tuple[bool, int, int]:
        """
        Check if account is within limits for a usage type.

        Returns: (is_allowed, current_usage, limit)
        """
        account = await self.get_account_by_id(account_id)
        if not account:
            return False, 0, 0

        limits = get_plan_limits(account.plan_type)

        # Get current period usage
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        usage = await self.get_usage_for_period(account_id, period_start, now)

        # Map usage type to limit
        if usage_type in [UsageType.MEMORY_STORE, UsageType.MEMORY_GET,
                          UsageType.MEMORY_SEARCH, UsageType.MEMORY_DELETE]:
            current = sum([
                usage[UsageType.MEMORY_STORE],
                usage[UsageType.MEMORY_GET],
                usage[UsageType.MEMORY_SEARCH],
                usage[UsageType.MEMORY_DELETE],
            ])
            limit = limits.memory_ops_per_month
        elif usage_type == UsageType.DISCOVERY_QUERY:
            current = usage[UsageType.DISCOVERY_QUERY]
            limit = limits.discovery_queries_per_month
        elif usage_type == UsageType.API_REQUEST:
            current = usage[UsageType.API_REQUEST]
            limit = limits.api_requests_per_month
        else:
            return True, 0, 0

        # Allow 120% for grace period (hard limit)
        hard_limit = int(limit * 1.2)

        return current < hard_limit, current, limit

    async def get_usage_percentage(
        self,
        account_id: UUID,
        usage_type: UsageType,
    ) -> float:
        """Get usage as percentage of limit."""
        is_allowed, current, limit = await self.check_limit(account_id, usage_type)
        if limit == 0:
            return 0.0
        return round(current / limit * 100, 1)

    # --- Subscription Management ---

    async def create_subscription(
        self,
        account_id: UUID,
        stripe_subscription_id: str,
        stripe_price_id: str,
        plan_type: PlanType,
        period_start: datetime,
        period_end: datetime,
        is_annual: bool = False,
    ) -> Subscription:
        """Create a subscription record."""
        subscription = Subscription(
            account_id=account_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=stripe_price_id,
            plan_type=plan_type,
            current_period_start=period_start,
            current_period_end=period_end,
            is_annual=is_annual,
            status=SubscriptionStatus.ACTIVE,
        )
        self.db.add(subscription)
        await self.db.flush()

        # Update account plan
        await self.update_account_plan(account_id, plan_type)

        return subscription

    async def get_active_subscription(self, account_id: UUID) -> Subscription | None:
        """Get active subscription for account."""
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.account_id == account_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    async def update_subscription_status(
        self,
        stripe_subscription_id: str,
        status: SubscriptionStatus,
    ) -> Subscription | None:
        """Update subscription status."""
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.status = status
            subscription.updated_at = datetime.now(timezone.utc)

            # If canceled, revert account to free plan
            if status == SubscriptionStatus.CANCELED:
                await self.update_account_plan(subscription.account_id, PlanType.FREE)

        return subscription

    async def cancel_subscription(
        self,
        stripe_subscription_id: str,
        cancel_at_period_end: bool = True,
    ) -> Subscription | None:
        """Cancel a subscription."""
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.cancel_at_period_end = cancel_at_period_end
            subscription.canceled_at = datetime.now(timezone.utc)
            subscription.updated_at = datetime.now(timezone.utc)

            if not cancel_at_period_end:
                subscription.status = SubscriptionStatus.CANCELED
                await self.update_account_plan(subscription.account_id, PlanType.FREE)

        return subscription

    # --- Usage Summaries ---

    async def create_usage_summary(
        self,
        account_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> UsageSummary:
        """Create a usage summary for a billing period."""
        account = await self.get_account_by_id(account_id)
        if not account:
            raise ValueError("Account not found")

        usage = await self.get_usage_for_period(account_id, period_start, period_end)
        limits = get_plan_limits(account.plan_type)
        plan = PLANS[account.plan_type]

        # Calculate totals
        memory_ops = sum([
            usage[UsageType.MEMORY_STORE],
            usage[UsageType.MEMORY_GET],
            usage[UsageType.MEMORY_SEARCH],
            usage[UsageType.MEMORY_DELETE],
        ])
        discovery_queries = usage[UsageType.DISCOVERY_QUERY]
        api_requests = usage[UsageType.API_REQUEST]

        # Calculate overages
        memory_ops_overage = max(0, memory_ops - limits.memory_ops_per_month)
        discovery_overage = max(0, discovery_queries - limits.discovery_queries_per_month)
        api_overage = max(0, api_requests - limits.api_requests_per_month)

        # Calculate overage cost (in cents)
        overage_cost = 0
        if account.plan_type != PlanType.FREE:
            pricing = plan.pricing
            overage_cost += (memory_ops_overage // 10000) * pricing.memory_ops_overage_cents
            overage_cost += (api_overage // 10000) * pricing.api_requests_overage_cents

        summary = UsageSummary(
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            memory_ops=memory_ops,
            discovery_queries=discovery_queries,
            api_requests=api_requests,
            plan_type=account.plan_type,
            memory_ops_overage=memory_ops_overage,
            discovery_overage=discovery_overage,
            api_requests_overage=api_overage,
            overage_amount_cents=overage_cost,
        )
        self.db.add(summary)
        await self.db.flush()

        return summary
