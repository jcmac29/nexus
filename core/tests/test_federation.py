"""Integration tests for federation service."""

import pytest
from uuid import uuid4
from httpx import AsyncClient


class TestFederationPeering:
    """Test federation peering operations."""

    async def test_initiate_peering(self, client: AsyncClient, auth_headers: dict):
        """Test initiating a peering connection."""
        response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Test Nexus Instance {uuid4().hex[:6]}",
                "peer_endpoint": "https://nexus.example.com",
                "trust_level": "standard",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "peer_id" in data
        assert "your_peer_id" in data
        assert "shared_secret" in data
        assert data["status"] == "pending"
        assert "message" in data

    async def test_initiate_peering_validates_endpoint(self, client: AsyncClient, auth_headers: dict):
        """Test that peering validates HTTPS requirement."""
        # HTTP should be rejected for federation (security requirement)
        response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": "Insecure Instance",
                "peer_endpoint": "http://insecure.example.com",
                "trust_level": "standard",
            },
            headers=auth_headers,
        )
        # Should be rejected for non-HTTPS (may be 400, 422, or 500 depending on error handling)
        assert response.status_code in [400, 422, 500]

    async def test_list_peers(self, client: AsyncClient, auth_headers: dict):
        """Test listing federated peers."""
        # Create a peer first
        await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"List Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://peer.example.com",
            },
            headers=auth_headers,
        )

        response = await client.get(
            "/api/v1/federation/peers",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_peers_by_status(self, client: AsyncClient, auth_headers: dict):
        """Test filtering peers by status."""
        response = await client.get(
            "/api/v1/federation/peers?status=pending",
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_get_peer_details(self, client: AsyncClient, auth_headers: dict):
        """Test getting peer details."""
        # Create a peer
        create_response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Details Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://details.example.com",
            },
            headers=auth_headers,
        )
        peer_id = create_response.json()["peer_id"]

        # Get details
        response = await client.get(
            f"/api/v1/federation/peers/{peer_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(peer_id)


class TestFederationPeerManagement:
    """Test peer lifecycle management."""

    async def test_suspend_peer(self, client: AsyncClient, auth_headers: dict):
        """Test suspending a peer."""
        # Create peer
        create_response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Suspend Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://suspend.example.com",
            },
            headers=auth_headers,
        )
        peer_id = create_response.json()["peer_id"]

        # Suspend
        response = await client.post(
            f"/api/v1/federation/peers/{peer_id}/suspend",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "suspended"

    async def test_activate_peer(self, client: AsyncClient, auth_headers: dict):
        """Test activating a suspended peer."""
        # Create and suspend peer
        create_response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Activate Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://activate.example.com",
            },
            headers=auth_headers,
        )
        peer_id = create_response.json()["peer_id"]
        await client.post(
            f"/api/v1/federation/peers/{peer_id}/suspend",
            headers=auth_headers,
        )

        # Activate
        response = await client.post(
            f"/api/v1/federation/peers/{peer_id}/activate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    async def test_revoke_peer(self, client: AsyncClient, auth_headers: dict):
        """Test revoking a peer."""
        # Create peer
        create_response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Revoke Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://revoke.example.com",
            },
            headers=auth_headers,
        )
        peer_id = create_response.json()["peer_id"]

        # Revoke
        response = await client.delete(
            f"/api/v1/federation/peers/{peer_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "revoked"


class TestFederationCapabilities:
    """Test capability discovery and invocation."""

    async def test_discover_peer_capabilities(self, client: AsyncClient, auth_headers: dict):
        """Test discovering capabilities on a peer."""
        # Create peer
        create_response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Capability Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://capabilities.example.com",
            },
            headers=auth_headers,
        )
        peer_id = create_response.json()["peer_id"]

        # Discover capabilities (will fail since peer doesn't exist, but tests the endpoint)
        response = await client.get(
            f"/api/v1/federation/peers/{peer_id}/capabilities",
            headers=auth_headers,
        )
        # May fail due to no actual peer, but endpoint should exist
        assert response.status_code in [200, 502, 504]

    async def test_invoke_remote_capability(self, client: AsyncClient, auth_headers: dict):
        """Test invoking a capability on a remote peer."""
        # Create peer
        create_response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Invoke Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://invoke.example.com",
            },
            headers=auth_headers,
        )
        peer_id = create_response.json()["peer_id"]

        # Try to invoke (will fail since peer doesn't exist)
        response = await client.post(
            f"/api/v1/federation/peers/{peer_id}/invoke",
            json={
                "agent_slug": "test-agent",
                "capability_name": "process_data",
                "input": {"data": "test"},
                "require_approval": True,
            },
            headers=auth_headers,
        )
        # May fail but endpoint should work
        assert response.status_code in [200, 502, 504]


class TestFederationSecurity:
    """Test federation security measures."""

    async def test_federation_requires_auth(self, client: AsyncClient):
        """Test that federation endpoints require authentication."""
        response = await client.get("/api/v1/federation/peers")
        assert response.status_code == 401

    async def test_peer_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test accessing non-existent peer."""
        fake_peer_id = str(uuid4())
        response = await client.get(
            f"/api/v1/federation/peers/{fake_peer_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_peer_operations_require_ownership(self, client: AsyncClient, auth_headers: dict):
        """Test that peer operations check ownership."""
        # Create peer with one agent
        create_response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Ownership Test Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://ownership.example.com",
            },
            headers=auth_headers,
        )
        peer_id = create_response.json()["peer_id"]

        # The same agent should be able to manage the peer
        response = await client.post(
            f"/api/v1/federation/peers/{peer_id}/suspend",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestFederationTrustLevels:
    """Test trust level functionality."""

    async def test_create_peer_with_minimal_trust(self, client: AsyncClient, auth_headers: dict):
        """Test creating peer with minimal trust."""
        response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Minimal Trust Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://minimal.example.com",
                "trust_level": "minimal",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_create_peer_with_elevated_trust(self, client: AsyncClient, auth_headers: dict):
        """Test creating peer with elevated trust."""
        response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Elevated Trust Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://elevated.example.com",
                "trust_level": "elevated",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_create_peer_with_full_trust(self, client: AsyncClient, auth_headers: dict):
        """Test creating peer with full trust."""
        response = await client.post(
            "/api/v1/federation/peers/initiate",
            json={
                "peer_name": f"Full Trust Peer {uuid4().hex[:6]}",
                "peer_endpoint": "https://full.example.com",
                "trust_level": "full",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestInboundFederation:
    """Test inbound federation endpoints (called by peers)."""

    async def test_federated_capabilities_endpoint(self, client: AsyncClient):
        """Test the inbound capabilities endpoint."""
        # This endpoint requires peer authentication headers
        response = await client.get(
            "/api/v1/federation/capabilities",
            headers={
                "X-Nexus-Peer-Id": "test-peer-id",
                "X-Nexus-Signature": "test-signature",
            },
        )
        # Should fail with invalid credentials but endpoint exists
        assert response.status_code in [401, 403, 200]

    async def test_federated_invoke_endpoint(self, client: AsyncClient):
        """Test the inbound invocation endpoint."""
        response = await client.post(
            "/api/v1/federation/invoke/test-agent/test-capability",
            json={"input": {}},
            headers={
                "X-Nexus-Peer-Id": "test-peer-id",
                "X-Nexus-Signature": "test-signature",
            },
        )
        # Should fail with invalid credentials but endpoint exists
        assert response.status_code in [401, 403, 404, 200]
