"""Pydantic schemas for billing API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Account Schemas ---

class AccountCreate(BaseModel):
    """Create a new account."""
    email: str = Field(..., description="Account email")
    name: str = Field(..., description="Account name")


class AccountResponse(BaseModel):
    """Account response."""
    id: UUID
    email: str
    name: str
    plan: str
    stripe_customer_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Usage Schemas ---

class UsageMetric(BaseModel):
    """Single usage metric."""
    used: int
    limit: int
    percentage: float


class UsageResponse(BaseModel):
    """Current usage response."""
    period_start: str
    period_end: str
    plan: str
    usage: dict[str, UsageMetric]


class UsageHistoryItem(BaseModel):
    """Historical usage item."""
    date: str
    memory_ops: int
    discovery_queries: int
    api_requests: int


class UsageHistoryResponse(BaseModel):
    """Usage history response."""
    items: list[UsageHistoryItem]


# --- Plan Schemas ---

class PlanFeature(BaseModel):
    """Plan feature."""
    name: str


class PlanLimitsResponse(BaseModel):
    """Plan limits."""
    agents: int
    memory_ops_per_month: int
    stored_memories: int
    discovery_queries_per_month: int
    api_requests_per_month: int
    team_members: int


class PlanPricingResponse(BaseModel):
    """Plan pricing."""
    monthly_price: float
    annual_price: float
    annual_savings_percent: int = 20


class PlanResponse(BaseModel):
    """Plan details."""
    type: str
    name: str
    description: str
    limits: PlanLimitsResponse
    pricing: PlanPricingResponse
    features: list[str]


class PlansListResponse(BaseModel):
    """All available plans."""
    plans: list[PlanResponse]
    current_plan: str


# --- Subscription Schemas ---

class CreateCheckoutRequest(BaseModel):
    """Request to create checkout session."""
    plan: str = Field(..., description="Plan type: starter, pro, business")
    annual: bool = Field(False, description="Annual billing")
    success_url: str = Field(..., description="Redirect URL on success")
    cancel_url: str = Field(..., description="Redirect URL on cancel")


class CheckoutResponse(BaseModel):
    """Checkout session response."""
    checkout_url: str
    session_id: str


class SubscriptionResponse(BaseModel):
    """Subscription details."""
    id: UUID
    plan: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    is_annual: bool

    model_config = {"from_attributes": True}


class CancelSubscriptionRequest(BaseModel):
    """Cancel subscription request."""
    cancel_at_period_end: bool = Field(
        True,
        description="If true, subscription remains active until period end"
    )


# --- Billing Portal ---

class BillingPortalResponse(BaseModel):
    """Billing portal session."""
    portal_url: str


# --- Invoice Schemas ---

class InvoiceLineItem(BaseModel):
    """Invoice line item."""
    description: str
    amount: float
    quantity: int


class InvoiceResponse(BaseModel):
    """Invoice details."""
    id: str
    amount_due: float
    amount_paid: float
    status: str
    period_start: datetime
    period_end: datetime
    line_items: list[InvoiceLineItem]
    pdf_url: str | None


class InvoiceListResponse(BaseModel):
    """List of invoices."""
    invoices: list[InvoiceResponse]
