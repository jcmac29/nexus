"""Profile and subscription API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.profiles.models import PromptType
from nexus.profiles.service import ProfileService

router = APIRouter(prefix="/profile", tags=["profile"])


# --- Schemas ---


class ProfileUpdate(BaseModel):
    """Profile update request."""
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None
    website: str | None = None
    contact_email: str | None = None
    timezone: str | None = None
    locale: str | None = None
    social_links: dict | None = None
    is_public: bool | None = None


class ProfileResponse(BaseModel):
    """Profile response."""
    id: UUID
    display_name: str | None
    bio: str | None
    avatar_url: str | None
    website: str | None
    timezone: str | None
    is_public: bool

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    """Settings update request."""
    email_notifications: bool | None = None
    webhook_notifications: bool | None = None
    notify_on_invocation: bool | None = None
    notify_on_message: bool | None = None
    notify_on_team_activity: bool | None = None
    show_online_status: bool | None = None
    allow_discovery: bool | None = None
    allow_invocations: bool | None = None
    allow_messages: bool | None = None
    default_memory_scope: str | None = None
    default_invocation_timeout: int | None = None
    max_concurrent_invocations: int | None = None
    default_temperature: float | None = None
    default_max_tokens: int | None = None
    custom_settings: dict | None = None


class CreatePromptRequest(BaseModel):
    """Create prompt request."""
    name: str
    content: str
    prompt_type: PromptType = PromptType.INSTRUCTION
    description: str | None = None
    variables: list[str] = []
    is_default: bool = False
    tags: list[str] = []
    category: str | None = None
    capability_name: str | None = None


class UpdatePromptRequest(BaseModel):
    """Update prompt request."""
    name: str | None = None
    content: str | None = None
    description: str | None = None
    variables: list[str] | None = None
    is_default: bool | None = None
    tags: list[str] | None = None
    category: str | None = None


class PromptResponse(BaseModel):
    """Prompt response."""
    id: UUID
    name: str
    content: str
    prompt_type: PromptType
    description: str | None
    variables: list[str]
    is_default: bool
    use_count: int

    class Config:
        from_attributes = True


class RenderPromptRequest(BaseModel):
    """Render prompt with variables."""
    variables: dict[str, str]


class CancelSubscriptionRequest(BaseModel):
    """Cancel subscription request."""
    reason: str | None = None
    cancel_immediately: bool = False


# --- Profile Endpoints ---


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get your profile."""
    service = ProfileService(session)
    return await service.get_or_create_profile(agent.id)


@router.put("/me", response_model=ProfileResponse)
async def update_my_profile(
    update: ProfileUpdate,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Update your profile."""
    service = ProfileService(session)
    return await service.update_profile(agent.id, **update.model_dump(exclude_none=True))


@router.get("/{agent_id}", response_model=ProfileResponse)
async def get_profile(
    agent_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Get a public profile."""
    service = ProfileService(session)
    profile = await service.get_or_create_profile(agent_id)
    if not profile.is_public:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


# --- Settings Endpoints ---


@router.get("/settings")
async def get_settings(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get your settings."""
    service = ProfileService(session)
    return await service.get_or_create_settings(agent.id)


@router.put("/settings")
async def update_settings(
    update: SettingsUpdate,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Update your settings."""
    service = ProfileService(session)
    return await service.update_settings(agent.id, **update.model_dump(exclude_none=True))


# --- Custom Prompts Endpoints ---


@router.post("/prompts", response_model=PromptResponse)
async def create_prompt(
    request: CreatePromptRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Create a custom prompt."""
    service = ProfileService(session)
    return await service.create_prompt(
        agent_id=agent.id,
        **request.model_dump(),
    )


@router.get("/prompts", response_model=list[PromptResponse])
async def list_prompts(
    prompt_type: PromptType | None = None,
    capability_name: str | None = None,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """List your custom prompts."""
    service = ProfileService(session)
    return await service.list_prompts(agent.id, prompt_type, capability_name)


@router.get("/prompts/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get a specific prompt."""
    service = ProfileService(session)
    prompt = await service.get_prompt(prompt_id)
    if not prompt or prompt.agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.put("/prompts/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: UUID,
    request: UpdatePromptRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Update a prompt."""
    service = ProfileService(session)
    prompt = await service.update_prompt(
        prompt_id, agent.id, **request.model_dump(exclude_none=True)
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Delete a prompt."""
    service = ProfileService(session)
    if not await service.delete_prompt(prompt_id, agent.id):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"status": "deleted"}


@router.post("/prompts/{prompt_id}/render")
async def render_prompt(
    prompt_id: UUID,
    request: RenderPromptRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Render a prompt with variable substitution."""
    service = ProfileService(session)
    prompt = await service.get_prompt(prompt_id)
    if not prompt or prompt.agent_id != agent.id:
        raise HTTPException(status_code=404, detail="Prompt not found")

    rendered = await service.render_prompt(prompt_id, request.variables)
    return {"rendered": rendered}


# --- Subscription Endpoints ---


@router.get("/subscription")
async def get_subscription(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get your subscription status."""
    service = ProfileService(session)
    return await service.get_subscription_status(agent.id)


@router.post("/subscription/cancel")
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Cancel your subscription.

    By default, cancels at end of billing period.
    Set cancel_immediately=true to cancel right away.
    """
    service = ProfileService(session)
    try:
        sub = await service.cancel_subscription(
            agent.id,
            reason=request.reason,
            cancel_immediately=request.cancel_immediately,
        )
        return {
            "status": "canceled" if request.cancel_immediately else "will_cancel",
            "cancel_at_period_end": sub.cancel_at_period_end,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "message": "Subscription canceled immediately" if request.cancel_immediately
                       else "Subscription will cancel at end of billing period",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/subscription/reactivate")
async def reactivate_subscription(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Reactivate a subscription that was set to cancel."""
    service = ProfileService(session)
    try:
        sub = await service.reactivate_subscription(agent.id)
        return {
            "status": "reactivated",
            "plan": sub.plan_name,
            "message": "Subscription reactivated successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/subscription/create-customer")
async def create_customer(
    email: str,
    name: str | None = None,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Create a Stripe customer for billing."""
    service = ProfileService(session)
    try:
        sub = await service.create_stripe_customer(agent.id, email, name)
        return {
            "customer_id": sub.stripe_customer_id,
            "message": "Customer created",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
