"""OAuth/SSO module - Login with Google, GitHub, etc."""

from nexus.oauth.models import OAuthConnection, OAuthProvider
from nexus.oauth.service import OAuthService
from nexus.oauth.routes import router

__all__ = [
    "OAuthConnection",
    "OAuthProvider",
    "OAuthService",
    "router",
]
