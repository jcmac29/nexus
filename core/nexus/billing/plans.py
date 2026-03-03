"""Plan definitions and limits."""

from enum import Enum
from dataclasses import dataclass


class PlanType(str, Enum):
    """Available plan types."""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


@dataclass
class PlanLimits:
    """Limits for a plan."""
    agents: int
    memory_ops_per_month: int
    stored_memories: int
    discovery_queries_per_month: int
    api_requests_per_month: int
    team_members: int
    retention_days: int | None  # None = unlimited


@dataclass
class PlanPricing:
    """Pricing for a plan."""
    monthly_price_cents: int
    annual_price_cents: int  # Annual price (with discount)
    memory_ops_overage_cents: int  # Per 10K operations
    api_requests_overage_cents: int  # Per 10K requests
    storage_overage_cents: int  # Per 10K memories


@dataclass
class PlanDefinition:
    """Complete plan definition."""
    type: PlanType
    name: str
    description: str
    limits: PlanLimits
    pricing: PlanPricing
    features: list[str]


# Plan definitions
PLANS: dict[PlanType, PlanDefinition] = {
    PlanType.FREE: PlanDefinition(
        type=PlanType.FREE,
        name="Free",
        description="For hobbyists and testing",
        limits=PlanLimits(
            agents=3,
            memory_ops_per_month=10_000,
            stored_memories=1_000,
            discovery_queries_per_month=1_000,
            api_requests_per_month=50_000,
            team_members=1,
            retention_days=30,
        ),
        pricing=PlanPricing(
            monthly_price_cents=0,
            annual_price_cents=0,
            memory_ops_overage_cents=0,  # No overage on free
            api_requests_overage_cents=0,
            storage_overage_cents=0,
        ),
        features=[
            "Community support",
            "Shared infrastructure",
            "Basic analytics",
        ],
    ),
    PlanType.STARTER: PlanDefinition(
        type=PlanType.STARTER,
        name="Starter",
        description="For individual developers",
        limits=PlanLimits(
            agents=10,
            memory_ops_per_month=100_000,
            stored_memories=50_000,
            discovery_queries_per_month=10_000,
            api_requests_per_month=500_000,
            team_members=1,
            retention_days=None,
        ),
        pricing=PlanPricing(
            monthly_price_cents=2900,  # $29
            annual_price_cents=27840,  # $278.40 (20% off)
            memory_ops_overage_cents=50,  # $0.50 per 10K
            api_requests_overage_cents=20,  # $0.20 per 10K
            storage_overage_cents=10,  # $0.10 per 10K
        ),
        features=[
            "Email support",
            "Basic analytics dashboard",
            "Webhooks",
            "Custom namespaces",
            "Unlimited retention",
        ],
    ),
    PlanType.PRO: PlanDefinition(
        type=PlanType.PRO,
        name="Pro",
        description="For teams and production",
        limits=PlanLimits(
            agents=50,
            memory_ops_per_month=1_000_000,
            stored_memories=500_000,
            discovery_queries_per_month=100_000,
            api_requests_per_month=5_000_000,
            team_members=5,
            retention_days=None,
        ),
        pricing=PlanPricing(
            monthly_price_cents=9900,  # $99
            annual_price_cents=95040,  # $950.40 (20% off)
            memory_ops_overage_cents=40,
            api_requests_overage_cents=15,
            storage_overage_cents=8,
        ),
        features=[
            "Priority email support",
            "Advanced analytics",
            "Webhooks + event streaming",
            "Team members (up to 5)",
            "API key management",
            "Usage alerts",
            "99.9% SLA",
        ],
    ),
    PlanType.BUSINESS: PlanDefinition(
        type=PlanType.BUSINESS,
        name="Business",
        description="For growing companies",
        limits=PlanLimits(
            agents=500,
            memory_ops_per_month=10_000_000,
            stored_memories=5_000_000,
            discovery_queries_per_month=1_000_000,
            api_requests_per_month=50_000_000,
            team_members=20,
            retention_days=None,
        ),
        pricing=PlanPricing(
            monthly_price_cents=49900,  # $499
            annual_price_cents=479040,  # $4,790.40 (20% off)
            memory_ops_overage_cents=30,
            api_requests_overage_cents=10,
            storage_overage_cents=5,
        ),
        features=[
            "Dedicated support channel",
            "Custom integrations assistance",
            "Team members (up to 20)",
            "SSO/SAML",
            "Audit logs",
            "Custom data retention",
            "99.95% SLA",
        ],
    ),
    PlanType.ENTERPRISE: PlanDefinition(
        type=PlanType.ENTERPRISE,
        name="Enterprise",
        description="For large organizations",
        limits=PlanLimits(
            agents=999_999,  # Effectively unlimited
            memory_ops_per_month=999_999_999,
            stored_memories=999_999_999,
            discovery_queries_per_month=999_999_999,
            api_requests_per_month=999_999_999,
            team_members=999,
            retention_days=None,
        ),
        pricing=PlanPricing(
            monthly_price_cents=200000,  # $2000 minimum
            annual_price_cents=1920000,
            memory_ops_overage_cents=0,  # Custom
            api_requests_overage_cents=0,
            storage_overage_cents=0,
        ),
        features=[
            "Everything in Business",
            "Unlimited resources",
            "Dedicated infrastructure",
            "On-premise option",
            "Custom SLA (up to 99.99%)",
            "Dedicated account manager",
            "24/7 phone support",
            "Security review & compliance",
        ],
    ),
}


def get_plan(plan_type: PlanType) -> PlanDefinition:
    """Get plan definition by type."""
    return PLANS[plan_type]


def get_plan_limits(plan_type: PlanType) -> PlanLimits:
    """Get plan limits by type."""
    return PLANS[plan_type].limits
