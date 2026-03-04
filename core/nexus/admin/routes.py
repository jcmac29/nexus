"""Admin API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.admin.auth import get_current_admin
from nexus.admin.models import AdminRole, AdminUser
from nexus.admin.schemas import (
    ActivityItem,
    AdminUserResponse,
    AgentSummary,
    DashboardStats,
    InstanceSettings,
    InstanceSettingsUpdate,
    LoginRequest,
    LoginResponse,
    MemorySearchResult,
    PaginatedResponse,
    RefreshRequest,
    TeamSummary,
)
from nexus.admin.service import AdminService
from nexus.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Authentication Endpoints
# ============================================================================


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
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
