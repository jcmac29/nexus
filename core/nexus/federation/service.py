"""Federation service - Manage peer connections and cross-instance communication."""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.federation.models import (
    FederatedPeer,
    FederationRequest,
    PeerStatus,
    TrustLevel,
)


class FederationService:
    """Service for managing federation between Nexus instances."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Peer Management ---

    async def initiate_peering(
        self,
        owner_agent_id: UUID,
        peer_name: str,
        peer_endpoint: str,
        trust_level: TrustLevel = TrustLevel.STANDARD,
    ) -> tuple[FederatedPeer, str]:
        """
        Initiate a peering connection with another Nexus instance.
        Returns the peer record and a secret to share with them.
        """
        # Generate credentials
        our_peer_id = f"peer_{secrets.token_urlsafe(16)}"
        shared_secret = secrets.token_urlsafe(32)

        peer = FederatedPeer(
            name=peer_name,
            endpoint_url=peer_endpoint.rstrip("/"),
            public_key="",  # They'll provide this when accepting
            our_peer_id=our_peer_id,
            our_secret=shared_secret,
            status=PeerStatus.PENDING,
            trust_level=trust_level,
            initiated_by_us=True,
            owner_agent_id=owner_agent_id,
        )

        self.session.add(peer)
        await self.session.commit()
        await self.session.refresh(peer)

        return peer, shared_secret

    async def accept_peering(
        self,
        owner_agent_id: UUID,
        peer_name: str,
        peer_endpoint: str,
        their_peer_id: str,
        their_secret: str,
        trust_level: TrustLevel = TrustLevel.STANDARD,
    ) -> FederatedPeer:
        """Accept an incoming peering request."""
        # Generate our credentials for them
        our_peer_id = f"peer_{secrets.token_urlsafe(16)}"
        our_secret = secrets.token_urlsafe(32)

        peer = FederatedPeer(
            name=peer_name,
            endpoint_url=peer_endpoint.rstrip("/"),
            public_key="",
            our_peer_id=their_peer_id,
            our_secret=their_secret,
            status=PeerStatus.ACTIVE,
            trust_level=trust_level,
            initiated_by_us=False,
            owner_agent_id=owner_agent_id,
        )

        self.session.add(peer)
        await self.session.commit()
        await self.session.refresh(peer)

        # TODO: Call back to peer to complete handshake
        return peer

    async def get_peer(self, peer_id: UUID) -> FederatedPeer | None:
        """Get a peer by ID."""
        result = await self.session.execute(
            select(FederatedPeer).where(FederatedPeer.id == peer_id)
        )
        return result.scalar_one_or_none()

    async def list_peers(
        self,
        owner_agent_id: UUID,
        status: PeerStatus | None = None,
    ) -> list[FederatedPeer]:
        """List all peers for an agent."""
        query = select(FederatedPeer).where(
            FederatedPeer.owner_agent_id == owner_agent_id
        )
        if status:
            query = query.where(FederatedPeer.status == status)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_peer_status(
        self,
        peer_id: UUID,
        status: PeerStatus,
    ) -> FederatedPeer | None:
        """Update peer status."""
        peer = await self.get_peer(peer_id)
        if not peer:
            return None

        peer.status = status
        await self.session.commit()
        await self.session.refresh(peer)
        return peer

    # --- Cross-Instance Communication ---

    async def discover_remote_capabilities(
        self,
        peer_id: UUID,
        query: str | None = None,
    ) -> list[dict]:
        """Discover capabilities on a remote peer."""
        peer = await self.get_peer(peer_id)
        if not peer or peer.status != PeerStatus.ACTIVE:
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self._build_auth_headers(peer)
                url = f"{peer.endpoint_url}/api/v1/federation/capabilities"
                if query:
                    url += f"?query={query}"

                response = await client.get(url, headers=headers)
                response.raise_for_status()

                # Log the request
                await self._log_request(
                    peer_id=peer_id,
                    direction="outbound",
                    request_type="discover",
                    status="completed",
                    request_summary={"query": query},
                    response_summary={"count": len(response.json())},
                )

                return response.json()

        except Exception as e:
            await self._log_request(
                peer_id=peer_id,
                direction="outbound",
                request_type="discover",
                status="failed",
                request_summary={"query": query, "error": str(e)},
            )
            return []

    async def invoke_remote_capability(
        self,
        peer_id: UUID,
        agent_slug: str,
        capability_name: str,
        input_data: dict,
        require_approval: bool = True,
    ) -> dict:
        """Invoke a capability on a remote peer's agent."""
        peer = await self.get_peer(peer_id)
        if not peer or peer.status != PeerStatus.ACTIVE:
            return {"error": "Peer not active"}

        if peer.trust_level == TrustLevel.MINIMAL:
            return {"error": "Trust level too low for invocations"}

        # Create pending request if approval required
        request_log = await self._log_request(
            peer_id=peer_id,
            direction="outbound",
            request_type="invoke",
            capability_name=capability_name,
            status="pending" if require_approval else "approved",
            request_summary={
                "agent": agent_slug,
                "capability": capability_name,
                "input_keys": list(input_data.keys()),
            },
        )

        if require_approval:
            return {
                "status": "pending_approval",
                "request_id": str(request_log.id),
                "message": "Request requires approval before execution",
            }

        # Execute the remote invocation
        return await self._execute_remote_invocation(
            peer, agent_slug, capability_name, input_data, request_log
        )

    async def _execute_remote_invocation(
        self,
        peer: FederatedPeer,
        agent_slug: str,
        capability_name: str,
        input_data: dict,
        request_log: FederationRequest,
    ) -> dict:
        """Actually execute the remote invocation."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = self._build_auth_headers(peer)
                url = f"{peer.endpoint_url}/api/v1/federation/invoke/{agent_slug}/{capability_name}"

                response = await client.post(
                    url,
                    headers=headers,
                    json={"input": input_data},
                )
                response.raise_for_status()
                result = response.json()

                # Update log
                request_log.status = "completed"
                request_log.completed_at = datetime.now(timezone.utc)
                request_log.response_summary = {
                    "status": result.get("status"),
                    "has_output": "output" in result,
                }
                await self.session.commit()

                # Update peer stats
                peer.requests_sent += 1
                peer.last_seen_at = datetime.now(timezone.utc)
                await self.session.commit()

                return result

        except Exception as e:
            request_log.status = "failed"
            request_log.response_summary = {"error": str(e)}
            await self.session.commit()
            return {"error": str(e)}

    # --- Inbound Request Handling ---

    async def handle_inbound_discovery(
        self,
        peer_id: str,
        signature: str,
    ) -> list[dict]:
        """Handle discovery request from a peer."""
        peer = await self._verify_peer_request(peer_id, signature)
        if not peer:
            return []

        # Return only published capabilities
        # TODO: Query actual published capabilities
        await self._log_request(
            peer_id=peer.id,
            direction="inbound",
            request_type="discover",
            status="completed",
        )

        peer.requests_received += 1
        peer.last_seen_at = datetime.now(timezone.utc)
        await self.session.commit()

        return []  # Return published capabilities

    async def handle_inbound_invocation(
        self,
        peer_id: str,
        signature: str,
        agent_slug: str,
        capability_name: str,
        input_data: dict,
    ) -> dict:
        """Handle invocation request from a peer."""
        peer = await self._verify_peer_request(peer_id, signature)
        if not peer:
            return {"error": "Invalid peer credentials"}

        if peer.trust_level == TrustLevel.MINIMAL:
            return {"error": "Trust level too low"}

        # Log inbound request
        request_log = await self._log_request(
            peer_id=peer.id,
            direction="inbound",
            request_type="invoke",
            capability_name=capability_name,
            status="pending",
            request_summary={
                "agent": agent_slug,
                "capability": capability_name,
                "input_keys": list(input_data.keys()),
            },
        )

        # TODO: Check if capability requires approval
        # TODO: Route to actual capability handler

        peer.requests_received += 1
        peer.last_seen_at = datetime.now(timezone.utc)
        await self.session.commit()

        return {
            "status": "pending",
            "request_id": str(request_log.id),
        }

    # --- Helper Methods ---

    def _build_auth_headers(self, peer: FederatedPeer) -> dict:
        """Build authentication headers for peer requests."""
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        message = f"{peer.our_peer_id}:{timestamp}"
        signature = hmac.new(
            peer.our_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-Nexus-Peer-ID": peer.our_peer_id,
            "X-Nexus-Timestamp": timestamp,
            "X-Nexus-Signature": signature,
        }

    async def _verify_peer_request(
        self,
        peer_id: str,
        signature: str,
    ) -> FederatedPeer | None:
        """Verify an incoming peer request."""
        result = await self.session.execute(
            select(FederatedPeer).where(
                FederatedPeer.our_peer_id == peer_id,
                FederatedPeer.status == PeerStatus.ACTIVE,
            )
        )
        peer = result.scalar_one_or_none()

        if not peer:
            return None

        # TODO: Verify signature with timestamp
        return peer

    async def _log_request(
        self,
        peer_id: UUID,
        direction: str,
        request_type: str,
        status: str = "pending",
        capability_name: str | None = None,
        request_summary: dict | None = None,
        response_summary: dict | None = None,
    ) -> FederationRequest:
        """Log a federation request for audit."""
        log = FederationRequest(
            peer_id=peer_id,
            direction=direction,
            request_type=request_type,
            capability_name=capability_name,
            status=status,
            request_summary=request_summary or {},
            response_summary=response_summary or {},
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log
