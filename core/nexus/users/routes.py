"""API routes for user authentication."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.cache import get_cache
from nexus.database import get_db
from nexus.mailer import send_password_reset_email
from nexus.users.models import User
from nexus.users.schemas import (
    AuthResponse,
    ChangePassword,
    ForgotPassword,
    ResetPassword,
    TokenRefresh,
    UpdateProfile,
    UserLogin,
    UserRegister,
    UserResponse,
)
from nexus.users.service import UserService
from nexus.security.ip_utils import get_client_ip

router = APIRouter(prefix="/identity", tags=["users"])


async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    """Dependency to get user service."""
    return UserService(db)


async def get_current_user(
    request: Request,
    service: UserService = Depends(get_user_service),
) -> User:
    """Get the current authenticated user from the request."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = auth_header.split(" ")[1]
    payload = service.decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await service.get_user_by_id(UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


# --- Rate Limiting ---


async def auth_rate_limit(request: Request):
    """Rate limit auth endpoints to prevent brute force attacks."""
    cache = await get_cache()

    # SECURITY: Use secure IP extraction that validates X-Forwarded-For
    client_ip = get_client_ip(request)

    key = f"ratelimit:auth:{client_ip}"
    allowed, _, _ = await cache.rate_limit_check(
        key=key,
        limit=10,  # 10 attempts
        window_seconds=300,  # per 5 minutes
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": "300"},
        )


async def check_account_lockout(email: str) -> None:
    """
    SECURITY: Check if an account is locked due to failed login attempts.
    Progressive lockout: 5 failures = 5 min, 10 failures = 30 min, 15+ = 1 hour.
    """
    cache = await get_cache()

    lockout_key = f"account_lockout:{email.lower()}"
    lockout_until = await cache.get(lockout_key)

    if lockout_until:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "error": "account_locked",
                "message": "Account temporarily locked due to too many failed login attempts.",
            },
        )


async def record_failed_login(email: str) -> None:
    """
    SECURITY: Record a failed login attempt and apply lockout if threshold exceeded.
    """
    cache = await get_cache()

    failures_key = f"login_failures:{email.lower()}"

    # Increment failure count (with 1-hour expiry)
    failures = await cache.get(failures_key)
    failures = int(failures) + 1 if failures else 1
    await cache.set(failures_key, str(failures), ttl=3600)

    # Apply progressive lockout
    lockout_key = f"account_lockout:{email.lower()}"
    if failures >= 15:
        # 15+ failures: 1 hour lockout
        await cache.set(lockout_key, "1", ttl=3600)
    elif failures >= 10:
        # 10+ failures: 30 minute lockout
        await cache.set(lockout_key, "1", ttl=1800)
    elif failures >= 5:
        # 5+ failures: 5 minute lockout
        await cache.set(lockout_key, "1", ttl=300)


async def clear_login_failures(email: str) -> None:
    """Clear failed login attempts after successful login."""
    cache = await get_cache()
    await cache.delete(f"login_failures:{email.lower()}")
    await cache.delete(f"account_lockout:{email.lower()}")


# --- Auth Routes ---


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    data: UserRegister,
    request: Request,
    service: UserService = Depends(get_user_service),
    _: None = Depends(auth_rate_limit),
) -> AuthResponse:
    """Register a new user account."""
    # Check if email already exists
    existing = await service.get_user_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = await service.create_user(
        email=data.email,
        password=data.password,
        name=data.name,
    )

    # Create tokens
    user_agent = request.headers.get("User-Agent")
    # SECURITY: Use secure IP extraction
    ip = get_client_ip(request)

    access_token = service.create_access_token(user.id)
    refresh_token = service.create_refresh_token()
    await service.create_session(user.id, refresh_token, user_agent, ip)

    return AuthResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            email_verified=user.email_verified,
            created_at=user.created_at,
        ),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email and password",
)
async def login(
    data: UserLogin,
    request: Request,
    service: UserService = Depends(get_user_service),
    _: None = Depends(auth_rate_limit),
) -> AuthResponse:
    """Authenticate with email and password."""
    # SECURITY: Check if account is locked before attempting login
    await check_account_lockout(data.email)

    user_agent = request.headers.get("User-Agent")
    # SECURITY: Use secure IP extraction
    ip = get_client_ip(request)

    result = await service.login(data.email, data.password, user_agent, ip)
    if not result:
        # SECURITY: Record failed login attempt for account lockout
        await record_failed_login(data.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # SECURITY: Clear failed login attempts on successful login
    await clear_login_failures(data.email)

    user, access_token, refresh_token = result

    return AuthResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            email_verified=user.email_verified,
            created_at=user.created_at,
        ),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Refresh access token",
)
async def refresh_token(
    data: TokenRefresh,
    service: UserService = Depends(get_user_service),
) -> AuthResponse:
    """Refresh the access token using a refresh token."""
    result = await service.refresh_tokens(data.refresh_token)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token, new_refresh_token = result

    # Get user for response
    session = await service.validate_refresh_token(new_refresh_token)
    user = await service.get_user_by_id(session.user_id) if session else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return AuthResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            email_verified=user.email_verified,
            created_at=user.created_at,
        ),
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout")
async def logout(
    data: TokenRefresh,
    service: UserService = Depends(get_user_service),
) -> None:
    """Logout and revoke the refresh token."""
    session = await service.validate_refresh_token(data.refresh_token)
    if session:
        await service.revoke_session(session)


