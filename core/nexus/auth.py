"""Authentication middleware and dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db

if TYPE_CHECKING:
    from nexus.identity.models import Agent

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def get_current_agent(
    api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> "Agent":
    """
    Dependency to get the current authenticated agent from API key.

    Expects header: Authorization: Bearer nex_xxxxx
    """
    # Import here to avoid circular imports
    from nexus.identity.service import IdentityService

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Handle "Bearer " prefix
    if api_key.startswith("Bearer "):
        api_key = api_key[7:]

    service = IdentityService(db)
    agent = await service.verify_api_key(api_key)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return agent


async def get_optional_agent(
    api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> "Agent | None":
    """
    Dependency to optionally get the current agent.

    Returns None if not authenticated (for public endpoints).
    """
    from nexus.identity.service import IdentityService

    if not api_key:
        return None

    if api_key.startswith("Bearer "):
        api_key = api_key[7:]

    service = IdentityService(db)
    return await service.verify_api_key(api_key)


def require_scopes(*required_scopes: str):
    """
    Dependency factory to require specific scopes.

    Usage:
        @router.post("/admin", dependencies=[Depends(require_scopes("admin"))])
    """

    async def check_scopes(
        api_key: str | None = Security(api_key_header),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        from nexus.identity.service import IdentityService

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key",
            )

        if api_key.startswith("Bearer "):
            api_key = api_key[7:]

        service = IdentityService(db)
        agent, api_key_record = await service.verify_api_key_with_record(api_key)

        if not agent or not api_key_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        # SECURITY: Actually validate the required scopes
        if required_scopes:
            agent_scopes = set(api_key_record.scopes or [])
            required_set = set(required_scopes)

            # Check if agent has at least one of the required scopes
            if not agent_scopes.intersection(required_set):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )

    return check_scopes
