"""Email module - Email communication for AI and human agents."""

from nexus.email.models import Email, EmailThread, EmailAccount, EmailTemplate
from nexus.email.service import EmailService
from nexus.email.routes import router

__all__ = ["Email", "EmailThread", "EmailAccount", "EmailTemplate", "EmailService", "router"]
