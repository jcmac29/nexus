"""Federation service - Manage peer connections and cross-instance communication."""

import hashlib
import hmac
import ipaddress
import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse
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

logger = logging.getLogger(__name__)


def _validate_peer_endpoint(url: str) -> None:
    """
    Validate peer endpoint URL to prevent SSRF attacks.

    Raises ValueError if URL is unsafe.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")

    # Must be https for federation (security requirement)
    if parsed.scheme != "https":
        raise ValueError("Federation endpoints must use HTTPS")

    # Must have a hostname
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")

    hostname = parsed.hostname.lower()

    # Block localhost and common local hostnames
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "metadata.google.internal", "169.254.169.254",
        "metadata.internal", "kubernetes.default",
    }
    if hostname in blocked_hosts:
        raise ValueError("Federation endpoint cannot point to localhost or internal services")

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Federation endpoint cannot point to private or reserved IP addresses")
    except ValueError:
        # Not an IP address, it's a hostname - check for suspicious patterns
        pass

    # Block internal-looking hostnames
    if any(internal in hostname for internal in [".internal", ".local", ".localhost", ".svc.cluster"]):
        raise ValueError("Federation endpoint cannot point to internal services")


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
        # SECURITY: Validate peer endpoint to prevent SSRF
        _validate_peer_endpoint(peer_endpoint)

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
        # SECURITY: Validate peer endpoint to prevent SSRF
        _validate_peer_endpoint(peer_endpoint)

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

        # Call back to peer to complete handshake
        await self._complete_handshake(peer, our_peer_id, our_secret)
        return peer

    async def _complete_handshake(
        self,
        peer: FederatedPeer,
        our_peer_id: str,
        our_secret: str,
    ) -> bool:
        """Complete the federation handshake by sending our credentials to the peer."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Build auth headers using their credentials
                headers = self._build_auth_headers(peer)
                url = f"{peer.endpoint_url}/api/v1/federation/handshake/complete"

                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "peer_id": our_peer_id,
                        "secret": our_secret,
                        "endpoint_url": "",  # Will be filled by the caller
                    },
                )
                response.raise_for_status()

                logger.info(f"Federation handshake completed with peer: {peer.name}")
                return True

        except Exception as e:
            logger.error(f"Failed to complete federation handshake with {peer.name}: {e}")
            # Mark peer as pending since handshake failed
            peer.status = PeerStatus.PENDING
            await self.session.commit()
            return False

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
        timestamp: str | None = None,
    ) -> list[dict]:
        """Handle discovery request from a peer."""
        peer = await self._verify_peer_request(peer_id, signature, timestamp)
        if not peer:
            return []

        # Return published capabilities from this instance
        from nexus.discovery.service import DiscoveryService
        from nexus.discovery.models import Capability, CapabilityStatus
        from nexus.identity.models import Agent, AgentStatus

        discovery = DiscoveryService(self.session)

        # Query all active capabilities that are marked for federation
        result = await self.session.execute(
            select(Capability, Agent)
            .join(Agent, Capability.agent_id == Agent.id)
            .where(
                Capability.status == CapabilityStatus.ACTIVE,
                Agent.status == AgentStatus.ACTIVE,
                # Only return capabilities marked as federated
                Capability.metadata_["federated"].astext == "true",
            )
            .limit(100)
        )

        capabilities = []
        for cap, agent in result.all():
            capabilities.append({
                "agent_slug": agent.slug,
                "name": cap.name,
                "description": cap.description,
                "category": cap.category,
                "tags": cap.tags,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
            })

        await self._log_request(
            peer_id=peer.id,
            direction="inbound",
            request_type="discover",
            status="completed",
            response_summary={"count": len(capabilities)},
        )

        peer.requests_received += 1
        peer.last_seen_at = datetime.now(timezone.utc)
        await self.session.commit()

        return capabilities

    async def handle_inbound_invocation(
        self,
        peer_id: str,
        signature: str,
        agent_slug: str,
        capability_name: str,
        input_data: dict,
        timestamp: str | None = None,
    ) -> dict:
        """Handle invocation request from a peer."""
        peer = await self._verify_peer_request(peer_id, signature, timestamp)
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

        # Find the capability and check if it requires approval
        from nexus.discovery.models import Capability, CapabilityStatus
        from nexus.identity.models import Agent, AgentStatus

        result = await self.session.execute(
            select(Capability, Agent)
            .join(Agent, Capability.agent_id == Agent.id)
            .where(
                Agent.slug == agent_slug,
                Agent.status == AgentStatus.ACTIVE,
                Capability.name == capability_name,
                Capability.status == CapabilityStatus.ACTIVE,
            )
        )
        row = result.first()

        if not row:
            request_log.status = "failed"
            request_log.response_summary = {"error": "Capability not found"}
            await self.session.commit()
            return {"error": "Capability not found"}

        capability, agent = row

        # Check if capability is federated
        cap_meta = capability.metadata_ or {}
        if not cap_meta.get("federated"):
            request_log.status = "failed"
            request_log.response_summary = {"error": "Capability not available for federation"}
            await self.session.commit()
            return {"error": "Capability not available for federation"}

        # Check trust level requirements
        required_trust = cap_meta.get("required_trust_level", "standard")
        if required_trust == "full" and peer.trust_level != TrustLevel.FULL:
            request_log.status = "failed"
            request_log.response_summary = {"error": "Insufficient trust level"}
            await self.session.commit()
            return {"error": "Insufficient trust level"}

        # Check if approval is required
        requires_approval = cap_meta.get("requires_approval", True)

        if requires_approval:
            peer.requests_received += 1
            peer.last_seen_at = datetime.now(timezone.utc)
            await self.session.commit()
            return {
                "status": "pending_approval",
                "request_id": str(request_log.id),
                "message": "Request requires manual approval",
            }

        # Execute the capability directly
        return await self._execute_inbound_capability(
            peer, capability, agent, input_data, request_log
        )

    async def _execute_inbound_capability(
        self,
        peer: FederatedPeer,
        capability,
        agent,
        input_data: dict,
        request_log: FederationRequest,
    ) -> dict:
        """Execute an inbound capability invocation."""
        try:
            # If capability has an endpoint, call it
            if capability.endpoint_url:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        capability.endpoint_url,
                        json=input_data,
                        headers={"X-Nexus-Federation": "true"},
                    )
                    response.raise_for_status()
                    result = response.json()
            else:
                # No endpoint - capability is informational only
                result = {
                    "status": "completed",
                    "message": "Capability executed (no endpoint configured)",
                }

            request_log.status = "completed"
            request_log.completed_at = datetime.now(timezone.utc)
            request_log.response_summary = {"status": "completed"}
            await self.session.commit()

            peer.requests_received += 1
            peer.last_seen_at = datetime.now(timezone.utc)
            await self.session.commit()

            return {"status": "completed", "output": result}

        except Exception as e:
            request_log.status = "failed"
            request_log.response_summary = {"error": str(e)}
            await self.session.commit()
            return {"error": str(e)}

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
        timestamp: str | None = None,
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

        # SECURITY: Verify timestamp to prevent replay attacks
        if timestamp:
            try:
                request_time = int(timestamp)
                current_time = int(datetime.now(timezone.utc).timestamp())
                # Allow 5 minute window for clock skew
                if abs(current_time - request_time) > 300:
                    logger.warning(f"Rejected peer request with stale timestamp: {peer_id}")
                    return None
            except (ValueError, TypeError):
                logger.warning(f"Invalid timestamp format from peer: {peer_id}")
                return None

        # SECURITY: Verify HMAC signature
        if timestamp:
            message = f"{peer_id}:{timestamp}"
            expected_signature = hmac.new(
                peer.our_secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning(f"Invalid signature from peer: {peer_id}")
                return None

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