# --- Password Reset ---


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request password reset",
)
async def forgot_password(
    data: ForgotPassword,
    service: UserService = Depends(get_user_service),
    _: None = Depends(auth_rate_limit),
) -> dict:
    """Request a password reset email."""
    user = await service.get_user_by_email(data.email)

    # Always return success to prevent email enumeration
    if user:
        token = await service.create_password_reset_token(user.id)
        # Send email (async, don't wait)
        try:
            await send_password_reset_email(user.email, user.name, token)
        except Exception:
            pass  # Log but don't fail the request

    return {"message": "If the email exists, a reset link has been sent"}


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password with token",
)
async def reset_password(
    data: ResetPassword,
    service: UserService = Depends(get_user_service),
) -> dict:
    """Reset password using the reset token."""
    reset = await service.validate_reset_token(data.token)
    if not reset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user = await service.get_user_by_id(reset.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found",
        )

    # Change password
    await service.change_password(user, data.password)

    # Mark token as used
    await service.use_reset_token(reset)

    # Revoke all sessions (force re-login)
    await service.revoke_all_sessions(user.id)

    return {"message": "Password reset successfully"}


# --- Profile ---


@router.get("/me", response_model=UserResponse, summary="Get current user")
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get the current user's profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        email_verified=current_user.email_verified,
        created_at=current_user.created_at,
    )


@router.patch("/me", response_model=UserResponse, summary="Update profile")
async def update_me(
    data: UpdateProfile,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Update the current user's profile."""
    user = await service.update_user(current_user, name=data.name)
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        email_verified=user.email_verified,
        created_at=user.created_at,
    )


@router.post(
    "/me/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change password",
)
async def change_password(
    data: ChangePassword,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict:
    """Change the current user's password."""
    if not service.verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    await service.change_password(current_user, data.new_password)

    return {"message": "Password changed successfully"}


# --- Two-Factor Authentication ---


class TwoFactorSetupResponse(BaseModel):
    """Response for 2FA setup."""
    secret: str
    qr_code: str
    backup_codes: list[str]


class TwoFactorVerifyRequest(BaseModel):
    """Request to verify/enable 2FA."""
    code: str


class TwoFactorStatusResponse(BaseModel):
    """Response for 2FA status."""
    enabled: bool
    backup_codes_remaining: int | None = None


@router.get("/me/2fa", response_model=TwoFactorStatusResponse, summary="Get 2FA status")
async def get_2fa_status(
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> TwoFactorStatusResponse:
    """Get the current user's 2FA status."""
    from nexus.users.two_factor import TwoFactorService

    two_factor_service = TwoFactorService(service.session)
    two_factor = await two_factor_service.get_user_2fa(current_user.id)

    if not two_factor or not two_factor.is_enabled:
        return TwoFactorStatusResponse(enabled=False)

    return TwoFactorStatusResponse(
        enabled=True,
        backup_codes_remaining=len(two_factor.backup_codes),
    )


@router.post("/me/2fa/setup", response_model=TwoFactorSetupResponse, summary="Setup 2FA")
async def setup_2fa(
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> TwoFactorSetupResponse:
    """
    Initialize 2FA setup.

    Returns a QR code and backup codes. Scan the QR code with an authenticator app,
    then call /me/2fa/verify with a code to enable 2FA.

    **Save the backup codes securely - they are only shown once.**
    """
    from nexus.users.two_factor import TwoFactorService

    two_factor_service = TwoFactorService(service.session)

    try:
        result = await two_factor_service.setup_2fa(current_user.id, current_user.email)
        return TwoFactorSetupResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/me/2fa/verify", status_code=status.HTTP_200_OK, summary="Verify and enable 2FA")
async def verify_2fa(
    data: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict:
    """
    Verify a TOTP code and enable 2FA.

    Call this after setup with a code from your authenticator app to complete setup.
    """
    from nexus.users.two_factor import TwoFactorService

    two_factor_service = TwoFactorService(service.session)

    try:
        if await two_factor_service.verify_and_enable(current_user.id, data.code):
            return {"message": "2FA enabled successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/me/2fa/disable", status_code=status.HTTP_200_OK, summary="Disable 2FA")
async def disable_2fa(
    data: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict:
    """
    Disable 2FA for the current user.

    Requires a valid TOTP code or backup code to confirm.
    """
    from nexus.users.two_factor import TwoFactorService

    two_factor_service = TwoFactorService(service.session)

    try:
        if await two_factor_service.disable_2fa(current_user.id, data.code):
            return {"message": "2FA disabled successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/me/2fa/backup-codes", status_code=status.HTTP_200_OK, summary="Regenerate backup codes")
async def regenerate_backup_codes(
    data: TwoFactorVerifyRequest,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict:
    """
    Generate new backup codes.

    Requires a valid TOTP code. Old backup codes will be invalidated.

    **Save the new backup codes securely - they are only shown once.**
    """
    from nexus.users.two_factor import TwoFactorService

    two_factor_service = TwoFactorService(service.session)

    try:
        codes = await two_factor_service.regenerate_backup_codes(current_user.id, data.code)
        if codes:
            return {"backup_codes": codes}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
