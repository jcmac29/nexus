"""Federation module - Connect Nexus instances together securely."""

from nexus.federation.models import (
    FederatedPeer,
    FederationRequest,
    PeerStatus,
    TrustLevel,
)
from nexus.federation.service import FederationService
from nexus.federation.routes import router

__all__ = [
    "FederatedPeer",
    "FederationRequest",
    "PeerStatus",
    "TrustLevel",
    "FederationService",
    "router",
]
