"""Admin authentication using JWT."""

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.admin.models import AdminRole, AdminUser
from nexus.config import get_settings
from nexus.database import get_db

security = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(
    admin_id: UUID,
    account_id: UUID | None,
    role: AdminRole,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token for an admin user."""
    settings = get_settings()

    if expires_delta is None:
        expires_delta = timedelta(hours=settings.admin_token_expire_hours)

    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(admin_id),
        "account_id": str(account_id) if account_id else None,
        "role": role.value,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(admin_id: UUID, expires_days: int = 30) -> str:
    """Create a refresh token."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)
    payload = {
        "sub": str(admin_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.admin_jwt_secret, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """
    Dependency to get the current authenticated admin user.

    Expects header: Authorization: Bearer <jwt_token>
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    admin_id = payload.get("sub")
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    stmt = select(AdminUser).where(
        AdminUser.id == UUID(admin_id),
        AdminUser.is_active == True,
    )
    result = await db.execute(stmt)
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found or inactive",
        )

    return admin


async def get_optional_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> AdminUser | None:
    """Optionally get the current admin user (for public endpoints)."""
    if not credentials:
        return None

    try:
        return await get_current_admin(credentials, db)
    except HTTPException:
        return None


def require_admin_role(*allowed_roles: AdminRole):
    """
    Dependency factory to require specific admin roles.

    Usage:
        @router.get("/settings", dependencies=[Depends(require_admin_role(AdminRole.ADMIN))])
    """

    async def check_role(
        admin: AdminUser = Depends(get_current_admin),
    ) -> AdminUser:
        if admin.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return admin

    return check_role
