"""AI-friendly onboarding - let AIs discover and join Nexus autonomously."""

from nexus.onboarding.service import OnboardingService
from nexus.onboarding.routes import router

__all__ = ["OnboardingService", "router"]
