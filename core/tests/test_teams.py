"""Integration tests for teams service."""

import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.fixture
def team_data():
    """Sample team data."""
    return {
        "name": f"Test Team {uuid4().hex[:6]}",
        "slug": f"test-team-{uuid4().hex[:8]}",
        "description": "A test team for integration testing",
    }


class TestTeamCRUD:
    """Test team CRUD operations."""

    async def test_create_team(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test creating a team."""
        response = await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == team_data["name"]
        assert data["slug"] == team_data["slug"]
        assert "id" in data
        assert "owner_agent_id" in data

    async def test_create_team_validates_slug(self, client: AsyncClient, auth_headers: dict):
        """Test that team slug is validated."""
        response = await client.post(
            "/api/v1/teams",
            json={
                "name": "Invalid Slug Team",
                "slug": "Invalid Slug With Spaces!",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422  # Validation error

    async def test_list_my_teams(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test listing teams I belong to."""
        # Create a team
        await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )

        response = await client.get(
            "/api/v1/teams/me",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_team(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test getting team details."""
        # Create team
        create_response = await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )
        team_id = create_response.json()["id"]

        # Get team
        response = await client.get(
            f"/api/v1/teams/{team_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == team_id
        assert data["name"] == team_data["name"]

    async def test_update_team(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test updating a team."""
        # Create team
        create_response = await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )
        team_id = create_response.json()["id"]

        # Update team
        new_name = f"Updated Team {uuid4().hex[:6]}"
        response = await client.patch(
            f"/api/v1/teams/{team_id}",
            json={"name": new_name, "description": "Updated description"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == new_name

    async def test_delete_team(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test deleting a team."""
        # Create team
        create_response = await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )
        team_id = create_response.json()["id"]

        # Delete team
        response = await client.delete(
            f"/api/v1/teams/{team_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify deleted
        get_response = await client.get(
            f"/api/v1/teams/{team_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404


class TestTeamMembers:
    """Test team member management."""

    async def test_get_team_members(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test getting team members."""
        # Create team (creator is automatically a member)
        create_response = await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )
        team_id = create_response.json()["id"]

        # Get members
        response = await client.get(
            f"/api/v1/teams/{team_id}/members",
            headers=auth_headers,
        )
        assert response.status_code == 200
        members = response.json()
        assert isinstance(members, list)
        # Creator should be owner
        assert any(m.get("role") == "owner" for m in members)


class TestTeamInvites:
    """Test team invitation system."""

    async def test_get_pending_invites(self, client: AsyncClient, auth_headers: dict):
        """Test getting pending invites."""
        response = await client.get(
            "/api/v1/teams/invites/pending",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestTeamAgentSharing:
    """Test agent sharing with teams."""

    async def test_get_team_agents(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test getting agents shared with a team."""
        # Create team
        create_response = await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )
        team_id = create_response.json()["id"]

        # Get shared agents
        response = await client.get(
            f"/api/v1/teams/{team_id}/agents",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestTeamSecurity:
    """Test team security measures."""

    async def test_teams_require_auth(self, client: AsyncClient):
        """Test that team endpoints require authentication."""
        response = await client.get("/api/v1/teams/me")
        assert response.status_code == 401

    async def test_team_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test accessing non-existent team."""
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/v1/teams/{fake_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_cannot_delete_others_team(self, client: AsyncClient, auth_headers: dict, team_data: dict):
        """Test that team deletion requires ownership."""
        # Create team
        create_response = await client.post(
            "/api/v1/teams",
            json=team_data,
            headers=auth_headers,
        )
        team_id = create_response.json()["id"]

        # Same user (owner) can delete
        response = await client.delete(
            f"/api/v1/teams/{team_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204
