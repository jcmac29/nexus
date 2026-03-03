"""Team collaboration API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.teams.service import TeamService
from nexus.teams.models import TeamRole

router = APIRouter(prefix="/teams", tags=["teams"])


# --- Schemas ---

class CreateTeamRequest(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None


class UpdateTeamRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class TeamResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    owner_agent_id: str
    created_at: str


class MemberResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    slug: str
    role: str
    joined_at: str


class InviteRequest(BaseModel):
    agent_id: str
    role: str = "member"


class InviteResponse(BaseModel):
    id: str
    token: str
    expires_at: str


class ShareAgentRequest(BaseModel):
    agent_id: str
    can_invoke: bool = True
    can_edit: bool = False
    can_manage_keys: bool = False


class UpdateRoleRequest(BaseModel):
    role: str


# --- Routes ---

async def get_team_service(db: AsyncSession = Depends(get_db)) -> TeamService:
    return TeamService(db)


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    data: CreateTeamRequest,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Create a new team."""
    try:
        team = await service.create_team(
            owner_agent_id=agent.id,
            name=data.name,
            slug=data.slug,
            description=data.description,
        )
        return _team_to_response(team)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me")
async def list_my_teams(
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """List teams I belong to."""
    return await service.list_my_teams(agent.id)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: UUID,
    service: TeamService = Depends(get_team_service),
):
    """Get a team by ID."""
    team = await service.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return _team_to_response(team)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: UUID,
    data: UpdateTeamRequest,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Update a team."""
    team = await service.update_team(
        team_id=team_id,
        agent_id=agent.id,
        name=data.name,
        description=data.description,
    )
    if not team:
        raise HTTPException(status_code=404, detail="Team not found or no permission")
    return _team_to_response(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Delete a team."""
    deleted = await service.delete_team(team_id, agent.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Team not found or no permission")


# --- Members ---

@router.get("/{team_id}/members", response_model=list[MemberResponse])
async def get_team_members(
    team_id: UUID,
    service: TeamService = Depends(get_team_service),
):
    """Get team members."""
    members = await service.get_members(team_id)
    return [MemberResponse(**m) for m in members]


@router.patch("/{team_id}/members/{member_agent_id}/role")
async def update_member_role(
    team_id: UUID,
    member_agent_id: UUID,
    data: UpdateRoleRequest,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Update a member's role."""
    try:
        role = TeamRole(data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {data.role}")

    try:
        member = await service.update_member_role(
            team_id, member_agent_id, role, agent.id
        )
        if not member:
            raise HTTPException(status_code=404, detail="Member not found or no permission")
        return {"status": "updated", "role": member.role.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{team_id}/members/{member_agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: UUID,
    member_agent_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Remove a member from team."""
    try:
        removed = await service.remove_member(team_id, member_agent_id, agent.id)
        if not removed:
            raise HTTPException(status_code=404, detail="Member not found or no permission")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Invites ---

@router.post("/{team_id}/invites", response_model=InviteResponse)
async def create_invite(
    team_id: UUID,
    data: InviteRequest,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Create a team invite."""
    try:
        role = TeamRole(data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {data.role}")

    try:
        invite = await service.create_invite(
            team_id=team_id,
            invitee_agent_id=UUID(data.agent_id),
            invited_by=agent.id,
            role=role,
        )
        return InviteResponse(
            id=str(invite.id),
            token=invite.token,
            expires_at=invite.expires_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/invites/pending")
async def get_pending_invites(
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Get my pending team invites."""
    return await service.get_pending_invites(agent.id)


@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Accept a team invite."""
    try:
        member = await service.accept_invite(token, agent.id)
        return {"status": "joined", "team_id": str(member.team_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Shared Agents ---

@router.post("/{team_id}/agents")
async def share_agent(
    team_id: UUID,
    data: ShareAgentRequest,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Share an agent with a team."""
    try:
        team_agent = await service.share_agent_with_team(
            team_id=team_id,
            agent_id=UUID(data.agent_id),
            shared_by=agent.id,
            can_invoke=data.can_invoke,
            can_edit=data.can_edit,
            can_manage_keys=data.can_manage_keys,
        )
        return {"status": "shared", "id": str(team_agent.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{team_id}/agents")
async def get_team_agents(
    team_id: UUID,
    service: TeamService = Depends(get_team_service),
):
    """Get agents shared with a team."""
    return await service.get_team_agents(team_id)


@router.delete("/{team_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_agent(
    team_id: UUID,
    agent_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: TeamService = Depends(get_team_service),
):
    """Remove an agent from team sharing."""
    removed = await service.unshare_agent(team_id, agent_id, agent.id)
    if not removed:
        raise HTTPException(status_code=404, detail="Not found or no permission")


def _team_to_response(team) -> TeamResponse:
    return TeamResponse(
        id=str(team.id),
        name=team.name,
        slug=team.slug,
        description=team.description,
        owner_agent_id=str(team.owner_agent_id),
        created_at=team.created_at.isoformat(),
    )
