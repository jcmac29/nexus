"""Profile service - Manage agent profiles, settings, prompts, and subscriptions."""

from datetime import datetime, timezone
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.config import get_settings
from nexus.profiles.models import (
    AgentProfile,
    AgentSettings,
    CustomPrompt,
    AgentSubscription,
    PromptType,
)

settings = get_settings()

# Configure Stripe if available
if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key


class ProfileService:
    """Service for managing profiles, settings, and subscriptions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Profile Management ---

    async def get_or_create_profile(self, agent_id: UUID) -> AgentProfile:
        """Get or create a profile for an agent."""
        result = await self.session.execute(
            select(AgentProfile).where(AgentProfile.agent_id == agent_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            profile = AgentProfile(agent_id=agent_id)
            self.session.add(profile)
            await self.session.commit()
            await self.session.refresh(profile)

        return profile

    async def update_profile(
        self,
        agent_id: UUID,
        display_name: str | None = None,
        bio: str | None = None,
        avatar_url: str | None = None,
        banner_url: str | None = None,
        website: str | None = None,
        contact_email: str | None = None,
        timezone: str | None = None,
        locale: str | None = None,
        social_links: dict | None = None,
        is_public: bool | None = None,
    ) -> AgentProfile:
        """Update agent profile."""
        profile = await self.get_or_create_profile(agent_id)

        if display_name is not None:
            profile.display_name = display_name
        if bio is not None:
            profile.bio = bio
        if avatar_url is not None:
            profile.avatar_url = avatar_url
        if banner_url is not None:
            profile.banner_url = banner_url
        if website is not None:
            profile.website = website
        if contact_email is not None:
            profile.contact_email = contact_email
        if timezone is not None:
            profile.timezone = timezone
        if locale is not None:
            profile.locale = locale
        if social_links is not None:
            profile.social_links = social_links
        if is_public is not None:
            profile.is_public = is_public

        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    # --- Settings Management ---

    async def get_or_create_settings(self, agent_id: UUID) -> AgentSettings:
        """Get or create settings for an agent."""
        result = await self.session.execute(
            select(AgentSettings).where(AgentSettings.agent_id == agent_id)
        )
        settings_obj = result.scalar_one_or_none()

        if not settings_obj:
            settings_obj = AgentSettings(agent_id=agent_id)
            self.session.add(settings_obj)
            await self.session.commit()
            await self.session.refresh(settings_obj)

        return settings_obj

    async def update_settings(
        self,
        agent_id: UUID,
        **kwargs,
    ) -> AgentSettings:
        """Update agent settings."""
        settings_obj = await self.get_or_create_settings(agent_id)

        # SECURITY: Whitelist of allowed fields to prevent mass assignment
        allowed_fields = {
            "default_model", "temperature", "max_tokens", "system_prompt",
            "response_format", "memory_enabled", "memory_window_size",
            "auto_summarize", "context_injection", "custom_instructions",
            "language", "timezone", "date_format", "notifications_enabled",
            "webhook_enabled", "rate_limit_override",
        }

        for key, value in kwargs.items():
            if key in allowed_fields and hasattr(settings_obj, key) and value is not None:
                setattr(settings_obj, key, value)

        await self.session.commit()
        await self.session.refresh(settings_obj)
        return settings_obj

    # --- Custom Prompts ---

    async def create_prompt(
        self,
        agent_id: UUID,
        name: str,
        content: str,
        prompt_type: PromptType = PromptType.INSTRUCTION,
        description: str | None = None,
        variables: list[str] | None = None,
        is_default: bool = False,
        tags: list[str] | None = None,
        category: str | None = None,
        capability_name: str | None = None,
    ) -> CustomPrompt:
        """Create a custom prompt."""
        # If setting as default, unset other defaults of same type
        if is_default:
            await self._unset_default_prompts(agent_id, prompt_type)

        prompt = CustomPrompt(
            agent_id=agent_id,
            name=name,
            content=content,
            prompt_type=prompt_type,
            description=description,
            variables=variables or [],
            is_default=is_default,
            tags=tags or [],
            category=category,
            capability_name=capability_name,
        )

        self.session.add(prompt)
        await self.session.commit()
        await self.session.refresh(prompt)
        return prompt

    async def get_prompt(self, prompt_id: UUID) -> CustomPrompt | None:
        """Get a prompt by ID."""
        result = await self.session.execute(
            select(CustomPrompt).where(CustomPrompt.id == prompt_id)
        )
        return result.scalar_one_or_none()

    async def list_prompts(
        self,
        agent_id: UUID,
        prompt_type: PromptType | None = None,
        capability_name: str | None = None,
    ) -> list[CustomPrompt]:
        """List prompts for an agent."""
        query = select(CustomPrompt).where(
            CustomPrompt.agent_id == agent_id,
            CustomPrompt.is_active == True,
        )

        if prompt_type:
            query = query.where(CustomPrompt.prompt_type == prompt_type)
        if capability_name:
            query = query.where(CustomPrompt.capability_name == capability_name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_default_prompt(
        self,
        agent_id: UUID,
        prompt_type: PromptType,
    ) -> CustomPrompt | None:
        """Get the default prompt of a specific type."""
        result = await self.session.execute(
            select(CustomPrompt).where(
                CustomPrompt.agent_id == agent_id,
                CustomPrompt.prompt_type == prompt_type,
                CustomPrompt.is_default == True,
                CustomPrompt.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def update_prompt(
        self,
        prompt_id: UUID,
        agent_id: UUID,
        **kwargs,
    ) -> CustomPrompt | None:
        """Update a custom prompt."""
        prompt = await self.get_prompt(prompt_id)
        if not prompt or prompt.agent_id != agent_id:
            return None

        # Handle is_default specially
        if kwargs.get("is_default"):
            await self._unset_default_prompts(agent_id, prompt.prompt_type)

        for key, value in kwargs.items():
            if hasattr(prompt, key) and value is not None:
                setattr(prompt, key, value)

        await self.session.commit()
        await self.session.refresh(prompt)
        return prompt

    async def delete_prompt(self, prompt_id: UUID, agent_id: UUID) -> bool:
        """Delete (deactivate) a prompt."""
        prompt = await self.get_prompt(prompt_id)
        if not prompt or prompt.agent_id != agent_id:
            return False

        prompt.is_active = False
        await self.session.commit()
        return True

    async def render_prompt(
        self,
        prompt_id: UUID,
        agent_id: UUID,
        variables: dict[str, str],
    ) -> str | None:
        """Render a prompt with variable substitution.

        SECURITY: Verifies ownership before allowing access.
        """
        prompt = await self.get_prompt(prompt_id)
        if not prompt:
            return None

        # SECURITY: Verify ownership - agents can only render their own prompts
        if prompt.agent_id != agent_id:
            return None

        content = prompt.content

        # SECURITY: Only substitute whitelisted variable names
        allowed_vars = set(prompt.variables or [])
        for var_name, var_value in variables.items():
            if var_name in allowed_vars:
                content = content.replace(f"{{{{{var_name}}}}}", str(var_value))

        # Update use count
        prompt.use_count += 1
        await self.session.commit()

        return content

    async def _unset_default_prompts(
        self,
        agent_id: UUID,
        prompt_type: PromptType,
    ) -> None:
        """Unset default flag for all prompts of a type."""
        result = await self.session.execute(
            select(CustomPrompt).where(
                CustomPrompt.agent_id == agent_id,
                CustomPrompt.prompt_type == prompt_type,
                CustomPrompt.is_default == True,
            )
        )
        for prompt in result.scalars():
            prompt.is_default = False

    # --- Subscription Management ---

    async def get_or_create_subscription(self, agent_id: UUID) -> AgentSubscription:
        """Get or create subscription record."""
        result = await self.session.execute(
            select(AgentSubscription).where(AgentSubscription.agent_id == agent_id)
        )
        sub = result.scalar_one_or_none()

        if not sub:
            sub = AgentSubscription(agent_id=agent_id)
            self.session.add(sub)
            await self.session.commit()
            await self.session.refresh(sub)

        return sub

    async def create_stripe_customer(
        self,
        agent_id: UUID,
        email: str,
        name: str | None = None,
    ) -> AgentSubscription:
        """Create a Stripe customer for an agent."""
        if not settings.stripe_secret_key:
            raise ValueError("Stripe not configured")

        sub = await self.get_or_create_subscription(agent_id)

        if not sub.stripe_customer_id:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"agent_id": str(agent_id)},
            )
            sub.stripe_customer_id = customer.id
            await self.session.commit()
            await self.session.refresh(sub)

        return sub

    async def create_subscription(
        self,
        agent_id: UUID,
        price_id: str,
    ) -> dict:
        """Create a Stripe subscription."""
        if not settings.stripe_secret_key:
            raise ValueError("Stripe not configured")

        sub = await self.get_or_create_subscription(agent_id)

        if not sub.stripe_customer_id:
            raise ValueError("No Stripe customer. Call create_stripe_customer first.")

        stripe_sub = stripe.Subscription.create(
            customer=sub.stripe_customer_id,
            items=[{"price": price_id}],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
        )

        sub.stripe_subscription_id = stripe_sub.id
        sub.plan_status = stripe_sub.status
        sub.current_period_start = datetime.fromtimestamp(
            stripe_sub.current_period_start, tz=timezone.utc
        )
        sub.current_period_end = datetime.fromtimestamp(
            stripe_sub.current_period_end, tz=timezone.utc
        )

        await self.session.commit()

        return {
            "subscription_id": stripe_sub.id,
            "client_secret": stripe_sub.latest_invoice.payment_intent.client_secret,
            "status": stripe_sub.status,
        }

    async def cancel_subscription(
        self,
        agent_id: UUID,
        reason: str | None = None,
        cancel_immediately: bool = False,
    ) -> AgentSubscription:
        """Cancel a subscription."""
        sub = await self.get_or_create_subscription(agent_id)

        if not sub.stripe_subscription_id:
            raise ValueError("No active subscription")

        if settings.stripe_secret_key:
            if cancel_immediately:
                stripe.Subscription.delete(sub.stripe_subscription_id)
                sub.plan_status = "canceled"
            else:
                stripe.Subscription.modify(
                    sub.stripe_subscription_id,
                    cancel_at_period_end=True,
                )
                sub.cancel_at_period_end = True

        sub.canceled_at = datetime.now(timezone.utc)
        sub.cancellation_reason = reason

        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def reactivate_subscription(self, agent_id: UUID) -> AgentSubscription:
        """Reactivate a subscription that was set to cancel."""
        sub = await self.get_or_create_subscription(agent_id)

        if not sub.stripe_subscription_id or not sub.cancel_at_period_end:
            raise ValueError("No subscription to reactivate")

        if settings.stripe_secret_key:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=False,
            )

        sub.cancel_at_period_end = False
        sub.canceled_at = None
        sub.cancellation_reason = None

        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def get_subscription_status(self, agent_id: UUID) -> dict:
        """Get current subscription status."""
        sub = await self.get_or_create_subscription(agent_id)

        return {
            "plan": sub.plan_name,
            "status": sub.plan_status,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "usage": {
                "invocations": f"{sub.current_invocations}/{sub.max_invocations_per_month}",
                "memory_mb": f"{sub.current_memory_mb}/{sub.max_memory_mb}",
            },
            "limits": {
                "max_agents": sub.max_agents,
                "max_team_members": sub.max_team_members,
            },
        }

    async def update_plan_limits(
        self,
        agent_id: UUID,
        plan_name: str,
    ) -> AgentSubscription:
        """Update limits based on plan."""
        sub = await self.get_or_create_subscription(agent_id)
        sub.plan_name = plan_name

        # Set limits based on plan
        if plan_name == "free":
            sub.max_agents = 3
            sub.max_invocations_per_month = 1000
            sub.max_memory_mb = 100
            sub.max_team_members = 1
        elif plan_name == "pro":
            sub.max_agents = 20
            sub.max_invocations_per_month = 50000
            sub.max_memory_mb = 5000
            sub.max_team_members = 10
        elif plan_name == "enterprise":
            sub.max_agents = 1000
            sub.max_invocations_per_month = 1000000
            sub.max_memory_mb = 100000
            sub.max_team_members = 1000

        await self.session.commit()
        await self.session.refresh(sub)
        return sub
