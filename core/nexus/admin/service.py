"""Admin service for dashboard operations."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.admin.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from nexus.admin.models import AdminRole, AdminUser
from nexus.admin.schemas import (
    ActivityItem,
    AgentSummary,
    DashboardStats,
    InstanceSettings,
    LoginResponse,
    MemorySearchResult,
    TeamSummary,
)
from nexus.config import get_settings


class AdminService:
    """Service for admin operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate(self, email: str, password: str) -> LoginResponse | None:
        """Authenticate admin user and return tokens."""
        stmt = select(AdminUser).where(
            AdminUser.email == email,
            AdminUser.is_active == True,
        )
        result = await self.db.execute(stmt)
        admin = result.scalar_one_or_none()

        if not admin or not verify_password(password, admin.password_hash):
            return None

        # Update last login
        admin.last_login = datetime.now(timezone.utc)
        await self.db.commit()

        settings = get_settings()
        access_token = create_access_token(admin.id, admin.account_id, admin.role)
        refresh_token = create_refresh_token(admin.id)

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.admin_token_expire_hours * 3600,
        )

    async def refresh_tokens(self, refresh_token: str) -> LoginResponse | None:
        """Refresh access token using refresh token."""
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            return None

        admin_id = payload.get("sub")
        stmt = select(AdminUser).where(
            AdminUser.id == UUID(admin_id),
            AdminUser.is_active == True,
        )
        result = await self.db.execute(stmt)
        admin = result.scalar_one_or_none()

        if not admin:
            return None

        settings = get_settings()
        access_token = create_access_token(admin.id, admin.account_id, admin.role)
        new_refresh_token = create_refresh_token(admin.id)

        return LoginResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=settings.admin_token_expire_hours * 3600,
        )

    async def create_admin(
        self,
        email: str,
        password: str,
        name: str,
        role: AdminRole = AdminRole.ADMIN,
        account_id: UUID | None = None,
    ) -> AdminUser:
        """Create a new admin user."""
        admin = AdminUser(
            email=email,
            password_hash=hash_password(password),
            name=name,
            role=role,
            account_id=account_id,
        )
        self.db.add(admin)
        await self.db.commit()
        await self.db.refresh(admin)
        return admin

    async def get_dashboard_stats(self, account_id: UUID | None = None) -> DashboardStats:
        """Get dashboard statistics."""
        from nexus.discovery.models import Capability
        from nexus.identity.models import Agent
        from nexus.memory.models import Memory
        from nexus.teams.models import Team

        # Build base queries with optional account filtering
        agent_query = select(func.count()).select_from(Agent)
        active_agent_query = select(func.count()).select_from(Agent).where(
            Agent.status == "active"
        )
        memory_query = select(func.count()).select_from(Memory)
        team_query = select(func.count()).select_from(Team)
        capability_query = select(func.count()).select_from(Capability)

        if account_id:
            agent_query = agent_query.where(Agent.account_id == account_id)
            active_agent_query = active_agent_query.where(Agent.account_id == account_id)
            memory_query = memory_query.where(Memory.account_id == account_id)
            # Teams don't have account_id directly, join through owner agent
            team_query = (
                select(func.count())
                .select_from(Team)
                .join(Agent, Team.owner_agent_id == Agent.id)
                .where(Agent.account_id == account_id)
            )
            capability_query = capability_query.where(Capability.account_id == account_id)

        total_agents = (await self.db.execute(agent_query)).scalar() or 0
        active_agents = (await self.db.execute(active_agent_query)).scalar() or 0
        total_memories = (await self.db.execute(memory_query)).scalar() or 0
        total_teams = (await self.db.execute(team_query)).scalar() or 0
        total_capabilities = (await self.db.execute(capability_query)).scalar() or 0

        # TODO: Add actual analytics queries when analytics module is integrated
        return DashboardStats(
            total_agents=total_agents,
            active_agents=active_agents,
            total_memories=total_memories,
            total_teams=total_teams,
            total_capabilities=total_capabilities,
            api_calls_today=0,
            api_calls_this_month=0,
        )

    async def list_agents(
        self,
        account_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> tuple[list[AgentSummary], int]:
        """List agents with pagination."""
        from nexus.identity.models import Agent

        query = select(Agent)
        count_query = select(func.count()).select_from(Agent)

        if account_id:
            query = query.where(Agent.account_id == account_id)
            count_query = count_query.where(Agent.account_id == account_id)

        if search:
            search_filter = Agent.name.ilike(f"%{search}%") | Agent.slug.ilike(
                f"%{search}%"
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(Agent.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        agents = result.scalars().all()

        summaries = [
            AgentSummary(
                id=agent.id,
                name=agent.name,
                slug=agent.slug,
                status=agent.status,
                capabilities_count=0,  # TODO: Add subquery
                memories_count=0,  # TODO: Add subquery
                created_at=agent.created_at,
                last_seen=getattr(agent, "last_seen", None),
            )
            for agent in agents
        ]

        return summaries, total

    async def list_teams(
        self,
        account_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TeamSummary], int]:
        """List teams with pagination."""
        from nexus.identity.models import Agent
        from nexus.teams.models import Team, TeamMember

        query = select(Team)
        count_query = select(func.count()).select_from(Team)

        if account_id:
            query = (
                query.join(Agent, Team.owner_agent_id == Agent.id)
                .where(Agent.account_id == account_id)
            )
            count_query = (
                count_query.join(Agent, Team.owner_agent_id == Agent.id)
                .where(Agent.account_id == account_id)
            )

        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(Team.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        teams = result.scalars().all()

        summaries = []
        for team in teams:
            # Get member count
            member_count_query = (
                select(func.count())
                .select_from(TeamMember)
                .where(TeamMember.team_id == team.id)
            )
            member_count = (await self.db.execute(member_count_query)).scalar() or 0

            summaries.append(
                TeamSummary(
                    id=team.id,
                    name=team.name,
                    slug=team.slug,
                    member_count=member_count,
                    created_at=team.created_at,
                )
            )

        return summaries, total

    async def search_memories(
        self,
        query: str,
        account_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MemorySearchResult], int]:
        """Search memories across agents."""
        from nexus.identity.models import Agent
        from nexus.memory.models import Memory

        search_query = select(Memory, Agent.name.label("agent_name")).join(
            Agent, Memory.agent_id == Agent.id
        )
        count_query = select(func.count()).select_from(Memory)

        # Text search filter
        search_filter = Memory.content.ilike(f"%{query}%")
        search_query = search_query.where(search_filter)
        count_query = count_query.where(search_filter)

        if account_id:
            search_query = search_query.where(Memory.account_id == account_id)
            count_query = count_query.where(Memory.account_id == account_id)

        total = (await self.db.execute(count_query)).scalar() or 0

        search_query = search_query.order_by(Memory.created_at.desc())
        search_query = search_query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(search_query)
        rows = result.all()

        memories = [
            MemorySearchResult(
                id=memory.id,
                agent_id=memory.agent_id,
                agent_name=agent_name,
                content=memory.content[:500],  # Truncate for listing
                memory_type=memory.memory_type,
                created_at=memory.created_at,
            )
            for memory, agent_name in rows
        ]

        return memories, total

    async def get_recent_activity(
        self,
        account_id: UUID | None = None,
        limit: int = 50,
    ) -> list[ActivityItem]:
        """Get recent activity feed."""
        from nexus.identity.models import Agent
        from nexus.memory.models import Memory

        # Get recent agent creations
        agent_query = select(Agent).order_by(Agent.created_at.desc()).limit(limit)
        if account_id:
            agent_query = agent_query.where(Agent.account_id == account_id)

        agents_result = await self.db.execute(agent_query)
        recent_agents = agents_result.scalars().all()

        # Get recent memories
        memory_query = (
            select(Memory, Agent.name.label("agent_name"))
            .join(Agent, Memory.agent_id == Agent.id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        if account_id:
            memory_query = memory_query.where(Memory.account_id == account_id)

        memories_result = await self.db.execute(memory_query)
        recent_memories = memories_result.all()

        # Combine and sort activities
        activities = []

        for agent in recent_agents:
            activities.append(
                ActivityItem(
                    id=agent.id,
                    type="agent_created",
                    description=f"Agent '{agent.name}' was registered",
                    agent_id=agent.id,
                    agent_name=agent.name,
                    timestamp=agent.created_at,
                )
            )

        for memory, agent_name in recent_memories:
            activities.append(
                ActivityItem(
                    id=memory.id,
                    type="memory_stored",
                    description=f"Memory stored by '{agent_name}'",
                    agent_id=memory.agent_id,
                    agent_name=agent_name,
                    timestamp=memory.created_at,
                )
            )

        # Sort by timestamp descending and limit
        activities.sort(key=lambda x: x.timestamp, reverse=True)
        return activities[:limit]

    async def get_instance_settings(self) -> InstanceSettings:
        """Get instance-level settings."""
        settings = get_settings()
        return InstanceSettings(
            instance_name=settings.app_name,
            allow_registration=True,  # TODO: Add to config
            require_email_verification=False,  # TODO: Add to config
            default_rate_limit=settings.rate_limit_requests,
            features={
                "graph_memory": settings.feature_graph_memory,
                "webhooks": settings.feature_webhooks,
                "federation": settings.feature_federation,
                "marketplace": settings.feature_marketplace,
            },
        )

    async def update_instance_settings(
        self, updates: dict
    ) -> InstanceSettings:
        """Update instance-level settings."""
        # TODO: Persist settings to database
        # For now, just return current settings
        return await self.get_instance_settings()

    async def get_federation_peers(
        self,
        account_id: UUID | None = None,
    ) -> list[dict]:
        """Get federation peers."""
        try:
            from nexus.federation.models import FederationPeer

            query = select(FederationPeer).order_by(FederationPeer.created_at.desc())

            result = await self.db.execute(query)
            peers = result.scalars().all()

            return [
                {
                    "id": str(peer.id),
                    "name": peer.name,
                    "url": peer.url,
                    "trust_level": peer.trust_level.value if hasattr(peer.trust_level, 'value') else str(peer.trust_level),
                    "status": peer.status.value if hasattr(peer.status, 'value') else str(peer.status),
                    "last_seen": peer.last_seen.isoformat() if peer.last_seen else None,
                }
                for peer in peers
            ]
        except Exception:
            # Federation module may not have tables created yet
            return []

    async def get_audit_logs(
        self,
        account_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get audit logs."""
        try:
            from nexus.audit.models import AuditLog

            query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)

            if account_id:
                query = query.where(AuditLog.account_id == account_id)

            result = await self.db.execute(query)
            logs = result.scalars().all()

            return [
                {
                    "id": str(log.id),
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": str(log.resource_id) if log.resource_id else None,
                    "agent_id": str(log.agent_id) if log.agent_id else None,
                    "timestamp": log.created_at.isoformat(),
                    "details": log.details or {},
                }
                for log in logs
            ]
        except Exception:
            # Audit module may not have tables created yet
            return []

    # =========================================================================
    # Agent CRUD Operations
    # =========================================================================

    async def create_agent(
        self,
        name: str,
        slug: str,
        description: str | None = None,
        status: str = "active",
        account_id: UUID | None = None,
    ) -> AgentSummary:
        """Create a new agent."""
        from nexus.identity.models import Agent, AgentStatus

        agent = Agent(
            name=name,
            slug=slug,
            description=description,
            status=AgentStatus(status),
            account_id=account_id,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)

        return AgentSummary(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            status=agent.status.value,
            capabilities_count=0,
            memories_count=0,
            created_at=agent.created_at,
            last_seen=None,
        )

    async def get_agent(self, agent_id: UUID) -> dict | None:
        """Get agent details by ID."""
        from nexus.discovery.models import Capability
        from nexus.identity.models import Agent, APIKey
        from nexus.memory.models import Memory

        stmt = select(Agent).where(Agent.id == agent_id)
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()

        if not agent:
            return None

        # Get counts
        caps_count = (
            await self.db.execute(
                select(func.count()).select_from(Capability).where(Capability.agent_id == agent_id)
            )
        ).scalar() or 0

        mems_count = (
            await self.db.execute(
                select(func.count()).select_from(Memory).where(Memory.agent_id == agent_id)
            )
        ).scalar() or 0

        # Get API key prefix if exists
        key_result = await self.db.execute(
            select(APIKey.key_prefix).where(APIKey.agent_id == agent_id).limit(1)
        )
        key_prefix = key_result.scalar_one_or_none()

        return {
            "id": agent.id,
            "name": agent.name,
            "slug": agent.slug,
            "description": agent.description,
            "status": agent.status.value if hasattr(agent.status, 'value') else str(agent.status),
            "capabilities_count": caps_count,
            "memories_count": mems_count,
            "created_at": agent.created_at,
            "last_seen": None,
            "api_key_prefix": key_prefix,
        }

    async def update_agent(
        self,
        agent_id: UUID,
        updates: dict,
    ) -> dict | None:
        """Update an agent."""
        from nexus.identity.models import Agent, AgentStatus

        stmt = select(Agent).where(Agent.id == agent_id)
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()

        if not agent:
            return None

        # SECURITY: Whitelist of allowed fields to prevent mass assignment
        allowed_fields = {"name", "slug", "description", "status"}

        for key, value in updates.items():
            if value is not None and key in allowed_fields:
                if key == "status":
                    setattr(agent, key, AgentStatus(value))
                else:
                    setattr(agent, key, value)

        await self.db.commit()
        await self.db.refresh(agent)

        return await self.get_agent(agent_id)

    async def delete_agent(self, agent_id: UUID) -> bool:
        """Delete an agent."""
        from nexus.identity.models import Agent

        stmt = select(Agent).where(Agent.id == agent_id)
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()

        if not agent:
            return False

        await self.db.delete(agent)
        await self.db.commit()
        return True

    # =========================================================================
    # Team CRUD Operations
    # =========================================================================

    async def create_team(
        self,
        name: str,
        slug: str,
        owner_agent_id: UUID,
        description: str | None = None,
    ) -> TeamSummary:
        """Create a new team."""
        from nexus.teams.models import Team, TeamMember, TeamRole

        team = Team(
            name=name,
            slug=slug,
            description=description,
            owner_agent_id=owner_agent_id,
        )
        self.db.add(team)
        await self.db.flush()

        # Add owner as team member
        member = TeamMember(
            team_id=team.id,
            agent_id=owner_agent_id,
            role=TeamRole.OWNER,
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(team)

        return TeamSummary(
            id=team.id,
            name=team.name,
            slug=team.slug,
            member_count=1,
            created_at=team.created_at,
        )

    async def get_team(self, team_id: UUID) -> dict | None:
        """Get team details by ID."""
        from nexus.identity.models import Agent
        from nexus.teams.models import Team, TeamMember

        stmt = select(Team).where(Team.id == team_id)
        result = await self.db.execute(stmt)
        team = result.scalar_one_or_none()

        if not team:
            return None

        # Get members with agent info
        members_stmt = (
            select(TeamMember, Agent.name.label("agent_name"), Agent.slug.label("agent_slug"))
            .join(Agent, TeamMember.agent_id == Agent.id)
            .where(TeamMember.team_id == team_id)
        )
        members_result = await self.db.execute(members_stmt)
        members = [
            {
                "agent_id": str(m.agent_id),
                "agent_name": agent_name,
                "agent_slug": agent_slug,
                "role": m.role.value,
                "joined_at": m.joined_at.isoformat(),
            }
            for m, agent_name, agent_slug in members_result.all()
        ]

        return {
            "id": team.id,
            "name": team.name,
            "slug": team.slug,
            "description": team.description,
            "owner_agent_id": team.owner_agent_id,
            "member_count": len(members),
            "members": members,
            "created_at": team.created_at,
        }

    async def update_team(
        self,
        team_id: UUID,
        updates: dict,
    ) -> dict | None:
        """Update a team."""
        from nexus.teams.models import Team

        stmt = select(Team).where(Team.id == team_id)
        result = await self.db.execute(stmt)
        team = result.scalar_one_or_none()

        if not team:
            return None

        # SECURITY: Whitelist of allowed fields to prevent mass assignment
        allowed_fields = {"name", "slug", "description"}

        for key, value in updates.items():
            if value is not None and key in allowed_fields:
                setattr(team, key, value)

        await self.db.commit()
        await self.db.refresh(team)

        return await self.get_team(team_id)

    async def delete_team(self, team_id: UUID) -> bool:
        """Delete a team."""
        from nexus.teams.models import Team

        stmt = select(Team).where(Team.id == team_id)
        result = await self.db.execute(stmt)
        team = result.scalar_one_or_none()

        if not team:
            return False

        await self.db.delete(team)
        await self.db.commit()
        return True

    async def add_team_member(
        self,
        team_id: UUID,
        agent_id: UUID,
        role: str = "member",
    ) -> bool:
        """Add a member to a team."""
        from nexus.teams.models import TeamMember, TeamRole

        # Check if already a member
        stmt = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.agent_id == agent_id,
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            return False  # Already a member

        member = TeamMember(
            team_id=team_id,
            agent_id=agent_id,
            role=TeamRole(role),
        )
        self.db.add(member)
        await self.db.commit()
        return True

    async def remove_team_member(
        self,
        team_id: UUID,
        agent_id: UUID,
    ) -> bool:
        """Remove a member from a team."""
        from nexus.teams.models import TeamMember

        stmt = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.agent_id == agent_id,
        )
        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()

        if not member:
            return False

        await self.db.delete(member)
        await self.db.commit()
        return True

    # =========================================================================
    # Memory Operations
    # =========================================================================

    async def delete_memory(self, memory_id: UUID) -> bool:
        """Delete a memory."""
        from nexus.memory.models import Memory

        stmt = select(Memory).where(Memory.id == memory_id)
        result = await self.db.execute(stmt)
        memory = result.scalar_one_or_none()

        if not memory:
            return False

        await self.db.delete(memory)
        await self.db.commit()
        return True

    async def bulk_delete_memories(self, memory_ids: list[UUID]) -> int:
        """Delete multiple memories. Returns count deleted."""
        from nexus.memory.models import Memory

        deleted = 0
        for memory_id in memory_ids:
            if await self.delete_memory(memory_id):
                deleted += 1

        return deleted
