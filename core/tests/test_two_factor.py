"""Tests for two-factor authentication."""

import pytest
import pyotp
import uuid
from httpx import AsyncClient

from nexus.main import app


@pytest.fixture
async def user_tokens(client: AsyncClient):
    """Create a test user and return auth tokens."""
    # Use unique email to avoid conflicts
    unique_email = f"2fa-test-{uuid.uuid4().hex[:8]}@example.com"

    # Register a new user
    response = await client.post(
        "/api/v1/identity/register",
        json={
            "email": unique_email,
            "password": "TestPassword123!",
            "name": "2FA Test User",
        },
    )

    assert response.status_code == 201
    data = response.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }


@pytest.fixture
def auth_headers(user_tokens):
    """Return auth headers for authenticated requests."""
    return {"Authorization": f"Bearer {user_tokens['access_token']}"}


class TestTwoFactorAuthentication:
    """Test 2FA endpoints."""

    async def test_get_2fa_status_disabled(self, client: AsyncClient, auth_headers):
        """Test getting 2FA status when disabled."""
        response = await client.get("/api/v1/identity/me/2fa", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] == False
        assert data.get("backup_codes_remaining") is None

    async def test_setup_2fa(self, client: AsyncClient, auth_headers):
        """Test setting up 2FA."""
        response = await client.post("/api/v1/identity/me/2fa/setup", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "secret" in data
        assert "qr_code" in data
        assert "backup_codes" in data

        # Secret should be base32 encoded
        assert len(data["secret"]) == 32

        # QR code should be base64 image
        assert data["qr_code"].startswith("data:image/png;base64,")

        # Should have 8 backup codes
        assert len(data["backup_codes"]) == 8

    async def test_verify_and_enable_2fa(self, client: AsyncClient, auth_headers):
        """Test enabling 2FA with valid code."""
        # Setup first
        setup_response = await client.post("/api/v1/identity/me/2fa/setup", headers=auth_headers)
        assert setup_response.status_code == 200
        secret = setup_response.json()["secret"]

        # Generate valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Verify and enable
        response = await client.post(
            "/api/v1/identity/me/2fa/verify",
            headers=auth_headers,
            json={"code": code},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "2FA enabled successfully"

        # Verify status is now enabled
        status_response = await client.get("/api/v1/identity/me/2fa", headers=auth_headers)
        assert status_response.status_code == 200
        assert status_response.json()["enabled"] == True

    async def test_verify_2fa_invalid_code(self, client: AsyncClient, auth_headers):
        """Test enabling 2FA with invalid code."""
        # Setup first
        await client.post("/api/v1/identity/me/2fa/setup", headers=auth_headers)

        # Try invalid code
        response = await client.post(
            "/api/v1/identity/me/2fa/verify",
            headers=auth_headers,
            json={"code": "000000"},
        )
        assert response.status_code == 400
        assert "Invalid verification code" in response.json()["detail"]

    async def test_disable_2fa(self, client: AsyncClient, auth_headers):
        """Test disabling 2FA."""
        # Setup and enable first
        setup_response = await client.post("/api/v1/identity/me/2fa/setup", headers=auth_headers)
        secret = setup_response.json()["secret"]

        totp = pyotp.TOTP(secret)
        code = totp.now()

        await client.post(
            "/api/v1/identity/me/2fa/verify",
            headers=auth_headers,
            json={"code": code},
        )

        # Disable with valid code
        disable_code = totp.now()
        response = await client.post(
            "/api/v1/identity/me/2fa/disable",
            headers=auth_headers,
            json={"code": disable_code},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "2FA disabled successfully"

        # Verify status is now disabled
        status_response = await client.get("/api/v1/identity/me/2fa", headers=auth_headers)
        assert status_response.json()["enabled"] == False

    async def test_regenerate_backup_codes(self, client: AsyncClient, auth_headers):
        """Test regenerating backup codes."""
        # Setup and enable first
        setup_response = await client.post("/api/v1/identity/me/2fa/setup", headers=auth_headers)
        secret = setup_response.json()["secret"]
        original_codes = setup_response.json()["backup_codes"]

        totp = pyotp.TOTP(secret)
        code = totp.now()

        await client.post(
            "/api/v1/identity/me/2fa/verify",
            headers=auth_headers,
            json={"code": code},
        )

        # Regenerate backup codes
        regen_code = totp.now()
        response = await client.post(
            "/api/v1/identity/me/2fa/backup-codes",
            headers=auth_headers,
            json={"code": regen_code},
        )
        assert response.status_code == 200
        new_codes = response.json()["backup_codes"]

        # Should have 8 new codes
        assert len(new_codes) == 8

        # Codes should be different
        assert set(new_codes) != set(original_codes)
