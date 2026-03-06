"""IP address utilities with security considerations.

SECURITY: Provides safe extraction of client IP addresses with
protection against header spoofing attacks.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Set

from fastapi import Request

from nexus.config import get_settings

logger = logging.getLogger(__name__)


# SECURITY: Trusted proxy IP ranges (configure based on infrastructure)
# These are common private network ranges used by reverse proxies
DEFAULT_TRUSTED_PROXIES: Set[str] = {
    "10.0.0.0/8",      # Private network (common for cloud providers)
    "172.16.0.0/12",   # Private network
    "192.168.0.0/16",  # Private network
    "127.0.0.0/8",     # Loopback
    "::1/128",         # IPv6 loopback
}


def _get_trusted_proxies() -> Set[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Get configured trusted proxy networks."""
    settings = get_settings()

    # Allow override from settings
    custom_proxies = getattr(settings, "trusted_proxy_networks", None)
    if custom_proxies:
        proxy_strs = custom_proxies
    else:
        proxy_strs = DEFAULT_TRUSTED_PROXIES

    networks = set()
    for proxy in proxy_strs:
        try:
            networks.add(ipaddress.ip_network(proxy, strict=False))
        except ValueError:
            logger.warning(f"Invalid trusted proxy network: {proxy}")

    return networks


def _is_trusted_proxy(ip_str: str, trusted_networks: Set) -> bool:
    """Check if an IP address is from a trusted proxy."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in trusted_networks)
    except ValueError:
        return False


def _is_valid_ip(ip_str: str) -> bool:
    """Validate that a string is a valid IP address."""
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """Get the real client IP address safely.

    SECURITY: Only trusts X-Forwarded-For header when request comes from
    a trusted proxy. Prevents header spoofing attacks.

    Returns:
        Client IP address string, or "unknown" if not determinable.
    """
    # Get the direct connection IP
    direct_ip = request.client.host if request.client else None

    if not direct_ip:
        return "unknown"

    # Get trusted proxy networks
    trusted_networks = _get_trusted_proxies()

    # Only parse X-Forwarded-For if request comes from trusted proxy
    if _is_trusted_proxy(direct_ip, trusted_networks):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For is a comma-separated list
            # The leftmost is the original client (if proxies are honest)
            # The rightmost is the most recent proxy
            ips = [ip.strip() for ip in forwarded.split(",")]

            # Get the first non-proxy IP (traversing from right to left)
            for ip in reversed(ips):
                if _is_valid_ip(ip) and not _is_trusted_proxy(ip, trusted_networks):
                    return ip

            # If all IPs are proxies, take the leftmost
            if ips and _is_valid_ip(ips[0]):
                return ips[0]

    # Return direct connection IP
    return direct_ip


def get_client_ip_simple(request: Request) -> str:
    """Simple client IP extraction (for non-security-critical uses).

    WARNING: This function trusts X-Forwarded-For headers. For rate limiting
    and security features, use get_client_ip() instead.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
