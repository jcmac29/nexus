"""Billing API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.billing.models import UsageType
from nexus.billing.plans import PLANS, PlanType
from nexus.billing.schemas import (
    AccountCreate,
    AccountResponse,
    BillingPortalResponse,
    CancelSubscriptionRequest,
    CheckoutResponse,
    CreateCheckoutRequest,
    InvoiceListResponse,
    InvoiceResponse,
    PlanLimitsResponse,
    PlanPricingResponse,
    PlanResponse,
    PlansListResponse,
    SubscriptionResponse,
    UsageHistoryItem,
    UsageHistoryResponse,
    UsageMetric,
    UsageResponse,
)
from nexus.billing.service import BillingService
from nexus.billing.stripe_client import stripe_client
from nexus.database import get_db

router = APIRouter(prefix="/billing", tags=["billing"])


# --- Helper Functions ---

async def get_billing_service(db: AsyncSession = Depends(get_db)) -> BillingService:
    """Get billing service instance."""
    return BillingService(db)


def plan_to_response(plan_type: PlanType) -> PlanResponse:
    """Convert plan definition to response."""
    plan = PLANS[plan_type]
    return PlanResponse(
        type=plan.type.value,
        name=plan.name,
        description=plan.description,
        limits=PlanLimitsResponse(
            agents=plan.limits.agents,
            memory_ops_per_month=plan.limits.memory_ops_per_month,
            stored_memories=plan.limits.stored_memories,
            discovery_queries_per_month=plan.limits.discovery_queries_per_month,
            api_requests_per_month=plan.limits.api_requests_per_month,
            team_members=plan.limits.team_members,
        ),
        pricing=PlanPricingResponse(
            monthly_price=plan.pricing.monthly_price_cents / 100,
            annual_price=plan.pricing.annual_price_cents / 100,
        ),
        features=plan.features,
    )


# --- Account Routes ---

@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
    service: BillingService = Depends(get_billing_service),
):
    """Create a new billing account."""
    # Check if account already exists
    existing = await service.get_account_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account with this email already exists",
        )

    account = await service.create_account(
        email=data.email,
        name=data.name,
    )

    # Create Stripe customer if enabled
    if stripe_client.enabled:
        stripe_customer_id = stripe_client.create_customer(
            email=data.email,
            name=data.name,
            metadata={"account_id": str(account.id)},
        )
        if stripe_customer_id:
            await service.set_stripe_customer_id(account.id, stripe_customer_id)

    return AccountResponse(
        id=account.id,
        email=account.email,
        name=account.name,
        plan=account.plan_type.value,
        stripe_customer_id=account.stripe_customer_id,
        created_at=account.created_at,
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    service: BillingService = Depends(get_billing_service),
):
    """Get account by ID."""
    account = await service.get_account_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    return AccountResponse(
        id=account.id,
        email=account.email,
        name=account.name,
        plan=account.plan_type.value,
        stripe_customer_id=account.stripe_customer_id,
        created_at=account.created_at,
    )


# --- Plans Routes ---

@router.get("/plans", response_model=PlansListResponse)
async def list_plans(account_id: UUID | None = None, service: BillingService = Depends(get_billing_service)):
    """List all available plans."""
    current_plan = "free"

    if account_id:
        account = await service.get_account_by_id(account_id)
        if account:
            current_plan = account.plan_type.value

    plans = [
        plan_to_response(pt)
        for pt in [PlanType.FREE, PlanType.STARTER, PlanType.PRO, PlanType.BUSINESS, PlanType.ENTERPRISE]
    ]

    return PlansListResponse(plans=plans, current_plan=current_plan)


@router.get("/plans/{plan_type}", response_model=PlanResponse)
async def get_plan(plan_type: str):
    """Get plan details."""
    try:
        pt = PlanType(plan_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_type}' not found",
        )

    return plan_to_response(pt)


# --- Usage Routes ---

@router.get("/accounts/{account_id}/usage", response_model=UsageResponse)
async def get_usage(
    account_id: UUID,
    service: BillingService = Depends(get_billing_service),
):
    """Get current usage for account."""
    usage_data = await service.get_current_month_usage(account_id)
    if not usage_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    return UsageResponse(
        period_start=usage_data["period_start"],
        period_end=usage_data["period_end"],
        plan=usage_data["plan"],
        usage={
            k: UsageMetric(**v)
            for k, v in usage_data["usage"].items()
        },
    )


@router.post("/accounts/{account_id}/usage/track")
async def track_usage(
    account_id: UUID,
    usage_type: str,
    count: int = 1,
    service: BillingService = Depends(get_billing_service),
):
    """Track usage for an account (internal use)."""
    try:
        ut = UsageType(usage_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid usage type: {usage_type}",
        )

    # Check limits
    is_allowed, current, limit = await service.check_limit(account_id, ut)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Usage limit exceeded: {current}/{limit}",
        )

    usage = await service.track_usage(account_id, ut, count)

    return {
        "tracked": True,
        "usage_type": usage_type,
        "count": usage.count,
        "limit": limit,
    }


@router.get("/accounts/{account_id}/usage/check")
async def check_usage_limit(
    account_id: UUID,
    usage_type: str,
    service: BillingService = Depends(get_billing_service),
):
    """Check if account is within limits for a usage type."""
    try:
        ut = UsageType(usage_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid usage type: {usage_type}",
        )

    is_allowed, current, limit = await service.check_limit(account_id, ut)

    return {
        "allowed": is_allowed,
        "current": current,
        "limit": limit,
        "percentage": round(current / limit * 100, 1) if limit > 0 else 0,
    }


# --- Subscription Routes ---

@router.post("/accounts/{account_id}/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    account_id: UUID,
    data: CreateCheckoutRequest,
    service: BillingService = Depends(get_billing_service),
):
    """Create a Stripe checkout session for subscription."""
    account = await service.get_account_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if not account.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account has no Stripe customer ID",
        )

    try:
        plan_type = PlanType(data.plan)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan: {data.plan}",
        )

    if plan_type == PlanType.FREE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot checkout for free plan",
        )

    result = stripe_client.create_checkout_session(
        customer_id=account.stripe_customer_id,
        plan_type=plan_type,
        annual=data.annual,
        success_url=data.success_url,
        cancel_url=data.cancel_url,
    )

    return CheckoutResponse(**result)


@router.get("/accounts/{account_id}/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    account_id: UUID,
    service: BillingService = Depends(get_billing_service),
):
    """Get active subscription for account."""
    subscription = await service.get_active_subscription(account_id)
    if not subscription:
        return None

    return SubscriptionResponse(
        id=subscription.id,
        plan=subscription.plan_type.value,
        status=subscription.status.value,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        is_annual=subscription.is_annual,
    )


@router.post("/accounts/{account_id}/subscription/cancel")
async def cancel_subscription(
    account_id: UUID,
    data: CancelSubscriptionRequest,
    service: BillingService = Depends(get_billing_service),
):
    """Cancel subscription."""
    subscription = await service.get_active_subscription(account_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    # Cancel in Stripe
    stripe_result = stripe_client.cancel_subscription(
        subscription.stripe_subscription_id,
        cancel_at_period_end=data.cancel_at_period_end,
    )

    # Update local record
    await service.cancel_subscription(
        subscription.stripe_subscription_id,
        cancel_at_period_end=data.cancel_at_period_end,
    )

    return {
        "canceled": True,
        "cancel_at_period_end": data.cancel_at_period_end,
        "period_end": subscription.current_period_end.isoformat(),
    }


# --- Billing Portal ---

@router.get("/accounts/{account_id}/portal", response_model=BillingPortalResponse)
async def get_billing_portal(
    account_id: UUID,
    return_url: str,
    service: BillingService = Depends(get_billing_service),
):
    """Get Stripe billing portal URL."""
    account = await service.get_account_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if not account.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account has no Stripe customer ID",
        )

    portal_url = stripe_client.create_billing_portal_session(
        customer_id=account.stripe_customer_id,
        return_url=return_url,
    )

    return BillingPortalResponse(portal_url=portal_url)


# --- Invoices ---

@router.get("/accounts/{account_id}/invoices", response_model=InvoiceListResponse)
async def list_invoices(
    account_id: UUID,
    limit: int = 10,
    service: BillingService = Depends(get_billing_service),
):
    """List invoices for account."""
    account = await service.get_account_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if not account.stripe_customer_id:
        return InvoiceListResponse(invoices=[])

    invoices = stripe_client.list_invoices(
        customer_id=account.stripe_customer_id,
        limit=limit,
    )

    return InvoiceListResponse(
        invoices=[
            InvoiceResponse(
                id=inv["id"],
                amount_due=inv["amount_due"],
                amount_paid=inv["amount_paid"],
                status=inv["status"],
                period_start=inv["period_start"],
                period_end=inv["period_end"],
                line_items=[],  # Simplified for now
                pdf_url=inv["pdf_url"],
            )
            for inv in invoices
        ]
    )


# --- Webhooks ---

@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    service: BillingService = Depends(get_billing_service),
):
    """Handle Stripe webhooks."""
    from nexus.billing.stripe_client import construct_webhook_event
    from nexus.config import get_settings

    settings = get_settings()
    webhook_secret = getattr(settings, 'stripe_webhook_secret', None)

    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    event = construct_webhook_event(payload, sig_header, webhook_secret)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    # Handle events
    if event.type == "checkout.session.completed":
        session = event.data.object
        # Create subscription record
        # This would be handled based on your specific needs

    elif event.type == "customer.subscription.updated":
        subscription = event.data.object
        from nexus.billing.models import SubscriptionStatus
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "canceled": SubscriptionStatus.CANCELED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "trialing": SubscriptionStatus.TRIALING,
            "paused": SubscriptionStatus.PAUSED,
        }
        new_status = status_map.get(subscription.status)
        if new_status:
            await service.update_subscription_status(
                subscription.id,
                new_status,
            )

    elif event.type == "customer.subscription.deleted":
        subscription = event.data.object
        from nexus.billing.models import SubscriptionStatus
        await service.update_subscription_status(
            subscription.id,
            SubscriptionStatus.CANCELED,
        )

    elif event.type == "invoice.payment_failed":
        invoice = event.data.object
        # Handle failed payment - could send notification, etc.
        pass

    return {"received": True}
