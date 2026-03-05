"""Tenant management API routes."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.tenants.limits import LimitsService
from nexus.tenants.models import TenantInvite, TenantSettings
from nexus.tenants.middleware import get_tenant_id

router = APIRouter(prefix="/tenants", tags=["tenants"])


# --- Schemas ---


class TenantSettingsCreate(BaseModel):
    """Request to create tenant settings."""

    subdomain: str | None = Field(default=None, min_length=3, max_length=63, pattern="^[a-z0-9-]+$")
    custom_domain: str | None = None
    display_name: str | None = Field(default=None, max_length=100)
    logo_url: str | None = None
    primary_color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    features: dict = Field(default_factory=dict)
    allowed_ip_ranges: list[str] | None = None
    require_2fa: bool = False


class TenantSettingsUpdate(BaseModel):
    """Request to update tenant settings."""

    subdomain: str | None = Field(default=None, min_length=3, max_length=63, pattern="^[a-z0-9-]+$")
    custom_domain: str | None = None
    display_name: str | None = Field(default=None, max_length=100)
    logo_url: str | None = None
    primary_color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    features: dict | None = None
    allowed_ip_ranges: list[str] | None = None
    require_2fa: bool | None = None


class TenantSettingsResponse(BaseModel):
    """Response containing tenant settings."""

    id: UUID
    account_id: UUID
    subdomain: str | None
    custom_domain: str | None
    display_name: str | None
    logo_url: str | None
    primary_color: str | None
    features: dict
    allowed_ip_ranges: list[str] | None
    require_2fa: bool
    rate_limit_multiplier: float
    data_region: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantInviteCreate(BaseModel):
    """Request to create a tenant invite."""

    email: EmailStr
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")


class TenantInviteResponse(BaseModel):
    """Response containing a tenant invite."""

    id: UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime
    accepted: bool

    model_config = {"from_attributes": True}


class LimitStatusResponse(BaseModel):
    """Response containing limit status."""

    agents: dict
    memories: dict
    team_members: dict


# --- Service helpers ---


async def get_limits_service(db: AsyncSession = Depends(get_db)) -> LimitsService:
    """Get limits service instance."""
    return LimitsService(db)


async def get_agent_account_id(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Get the account ID for the current agent."""
    if hasattr(agent, "account_id") and agent.account_id:
        return agent.account_id

    # Fall back to looking up account by agent
    from nexus.billing.models import Account

    # For now, assume single account or return error
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Agent is not associated with an account",
    )


# --- Routes ---


@router.get("/settings", response_model=TenantSettingsResponse)
async def get_tenant_settings(
    account_id: UUID = Depends(get_agent_account_id),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant settings for the current account."""
    stmt = select(TenantSettings).where(TenantSettings.account_id == account_id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant settings not found",
        )

    return TenantSettingsResponse.model_validate(settings)


@router.post("/settings", response_model=TenantSettingsResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant_settings(
    data: TenantSettingsCreate,
    account_id: UUID = Depends(get_agent_account_id),
    db: AsyncSession = Depends(get_db),
):
    """Create tenant settings for the current account."""
    # Check if settings already exist
    stmt = select(TenantSettings).where(TenantSettings.account_id == account_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant settings already exist",
        )

    # Check subdomain uniqueness
    if data.subdomain:
        subdomain_check = await db.execute(
            select(TenantSettings).where(TenantSettings.subdomain == data.subdomain)
        )
        if subdomain_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Subdomain already in use",
            )

    settings = TenantSettings(
        account_id=account_id,
        subdomain=data.subdomain,
        custom_domain=data.custom_domain,
        display_name=data.display_name,
        logo_url=data.logo_url,
        primary_color=data.primary_color,
        features=data.features,
        allowed_ip_ranges=data.allowed_ip_ranges,
        require_2fa=data.require_2fa,
    )
    db.add(settings)
    await db.commit()
    await db.refresh(settings)

    return TenantSettingsResponse.model_validate(settings)


@router.patch("/settings", response_model=TenantSettingsResponse)
async def update_tenant_settings(
    data: TenantSettingsUpdate,
    account_id: UUID = Depends(get_agent_account_id),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant settings."""
    stmt = select(TenantSettings).where(TenantSettings.account_id == account_id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant settings not found",
        )

    # Check subdomain uniqueness if changing
    if data.subdomain and data.subdomain != settings.subdomain:
        subdomain_check = await db.execute(
            select(TenantSettings).where(TenantSettings.subdomain == data.subdomain)
        )
        if subdomain_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Subdomain already in use",
            )

    # Apply updates
    # SECURITY: Whitelist of allowed fields to prevent mass assignment attacks
    allowed_fields = {
        "subdomain", "custom_domain", "display_name", "logo_url", "primary_color",
        "features", "allowed_ip_ranges", "require_2fa", "rate_limit_multiplier",
        "custom_rate_limits", "data_region", "retention_days",
    }
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key in allowed_fields:
            setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)

    return TenantSettingsResponse.model_validate(settings)


@router.get("/limits", response_model=LimitStatusResponse)
async def get_limit_status(
    account_id: UUID = Depends(get_agent_account_id),
    service: LimitsService = Depends(get_limits_service),
):
    """Get current resource limit status."""
    return await service.get_limit_status(account_id)


@router.post("/invites", response_model=TenantInviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    data: TenantInviteCreate,
    agent: Agent = Depends(get_current_agent),
    account_id: UUID = Depends(get_agent_account_id),
    db: AsyncSession = Depends(get_db),
):
    """Create an invitation to join the tenant."""
    # Check for existing pending invite
    stmt = select(TenantInvite).where(
        TenantInvite.account_id == account_id,
        TenantInvite.email == data.email,
        TenantInvite.accepted_at.is_(None),
        TenantInvite.expires_at > datetime.now(timezone.utc),
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active invite already exists for this email",
        )

    invite = TenantInvite(
        account_id=account_id,
        email=data.email,
        role=data.role,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_by=agent.id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    return TenantInviteResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        accepted=invite.accepted_at is not None,
    )


@router.get("/invites", response_model=list[TenantInviteResponse])
async def list_invites(
    include_expired: bool = Query(default=False),
    account_id: UUID = Depends(get_agent_account_id),
    db: AsyncSession = Depends(get_db),
):
    """List all invitations for the tenant."""
    conditions = [TenantInvite.account_id == account_id]
    if not include_expired:
        conditions.append(TenantInvite.expires_at > datetime.now(timezone.utc))

    stmt = select(TenantInvite).where(*conditions).order_by(TenantInvite.created_at.desc())
    result = await db.execute(stmt)
    invites = list(result.scalars().all())

    return [
        TenantInviteResponse(
            id=invite.id,
            email=invite.email,
            role=invite.role,
            expires_at=invite.expires_at,
            created_at=invite.created_at,
            accepted=invite.accepted_at is not None,
        )
        for invite in invites
    ]


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    invite_id: UUID,
    account_id: UUID = Depends(get_agent_account_id),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a pending invitation."""
    stmt = select(TenantInvite).where(
        TenantInvite.id == invite_id,
        TenantInvite.account_id == account_id,
    )
    result = await db.execute(stmt)
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    await db.delete(invite)
    await db.commit()


@router.get("/current")
async def get_current_tenant(request: Request):
    """Get information about the current tenant context."""
    tenant_id = get_tenant_id(request)
    if not tenant_id:
        return {"tenant_id": None, "is_multi_tenant": False}

    return {
        "tenant_id": str(tenant_id),
        "is_multi_tenant": True,
        "settings": getattr(request.state, "tenant_settings", {}),
    }
