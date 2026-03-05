"""Schemas for user authentication."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=100)


class UserLogin(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User response schema."""

    id: UUID
    email: str
    name: str
    email_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Authentication response with tokens."""

    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    """Token refresh request."""

    refresh_token: str


class ForgotPassword(BaseModel):
    """Forgot password request."""

    email: EmailStr


class ResetPassword(BaseModel):
    """Password reset request."""

    token: str
    password: str = Field(..., min_length=8)


class ChangePassword(BaseModel):
    """Change password request."""

    current_password: str
    new_password: str = Field(..., min_length=8)


class UpdateProfile(BaseModel):
    """Update user profile."""

    name: str | None = Field(None, min_length=1, max_length=100)
