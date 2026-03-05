"""Encryption utilities for Nexus."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import bcrypt

from nexus.config import get_settings


def generate_key(length: int = 32) -> str:
    """Generate a cryptographically secure random key."""
    return secrets.token_urlsafe(length)


def derive_key(password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
    """Derive an encryption key from a password using PBKDF2."""
    if salt is None:
        salt = secrets.token_bytes(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt


def hash_value(value: str) -> str:
    """Hash a value using bcrypt."""
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()


def verify_hash(value: str, hashed: str) -> bool:
    """Verify a value against a bcrypt hash."""
    try:
        return bcrypt.checkpw(value.encode(), hashed.encode())
    except Exception:
        return False


def sha256_hash(value: str) -> str:
    """Generate SHA-256 hash of a value."""
    return hashlib.sha256(value.encode()).hexdigest()


class EncryptionService:
    """Service for encrypting and decrypting sensitive data."""

    def __init__(self, key: Optional[str] = None):
        """Initialize encryption service with a key."""
        import logging
        logger = logging.getLogger(__name__)

        if key is None:
            settings = get_settings()
            key = settings.secret_key

        # SECURITY: Validate key strength
        # Fernet requires a 32-byte key. We derive it from the secret,
        # so the secret should be high-entropy to prevent brute force.
        if len(key) < 32:
            logger.warning(
                "SECURITY WARNING: Encryption secret_key is less than 32 characters. "
                "This may be vulnerable to brute force attacks. "
                "Use a cryptographically random key of at least 32 characters."
            )

        # Check for common weak keys
        weak_keys = {"secret", "password", "changeme", "nexus-secret-key", "nexus-secret"}
        if key.lower() in weak_keys or key.lower().startswith("changeme"):
            logger.error(
                "SECURITY ERROR: Using a default or weak encryption key. "
                "Set NEXUS_SECRET_KEY to a cryptographically random value in production!"
            )

        # Derive a proper Fernet key from the secret using SHA256
        # Note: For maximum security, the input key should already be high-entropy
        key_bytes = hashlib.sha256(key.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext and return base64-encoded ciphertext."""
        ciphertext = self._fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(ciphertext).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64-encoded ciphertext and return plaintext."""
        ciphertext_bytes = base64.urlsafe_b64decode(ciphertext.encode())
        plaintext = self._fernet.decrypt(ciphertext_bytes)
        return plaintext.decode()

    def encrypt_dict(self, data: dict) -> dict:
        """Encrypt all string values in a dictionary."""
        return {
            key: self.encrypt(value) if isinstance(value, str) else value
            for key, value in data.items()
        }

    def decrypt_dict(self, data: dict) -> dict:
        """Decrypt all string values in a dictionary."""
        return {
            key: self.decrypt(value) if isinstance(value, str) else value
            for key, value in data.items()
        }


# Global encryption service instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """Get or create the global encryption service."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_value(value: str) -> str:
    """Encrypt a value using the global encryption service."""
    return get_encryption_service().encrypt(value)


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a value using the global encryption service."""
    return get_encryption_service().decrypt(ciphertext)
