"""Team collaboration service."""

import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.teams.models import Team, TeamMember, TeamInvite, TeamAgent, TeamRole
from nexus.identity.models import Agent


class TeamService:
    """Service for team management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Team CRUD ---

    async def create_team(
        self,
        owner_agent_id: UUID,
        name: str,
        slug: str,
        description: str | None = None,
    ) -> Team:
        """Create a new team."""
        # Check slug uniqueness
        existing = await self.db.execute(
            select(Team).where(Team.slug == slug)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Team slug '{slug}' already exists")

        team = Team(
            name=name,
            slug=slug,
            description=description,
            owner_agent_id=owner_agent_id,
        )
        self.db.add(team)
        await self.db.flush()

        # Add owner as member
        member = TeamMember(
            team_id=team.id,
            agent_id=owner_agent_id,
            role=TeamRole.OWNER,
        )
        self.db.add(member)
        await self.db.flush()

        return team

    async def get_team(self, team_id: UUID) -> Team | None:
        """Get a team by ID."""
        result = await self.db.execute(
            select(Team).where(Team.id == team_id)
        )
        return result.scalar_one_or_none()

    async def get_team_by_slug(self, slug: str) -> Team | None:
        """Get a team by slug."""
        result = await self.db.execute(
            select(Team).where(Team.slug == slug)
        )
        return result.scalar_one_or_none()

    async def update_team(
        self,
        team_id: UUID,
        agent_id: UUID,
        **updates,
    ) -> Team | None:
        """Update a team (requires admin/owner)."""
        if not await self._has_role(team_id, agent_id, [TeamRole.OWNER, TeamRole.ADMIN]):
            return None

        result = await self.db.execute(
            select(Team).where(Team.id == team_id)
        )
        team = result.scalar_one_or_none()
        if not team:
            return None

        for key, value in updates.items():
            if hasattr(team, key) and value is not None:
                setattr(team, key, value)

        team.updated_at = datetime.now(timezone.utc)
        return team

    async def delete_team(self, team_id: UUID, agent_id: UUID) -> bool:
        """Delete a team (owner only)."""
        if not await self._has_role(team_id, agent_id, [TeamRole.OWNER]):
            return False

        result = await self.db.execute(
            select(Team).where(Team.id == team_id)
        )
        team = result.scalar_one_or_none()
        if team:
            await self.db.delete(team)
            return True
        return False

    async def list_my_teams(self, agent_id: UUID) -> list[dict[str, Any]]:
        """List teams an agent belongs to."""
        result = await self.db.execute(
            select(Team, TeamMember)
            .join(TeamMember, Team.id == TeamMember.team_id)
            .where(TeamMember.agent_id == agent_id)
            .order_by(Team.name)
        )
        return [
            {
                "id": str(team.id),
                "name": team.name,
                "slug": team.slug,
                "description": team.description,
                "role": member.role.value,
                "joined_at": member.joined_at.isoformat(),
            }
            for team, member in result.all()
        ]

    # --- Members ---

    async def get_members(self, team_id: UUID) -> list[dict[str, Any]]:
        """Get team members."""
        result = await self.db.execute(
            select(TeamMember, Agent)
            .join(Agent, TeamMember.agent_id == Agent.id)
            .where(TeamMember.team_id == team_id)
            .order_by(TeamMember.role, Agent.name)
        )
        return [
            {
                "id": str(member.id),
                "agent_id": str(agent.id),
                "name": agent.name,
                "slug": agent.slug,
                "role": member.role.value,
                "joined_at": member.joined_at.isoformat(),
            }
            for member, agent in result.all()
        ]

    async def update_member_role(
        self,
        team_id: UUID,
        member_agent_id: UUID,
        new_role: TeamRole,
        requester_agent_id: UUID,
    ) -> TeamMember | None:
        """Update a member's role (admin/owner only)."""
        if not await self._has_role(team_id, requester_agent_id, [TeamRole.OWNER, TeamRole.ADMIN]):
            return None

        # Can't change owner role
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == member_agent_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return None
        if member.role == TeamRole.OWNER:
            raise ValueError("Cannot change owner's role")

        member.role = new_role
        return member

    async def remove_member(
        self,
        team_id: UUID,
        member_agent_id: UUID,
        requester_agent_id: UUID,
    ) -> bool:
        """Remove a member from team."""
        # Self-removal is always allowed
        if member_agent_id != requester_agent_id:
            if not await self._has_role(team_id, requester_agent_id, [TeamRole.OWNER, TeamRole.ADMIN]):
                return False

        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == member_agent_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        if member.role == TeamRole.OWNER:
            raise ValueError("Cannot remove team owner")

        await self.db.delete(member)
        return True

    # --- Invites ---

    async def create_invite(
        self,
        team_id: UUID,
        invitee_agent_id: UUID,
        invited_by: UUID,
        role: TeamRole = TeamRole.MEMBER,
        expires_in_days: int = 7,
    ) -> TeamInvite:
        """Create a team invite."""
        if not await self._has_role(team_id, invited_by, [TeamRole.OWNER, TeamRole.ADMIN]):
            raise ValueError("No permission to invite")

        # Check if already a member
        existing_member = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == invitee_agent_id,
            )
        )
        if existing_member.scalar_one_or_none():
            raise ValueError("Agent is already a team member")

        token = secrets.token_urlsafe(48)
        invite = TeamInvite(
            team_id=team_id,
            invitee_agent_id=invitee_agent_id,
            invited_by=invited_by,
            role=role,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        )
        self.db.add(invite)
        await self.db.flush()
        return invite

    async def accept_invite(self, token: str, agent_id: UUID) -> TeamMember:
        """Accept a team invite."""
        result = await self.db.execute(
            select(TeamInvite).where(TeamInvite.token == token)
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise ValueError("Invalid invite token")
        if invite.invitee_agent_id != agent_id:
            raise ValueError("Invite not for this agent")
        if invite.expires_at < datetime.now(timezone.utc):
            raise ValueError("Invite has expired")

        # Create membership
        member = TeamMember(
            team_id=invite.team_id,
            agent_id=agent_id,
            role=invite.role,
            invited_by=invite.invited_by,
        )
        self.db.add(member)

        # Delete invite
        await self.db.delete(invite)
        await self.db.flush()

        return member

    async def get_pending_invites(self, agent_id: UUID) -> list[dict[str, Any]]:
        """Get pending invites for an agent."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(TeamInvite, Team, Agent)
            .join(Team, TeamInvite.team_id == Team.id)
            .join(Agent, TeamInvite.invited_by == Agent.id)
            .where(
                TeamInvite.invitee_agent_id == agent_id,
                TeamInvite.expires_at > now,
            )
        )
        return [
            {
                "id": str(invite.id),
                "team_id": str(team.id),
                "team_name": team.name,
                "invited_by_name": agent.name,
                "role": invite.role.value,
                "token": invite.token,
                "expires_at": invite.expires_at.isoformat(),
            }
            for invite, team, agent in result.all()
        ]

    # --- Shared Agents ---

    async def share_agent_with_team(
        self,
        team_id: UUID,
        agent_id: UUID,
        shared_by: UUID,
        can_invoke: bool = True,
        can_edit: bool = False,
        can_manage_keys: bool = False,
    ) -> TeamAgent:
        """Share an agent with a team."""
        if not await self._has_role(team_id, shared_by, [TeamRole.OWNER, TeamRole.ADMIN, TeamRole.MEMBER]):
            raise ValueError("No permission to share")

        # Check if already shared
        existing = await self.db.execute(
            select(TeamAgent).where(
                TeamAgent.team_id == team_id,
                TeamAgent.agent_id == agent_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Agent already shared with team")

        team_agent = TeamAgent(
            team_id=team_id,
            agent_id=agent_id,
            shared_by=shared_by,
            can_invoke=can_invoke,
            can_edit=can_edit,
            can_manage_keys=can_manage_keys,
        )
        self.db.add(team_agent)
        await self.db.flush()
        return team_agent

    async def get_team_agents(self, team_id: UUID) -> list[dict[str, Any]]:
        """Get agents shared with a team."""
        result = await self.db.execute(
            select(TeamAgent, Agent)
            .join(Agent, TeamAgent.agent_id == Agent.id)
            .where(TeamAgent.team_id == team_id)
        )
        return [
            {
                "id": str(ta.id),
                "agent_id": str(agent.id),
                "agent_name": agent.name,
                "agent_slug": agent.slug,
                "can_invoke": ta.can_invoke,
                "can_edit": ta.can_edit,
                "can_manage_keys": ta.can_manage_keys,
                "shared_at": ta.shared_at.isoformat(),
            }
            for ta, agent in result.all()
        ]

    async def unshare_agent(
        self,
        team_id: UUID,
        agent_id: UUID,
        requester_id: UUID,
    ) -> bool:
        """Remove an agent from team sharing."""
        if not await self._has_role(team_id, requester_id, [TeamRole.OWNER, TeamRole.ADMIN]):
            return False

        result = await self.db.execute(
            select(TeamAgent).where(
                TeamAgent.team_id == team_id,
                TeamAgent.agent_id == agent_id,
            )
        )
        team_agent = result.scalar_one_or_none()
        if team_agent:
            await self.db.delete(team_agent)
            return True
        return False

    # --- Helpers ---

    async def _has_role(
        self,
        team_id: UUID,
        agent_id: UUID,
        roles: list[TeamRole],
    ) -> bool:
        """Check if agent has one of the specified roles."""
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == agent_id,
            )
        )
        member = result.scalar_one_or_none()
        return member is not None and member.role in roles

    async def get_member_role(self, team_id: UUID, agent_id: UUID) -> TeamRole | None:
        """Get an agent's role in a team."""
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == agent_id,
            )
        )
        member = result.scalar_one_or_none()
        return member.role if member else None
