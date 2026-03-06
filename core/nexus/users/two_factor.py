"""Two-factor authentication for users."""

import secrets
import base64
from io import BytesIO
from datetime import datetime, timezone
from uuid import UUID

import pyotp
import qrcode
from sqlalchemy import select, Boolean, DateTime, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import Base
from nexus.security.encryption import encrypt_value, decrypt_value


class UserTwoFactor(Base):
    """Two-factor authentication settings for a user."""

    __tablename__ = "user_two_factor"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    # TOTP secret (encrypted)
    totp_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Backup codes (hashed, one-time use)
    backup_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        default=list,
        server_default="{}",
    )
    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Timestamps
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
    )


class TwoFactorService:
    """Service for managing two-factor authentication."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.issuer = "Nexus"

    async def get_user_2fa(self, user_id: UUID) -> UserTwoFactor | None:
        """Get 2FA settings for a user."""
        result = await self.session.execute(
            select(UserTwoFactor).where(UserTwoFactor.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def setup_2fa(self, user_id: UUID, email: str) -> dict:
        """
        Initialize 2FA setup for a user.
        Returns the secret and QR code for authenticator app setup.
        """
        # Check if already set up
        existing = await self.get_user_2fa(user_id)
        if existing and existing.is_enabled:
            raise ValueError("2FA is already enabled for this account")

        # Generate new TOTP secret
        secret = pyotp.random_base32()

        # Generate backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
        # Hash backup codes for storage (using simple hash since they're one-time)
        import hashlib
        hashed_codes = [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes]

        # Create or update 2FA record
        if existing:
            existing.totp_secret_encrypted = encrypt_value(secret)
            existing.backup_codes = hashed_codes
            existing.is_verified = False
            two_factor = existing
        else:
            two_factor = UserTwoFactor(
                user_id=user_id,
                totp_secret_encrypted=encrypt_value(secret),
                backup_codes=hashed_codes,
                is_enabled=False,
                is_verified=False,
            )
            self.session.add(two_factor)

        await self.session.flush()

        # Generate QR code
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=email, issuer_name=self.issuer)

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            "secret": secret,
            "qr_code": f"data:image/png;base64,{qr_base64}",
            "backup_codes": backup_codes,  # Only shown once during setup
        }

    async def verify_and_enable(self, user_id: UUID, code: str) -> bool:
        """
        Verify a TOTP code and enable 2FA if valid.
        This is called during setup to confirm the user has set up their authenticator.
        """
        two_factor = await self.get_user_2fa(user_id)
        if not two_factor:
            raise ValueError("2FA not set up")

        if two_factor.is_enabled:
            raise ValueError("2FA is already enabled")

        # Decrypt and verify
        secret = decrypt_value(two_factor.totp_secret_encrypted)
        totp = pyotp.TOTP(secret)

        if totp.verify(code, valid_window=1):
            two_factor.is_enabled = True
            two_factor.is_verified = True
            two_factor.enabled_at = datetime.now(timezone.utc)
            await self.session.flush()
            return True

        return False

    async def verify_code(self, user_id: UUID, code: str) -> bool:
        """
        Verify a TOTP code during login.
        Also accepts backup codes (one-time use).
        """
        two_factor = await self.get_user_2fa(user_id)
        if not two_factor or not two_factor.is_enabled:
            return True  # 2FA not enabled, allow login

        # Try TOTP first
        secret = decrypt_value(two_factor.totp_secret_encrypted)
        totp = pyotp.TOTP(secret)

        if totp.verify(code, valid_window=1):
            two_factor.last_used_at = datetime.now(timezone.utc)
            await self.session.flush()
            return True

        # Try backup code
        import hashlib
        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        if code_hash in two_factor.backup_codes:
            # Remove used backup code
            two_factor.backup_codes = [c for c in two_factor.backup_codes if c != code_hash]
            two_factor.last_used_at = datetime.now(timezone.utc)
            await self.session.flush()
            return True

        return False

    async def disable_2fa(self, user_id: UUID, code: str) -> bool:
        """
        Disable 2FA for a user (requires valid code).
        """
        two_factor = await self.get_user_2fa(user_id)
        if not two_factor or not two_factor.is_enabled:
            raise ValueError("2FA is not enabled")

        # Verify code before disabling
        if not await self.verify_code(user_id, code):
            return False

        two_factor.is_enabled = False
        two_factor.is_verified = False
        await self.session.flush()
        return True

    async def regenerate_backup_codes(self, user_id: UUID, code: str) -> list[str] | None:
        """
        Generate new backup codes (requires valid 2FA code).
        """
        two_factor = await self.get_user_2fa(user_id)
        if not two_factor or not two_factor.is_enabled:
            raise ValueError("2FA is not enabled")

        # Verify code before regenerating
        if not await self.verify_code(user_id, code):
            return None

        # Generate new backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
        import hashlib
        hashed_codes = [hashlib.sha256(c.encode()).hexdigest() for c in backup_codes]

        two_factor.backup_codes = hashed_codes
        await self.session.flush()

        return backup_codes

    async def is_2fa_enabled(self, user_id: UUID) -> bool:
        """Check if 2FA is enabled for a user."""
        two_factor = await self.get_user_2fa(user_id)
        return two_factor is not None and two_factor.is_enabled
