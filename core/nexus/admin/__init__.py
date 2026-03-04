"""Admin module for dashboard authentication and management."""

from nexus.admin.auth import get_current_admin, require_admin_role
from nexus.admin.models import AdminRole, AdminUser
from nexus.admin.service import AdminService

__all__ = [
    "AdminUser",
    "AdminRole",
    "AdminService",
    "get_current_admin",
    "require_admin_role",
]
