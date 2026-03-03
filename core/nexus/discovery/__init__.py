"""Discovery module - Find agents and capabilities."""

from nexus.discovery.models import Capability
from nexus.discovery.routes import router
from nexus.discovery.service import DiscoveryService

__all__ = ["Capability", "router", "DiscoveryService"]
