"""User authentication service."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.config import get_settings
from nexus.users.models import PasswordResetToken, User, UserSession


class UserService:
    """Service for user authentication and management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    # --- Password Hashing ---

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

    # --- Token Generation ---

    def create_access_token(self, user_id: UUID, expires_delta: timedelta | None = None) -> str:
        """Create a JWT access token."""
        if expires_delta is None:
            expires_delta = timedelta(minutes=15)

        expire = datetime.now(timezone.utc) + expires_delta
        payload = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, self.settings.secret_key, algorithm="HS256")

    def create_refresh_token(self) -> str:
        """Create a random refresh token."""
        return secrets.token_urlsafe(64)

    def hash_token(self, token: str) -> str:
        """Hash a token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    def decode_access_token(self, token: str) -> dict | None:
        """Decode and validate an access token."""
        try:
            payload = jwt.decode(token, self.settings.secret_key, algorithms=["HS256"])
            if payload.get("type") != "access":
                return None
            return payload
        except jwt.PyJWTError:
            return None

    # --- User Operations ---

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email."""
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get a user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_user(self, email: str, password: str, name: str) -> User:
        """Create a new user."""
        user = User(
            email=email.lower(),
            password_hash=self.hash_password(password),
            name=name,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user(self, user: User, name: str | None = None) -> User:
        """Update user profile."""
        if name is not None:
            user.name = name
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def change_password(self, user: User, new_password: str) -> None:
        """Change user's password."""
        user.password_hash = self.hash_password(new_password)
        await self.db.commit()

    # --- Session Management ---

    async def create_session(
        self,
        user_id: UUID,
        refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> UserSession:
        """Create a new user session."""
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=self.hash_token(refresh_token),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        self.db.add(session)
        await self.db.commit()
        return session

    async def validate_refresh_token(self, refresh_token: str) -> UserSession | None:
        """Validate a refresh token and return the session."""
        token_hash = self.hash_token(refresh_token)
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.expires_at > datetime.now(timezone.utc),
                UserSession.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, session: UserSession) -> None:
        """Revoke a user session."""
        session.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def revoke_all_sessions(self, user_id: UUID) -> None:
        """Revoke all sessions for a user."""
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        sessions = result.scalars().all()
        for session in sessions:
            session.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()

    # --- Password Reset ---

    async def create_password_reset_token(self, user_id: UUID) -> str:
        """Create a password reset token."""
        token = secrets.token_urlsafe(32)
        reset = PasswordResetToken(
            user_id=user_id,
            token_hash=self.hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.db.add(reset)
        await self.db.commit()
        return token

    async def validate_reset_token(self, token: str) -> PasswordResetToken | None:
        """Validate a password reset token."""
        token_hash = self.hash_token(token)
        result = await self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
                PasswordResetToken.used_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def use_reset_token(self, reset: PasswordResetToken) -> None:
        """Mark a reset token as used."""
        reset.used_at = datetime.now(timezone.utc)
        await self.db.commit()

    # --- Login/Logout ---

    async def login(
        self,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, str, str] | None:
        """
        Authenticate a user and return tokens.
        Returns: (user, access_token, refresh_token) or None if invalid.
        """
        user = await self.get_user_by_email(email)
        if not user or not user.is_active:
            return None

        if not self.verify_password(password, user.password_hash):
            return None

        # Update last login
        user.last_login = datetime.now(timezone.utc)

        # Create tokens
        access_token = self.create_access_token(user.id)
        refresh_token = self.create_refresh_token()

        # Create session
        await self.create_session(user.id, refresh_token, user_agent, ip_address)

        await self.db.commit()
        return user, access_token, refresh_token

    async def refresh_tokens(
        self,
        refresh_token: str,
    ) -> tuple[str, str] | None:
        """
        Refresh access and refresh tokens.
        Returns: (new_access_token, new_refresh_token) or None if invalid.
        """
        session = await self.validate_refresh_token(refresh_token)
        if not session:
            return None

        user = await self.get_user_by_id(session.user_id)
        if not user or not user.is_active:
            return None

        # Revoke old session
        await self.revoke_session(session)

        # Create new tokens
        access_token = self.create_access_token(user.id)
        new_refresh_token = self.create_refresh_token()

        # Create new session
        await self.create_session(user.id, new_refresh_token)

        return access_token, new_refresh_token
