"""Admin API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.admin.auth import get_current_admin
from nexus.admin.models import AdminRole, AdminUser
from nexus.admin.schemas import (
    ActivityItem,
    AdminUserResponse,
    AgentCreate,
    AgentDetail,
    AgentSummary,
    AgentUpdate,
    DashboardStats,
    InstanceSettings,
    InstanceSettingsUpdate,
    LoginRequest,
    LoginResponse,
    MemorySearchResult,
    PaginatedResponse,
    RefreshRequest,
    TeamCreate,
    TeamDetail,
    TeamMemberAdd,
    TeamSummary,
    TeamUpdate,
)
from nexus.admin.service import AdminService
from nexus.cache import get_cache
from nexus.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Rate Limiting for Login ---

async def login_rate_limit(request: Request):
    """
    SECURITY: Rate limit login attempts to prevent brute force attacks.
    Limit: 5 attempts per minute per IP address.
    """
    cache = await get_cache()

    # Get client IP (handle proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    key = f"ratelimit:admin:login:{client_ip}"

    allowed, current, remaining = await cache.rate_limit_check(
        key=key,
        limit=5,  # 5 attempts
        window_seconds=60,  # per minute
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many login attempts. Please try again later.",
                "retry_after": 60,
            },
            headers={"Retry-After": "60"},
        )


# ============================================================================
# Authentication Endpoints
# ============================================================================


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(login_rate_limit),  # SECURITY: Rate limit login attempts
):
    """Login with email and password."""
    service = AdminService(db)
    result = await service.authenticate(request.email, request.password)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return result


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    service = AdminService(db)
    result = await service.refresh_tokens(request.refresh_token)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    return result


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    admin: AdminUser = Depends(get_current_admin),
):
    """Logout (client should discard tokens)."""
    # JWT tokens are stateless, so we just return success
    # In a production system, you might want to blacklist the token
    return None


@router.get("/auth/me", response_model=AdminUserResponse)
async def get_current_user(
    admin: AdminUser = Depends(get_current_admin),
):
    """Get current admin user info."""
    return admin


# ============================================================================
# Dashboard Endpoints
# ============================================================================


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard statistics."""
    service = AdminService(db)

    # Super admins see all data, others see their account only
    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id

    return await service.get_dashboard_stats(account_id)


@router.get("/agents", response_model=PaginatedResponse)
async def list_agents(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: str | None = None,
):
    """List all agents with pagination."""
    service = AdminService(db)

    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id
    agents, total = await service.list_agents(account_id, page, page_size, search)

    return PaginatedResponse(
        items=[AgentSummary.model_validate(a) for a in agents],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/teams", response_model=PaginatedResponse)
async def list_teams(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """List all teams with pagination."""
    service = AdminService(db)

    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id
    teams, total = await service.list_teams(account_id, page, page_size)

    return PaginatedResponse(
        items=[TeamSummary.model_validate(t) for t in teams],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/memories", response_model=PaginatedResponse)
async def search_memories(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    q: str = Query(..., min_length=1, description="Search query"),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Search memories across all agents."""
    service = AdminService(db)

    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id
    memories, total = await service.search_memories(q, account_id, page, page_size)

    return PaginatedResponse(
        items=[MemorySearchResult.model_validate(m) for m in memories],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/activity", response_model=list[ActivityItem])
async def get_recent_activity(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """Get recent activity feed."""
    service = AdminService(db)

    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id
    return await service.get_recent_activity(account_id, limit)


# ============================================================================
# Agent CRUD Endpoints
# ============================================================================


@router.post("/agents", response_model=AgentSummary, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent."""
    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create agents",
        )

    service = AdminService(db)
    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id

    try:
        return await service.create_agent(
            name=data.name,
            slug=data.slug,
            description=data.description,
            status=data.status,
            account_id=account_id,
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent with this slug already exists",
            )
        raise


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get agent details by ID."""
    from uuid import UUID

    service = AdminService(db)
    agent = await service.get_agent(UUID(agent_id))

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return agent


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    data: AgentUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update agents",
        )

    service = AdminService(db)
    agent = await service.update_agent(
        UUID(agent_id),
        data.model_dump(exclude_unset=True),
    )

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return agent


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete agents",
        )

    service = AdminService(db)
    deleted = await service.delete_agent(UUID(agent_id))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )


# ============================================================================
# Team CRUD Endpoints
# ============================================================================


@router.post("/teams", response_model=TeamSummary, status_code=status.HTTP_201_CREATED)
async def create_team(
    data: TeamCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new team."""
    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create teams",
        )

    service = AdminService(db)

    try:
        return await service.create_team(
            name=data.name,
            slug=data.slug,
            owner_agent_id=data.owner_agent_id,
            description=data.description,
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team with this slug already exists",
            )
        if "foreign key" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Owner agent not found",
            )
        raise


@router.get("/teams/{team_id}")
async def get_team(
    team_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get team details by ID."""
    from uuid import UUID

    service = AdminService(db)
    team = await service.get_team(UUID(team_id))

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    return team


@router.put("/teams/{team_id}")
async def update_team(
    team_id: str,
    data: TeamUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a team."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update teams",
        )

    service = AdminService(db)
    team = await service.update_team(
        UUID(team_id),
        data.model_dump(exclude_unset=True),
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    return team


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a team."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete teams",
        )

    service = AdminService(db)
    deleted = await service.delete_team(UUID(team_id))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )


@router.post("/teams/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: str,
    data: TeamMemberAdd,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a member to a team."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can manage team members",
        )

    service = AdminService(db)

    try:
        added = await service.add_team_member(
            UUID(team_id),
            data.agent_id,
            data.role,
        )
    except Exception as e:
        if "foreign key" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent or team not found",
            )
        raise

    if not added:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent is already a team member",
        )

    return {"message": "Member added successfully"}


@router.delete("/teams/{team_id}/members/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: str,
    agent_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from a team."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can manage team members",
        )

    service = AdminService(db)
    removed = await service.remove_team_member(UUID(team_id), UUID(agent_id))

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in team",
        )


# ============================================================================
# Memory Management Endpoints
# ============================================================================


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a memory."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete memories",
        )

    service = AdminService(db)
    deleted = await service.delete_memory(UUID(memory_id))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )


@router.post("/memories/bulk-delete")
async def bulk_delete_memories(
    memory_ids: list[str],
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple memories."""
    from uuid import UUID

    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete memories",
        )

    service = AdminService(db)
    deleted = await service.bulk_delete_memories([UUID(mid) for mid in memory_ids])

    return {"deleted": deleted}


# ============================================================================
# Settings Endpoints
# ============================================================================


@router.get("/settings", response_model=InstanceSettings)
async def get_settings(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get instance settings."""
    service = AdminService(db)
    return await service.get_instance_settings()


@router.patch("/settings", response_model=InstanceSettings)
async def update_settings(
    updates: InstanceSettingsUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update instance settings (admin only)."""
    if admin.role not in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update settings",
        )

    service = AdminService(db)
    return await service.update_instance_settings(updates.model_dump(exclude_unset=True))


# ============================================================================
# Federation Endpoints
# ============================================================================


@router.get("/federation/peers")
async def get_federation_peers(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get federation peers."""
    service = AdminService(db)
    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id
    return await service.get_federation_peers(account_id)


# ============================================================================
# Audit Log Endpoints
# ============================================================================


@router.get("/audit/logs")
async def get_audit_logs(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Get audit logs."""
    service = AdminService(db)
    account_id = None if admin.role == AdminRole.SUPER_ADMIN else admin.account_id
    return await service.get_audit_logs(account_id, limit)
