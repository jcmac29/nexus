"""Analytics module - Usage tracking and insights."""

from nexus.analytics.service import AnalyticsService
from nexus.analytics.routes import router

__all__ = ["AnalyticsService", "router"]
