"""Nexus SDK - Connect your AI agents."""

from nexus_sdk.client import Nexus, NexusAsync
from nexus_sdk.memory import Memory, MemoryAsync
from nexus_sdk.discovery import Discovery, DiscoveryAsync
from nexus_sdk.graph import Graph, GraphAsync
from nexus_sdk.webhooks import Webhooks, WebhooksAsync
from nexus_sdk.analytics import Analytics, AnalyticsAsync
from nexus_sdk.tenants import Tenants, TenantsAsync
from nexus_sdk.swarm import Swarm, SwarmAsync
from nexus_sdk.learning import Learning, LearningAsync
from nexus_sdk.reputation import Reputation, ReputationAsync
from nexus_sdk.goals import Goals, GoalsAsync
from nexus_sdk.context import Context, ContextAsync
from nexus_sdk.budgets import Budgets, BudgetsAsync
from nexus_sdk.vitals import Vitals, VitalsAsync

__version__ = "0.3.0"

__all__ = [
    "Nexus",
    "NexusAsync",
    "Memory",
    "MemoryAsync",
    "Discovery",
    "DiscoveryAsync",
    "Graph",
    "GraphAsync",
    "Webhooks",
    "WebhooksAsync",
    "Analytics",
    "AnalyticsAsync",
    "Tenants",
    "TenantsAsync",
    "Swarm",
    "SwarmAsync",
    "Learning",
    "LearningAsync",
    "Reputation",
    "ReputationAsync",
    "Goals",
    "GoalsAsync",
    "Context",
    "ContextAsync",
    "Budgets",
    "BudgetsAsync",
    "Vitals",
    "VitalsAsync",
]
