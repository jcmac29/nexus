"""Tests for security module."""

import pytest

from nexus.security.encryption import (
    encrypt_value,
    decrypt_value,
    hash_value,
    verify_hash,
    generate_key,
    EncryptionService,
)
from nexus.security.tokens import (
    create_access_token,
    create_refresh_token,
    verify_token,
    revoke_token,
    TokenService,
)


class TestEncryption:
    """Tests for encryption utilities."""

    def test_generate_key(self):
        """Test key generation."""
        key1 = generate_key()
        key2 = generate_key()

        assert key1 != key2
        assert len(key1) > 20

    def test_encrypt_decrypt(self):
        """Test encryption and decryption."""
        plaintext = "Hello, World!"
        ciphertext = encrypt_value(plaintext)

        assert ciphertext != plaintext
        assert decrypt_value(ciphertext) == plaintext

    def test_encryption_service(self):
        """Test EncryptionService class."""
        service = EncryptionService(key="test-secret-key-12345")

        plaintext = "sensitive data"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert encrypted != plaintext
        assert decrypted == plaintext

    def test_encrypt_dict(self):
        """Test dictionary encryption."""
        service = EncryptionService(key="test-secret-key-12345")

        data = {"password": "secret123", "count": 42}
        encrypted = service.encrypt_dict(data)

        assert encrypted["password"] != "secret123"
        assert encrypted["count"] == 42

    def test_hash_and_verify(self):
        """Test password hashing."""
        password = "my-secure-password"
        hashed = hash_value(password)

        assert hashed != password
        assert verify_hash(password, hashed)
        assert not verify_hash("wrong-password", hashed)


class TestTokens:
    """Tests for JWT token management."""

    def test_create_access_token(self):
        """Test access token creation."""
        token = create_access_token(
            subject="user-123",
            scopes=["read", "write"],
        )

        assert token is not None
        assert len(token) > 50

    def test_verify_access_token(self):
        """Test access token verification."""
        token = create_access_token(
            subject="user-123",
            scopes=["read", "write"],
        )

        payload = verify_token(token, expected_type="access")

        assert payload is not None
        assert payload.sub == "user-123"
        assert "read" in payload.scopes

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        token = create_refresh_token(subject="user-123")

        assert token is not None
        payload = verify_token(token, expected_type="refresh")
        assert payload.type == "refresh"

    def test_revoke_token(self):
        """Test token revocation."""
        token = create_access_token(subject="user-123")

        # Should verify before revocation
        assert verify_token(token) is not None

        # Revoke
        assert revoke_token(token)

        # Should not verify after revocation
        assert verify_token(token) is None

    def test_token_service_refresh(self):
        """Test token refresh flow."""
        service = TokenService()

        # Create initial tokens
        access_token = service.create_access_token(
            subject="user-123",
            scopes=["read"],
        )
        refresh_token = service.create_refresh_token(subject="user-123")

        # Refresh tokens
        result = service.refresh_access_token(refresh_token)

        assert result is not None
        new_access, new_refresh = result

        # Verify new tokens
        assert verify_token(new_access) is not None
        assert verify_token(new_refresh, expected_type="refresh") is not None

        # Old refresh token should be revoked
        assert service.refresh_access_token(refresh_token) is None

    def test_invalid_token(self):
        """Test invalid token handling."""
        payload = verify_token("invalid-token")
        assert payload is None

    def test_wrong_token_type(self):
        """Test token type validation."""
        refresh_token = create_refresh_token(subject="user-123")

        # Should fail when expecting access token
        payload = verify_token(refresh_token, expected_type="access")
        assert payload is None
