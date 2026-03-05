"""Billing API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.billing.models import UsageType
from nexus.cache import get_cache
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
from nexus.identity.models import Agent

router = APIRouter(prefix="/billing", tags=["billing"])


# --- Rate Limiting ---


async def public_endpoint_rate_limit(request: Request):
    """
    SECURITY: Rate limit public endpoints to prevent enumeration and DoS.
    Limit: 60 requests per minute per IP address.
    """
    cache = await get_cache()

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    key = f"ratelimit:billing:public:{client_ip}"

    allowed, current, remaining = await cache.rate_limit_check(
        key=key,
        limit=60,  # 60 requests
        window_seconds=60,  # per minute
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after": 60,
            },
            headers={"Retry-After": "60"},
        )


# --- Helper Functions ---

async def get_billing_service(db: AsyncSession = Depends(get_db)) -> BillingService:
    """Get billing service instance."""
    return BillingService(db)


async def get_agent_account_id(
    agent: Agent = Depends(get_current_agent),
) -> UUID:
    """Get the account ID for the current agent."""
    if hasattr(agent, "account_id") and agent.account_id:
        return agent.account_id
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Agent is not associated with a billing account",
    )


async def verify_account_access(
    account_id: UUID,
    agent: Agent = Depends(get_current_agent),
) -> None:
    """Verify the agent has access to the specified account."""
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this account",
        )


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
    agent: Agent = Depends(get_current_agent),  # SECURITY: Require authentication
    service: BillingService = Depends(get_billing_service),
):
    """Create a new billing account. Requires authentication."""
    # SECURITY: Only authenticated agents can create billing accounts
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
        owner_agent_id=agent.id,  # Associate with the creating agent
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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Get account by ID."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this account",
        )

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
async def list_plans(
    account_id: UUID | None = None,
    service: BillingService = Depends(get_billing_service),
    _: None = Depends(public_endpoint_rate_limit),  # SECURITY: Rate limit public endpoint
):
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
async def get_plan(
    plan_type: str,
    _: None = Depends(public_endpoint_rate_limit),  # SECURITY: Rate limit public endpoint
):
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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Get current usage for account."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this account",
        )

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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Track usage for an account (internal use)."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to track usage for this account",
        )

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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Check if account is within limits for a usage type."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to check limits for this account",
        )

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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Create a Stripe checkout session for subscription."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create checkout for this account",
        )

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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Get active subscription for account."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view subscription for this account",
        )

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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Cancel subscription."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel subscription for this account",
        )

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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """Get Stripe billing portal URL."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access billing portal for this account",
        )

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
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
):
    """List invoices for account."""
    # SECURITY: Verify the agent has access to this account
    if not hasattr(agent, "account_id") or agent.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view invoices for this account",
        )

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
        # Create subscription record and give promotional credits for first-time paid subscribers
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")

        if customer_id and subscription_id:
            # Find the account by Stripe customer ID
            account = await service.get_account_by_stripe_customer(customer_id)
            if account:
                # Find the user by matching email
                from nexus.users.models import User
                from sqlalchemy import select

                result = await service.db.execute(
                    select(User).where(User.email == account.email.lower())
                )
                user = result.scalar_one_or_none()

                if user:
                    # Give $5 promo credit for first-time paid subscribers
                    from nexus.credits.service import CreditService
                    from decimal import Decimal

                    credit_service = CreditService(service.db)

                    # Check if they already have promotional credits (don't give twice)
                    balance = await credit_service.get_balance("user", user.id)
                    if not balance or balance.promotional_balance == 0:
                        await credit_service.add_promotional_credits(
                            owner_type="user",
                            owner_id=user.id,
                            amount=Decimal("5.00"),
                            description="Welcome bonus - $5 promotional credit for upgrading to paid plan",
                        )
                        await service.db.commit()

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


# --- Seller Account & Payouts (Stripe Connect) ---

@router.get("/seller-account")
async def get_seller_account(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get seller account details for current user."""
    from nexus.billing.models import SellerAccount
    from sqlalchemy import select
    from nexus.users.models import User

    # Get user from agent
    if not hasattr(agent, "user_id") or not agent.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent not associated with user account",
        )

    # Get account
    result = await db.execute(
        select(SellerAccount).join(Account).where(
            Account.email == (await db.execute(select(User.email).where(User.id == agent.user_id))).scalar()
        )
    )
    seller = result.scalar_one_or_none()

    if not seller:
        return None

    return {
        "id": str(seller.id),
        "stripe_account_id": seller.stripe_account_id,
        "stripe_onboarding_complete": seller.stripe_onboarding_complete,
        "stripe_payouts_enabled": seller.stripe_payouts_enabled,
        "total_sales": seller.total_sales_cents / 100,
        "total_fees_paid": seller.total_fees_paid_cents / 100,
        "total_payouts": seller.total_payouts_cents / 100,
        "pending_balance": seller.pending_balance_cents / 100,
        "payout_schedule": seller.payout_schedule,
        "minimum_payout": seller.minimum_payout_cents / 100,
    }


@router.post("/seller-account/onboard")
async def onboard_seller(
    agent: Agent = Depends(get_current_agent),
    service: BillingService = Depends(get_billing_service),
    db: AsyncSession = Depends(get_db),
):
    """Start Stripe Connect onboarding for seller."""
    from nexus.billing.models import SellerAccount
    from nexus.billing.marketplace_service import MarketplaceBillingService
    from nexus.users.models import User
    from sqlalchemy import select

    if not hasattr(agent, "user_id") or not agent.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent not associated with user account",
        )

    # Get user email
    result = await db.execute(select(User).where(User.id == agent.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get or create account
    account = await service.get_account_by_email(user.email)
    if not account:
        account = await service.create_account(user.email, user.name)
        await db.commit()

    # Get or create seller account
    result = await db.execute(
        select(SellerAccount).where(SellerAccount.account_id == account.id)
    )
    seller = result.scalar_one_or_none()

    marketplace_service = MarketplaceBillingService(db)

    if not seller:
        seller = await marketplace_service.create_seller_account(account.id)

    # Create Stripe Connect account if needed
    if not seller.stripe_account_id:
        if stripe_client.enabled:
            stripe_account_id = stripe_client.create_connect_account(
                email=user.email,
                metadata={"account_id": str(account.id)},
            )
            seller.stripe_account_id = stripe_account_id
            await db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe is not configured",
            )

    # Generate onboarding link
    from nexus.config import get_settings
    settings = get_settings()
    return_url = f"{settings.frontend_url}/earnings?onboarding=complete"
    refresh_url = f"{settings.frontend_url}/earnings?onboarding=refresh"

    onboarding_url = stripe_client.create_connect_onboarding_link(
        seller.stripe_account_id,
        return_url=return_url,
        refresh_url=refresh_url,
    )

    return {"onboarding_url": onboarding_url}


@router.get("/seller-account/dashboard")
async def get_seller_dashboard_link(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get Stripe Express dashboard link for seller."""
    from nexus.billing.models import SellerAccount
    from sqlalchemy import select
    from nexus.users.models import User

    if not hasattr(agent, "user_id") or not agent.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent not associated with user account",
        )

    result = await db.execute(select(User).where(User.id == agent.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find seller account
    result = await db.execute(
        select(SellerAccount).join(Account).where(Account.email == user.email)
    )
    seller = result.scalar_one_or_none()

    if not seller or not seller.stripe_account_id:
        raise HTTPException(status_code=404, detail="Seller account not found")

    dashboard_url = stripe_client.create_connect_login_link(seller.stripe_account_id)
    return {"dashboard_url": dashboard_url}


@router.post("/payouts/request")
async def request_payout(
    amount_cents: int,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Request a payout of available earnings."""
    from nexus.billing.models import SellerAccount
    from nexus.billing.marketplace_service import MarketplaceBillingService
    from sqlalchemy import select
    from nexus.users.models import User

    if not hasattr(agent, "user_id") or not agent.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent not associated with user account",
        )

    result = await db.execute(select(User).where(User.id == agent.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find seller account
    result = await db.execute(
        select(SellerAccount).join(Account).where(Account.email == user.email)
    )
    seller = result.scalar_one_or_none()

    if not seller:
        raise HTTPException(status_code=404, detail="Seller account not found")

    if not seller.stripe_payouts_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payouts not enabled. Complete Stripe onboarding first.",
        )

    if amount_cents < seller.minimum_payout_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum payout is ${seller.minimum_payout_cents / 100}",
        )

    if amount_cents > seller.pending_balance_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount exceeds available balance",
        )

    # Create payout via Stripe
    if stripe_client.enabled and seller.stripe_account_id:
        payout_result = stripe_client.create_payout(
            account_id=seller.stripe_account_id,
            amount_cents=amount_cents,
            metadata={"seller_account_id": str(seller.id)},
        )

        # Update seller balance
        seller.pending_balance_cents -= amount_cents
        seller.total_payouts_cents += amount_cents
        await db.commit()

        return {
            "status": "processing",
            "payout_id": payout_result.get("id"),
            "amount": amount_cents / 100,
            "arrival_date": payout_result.get("arrival_date"),
        }

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Stripe is not configured",
    )


@router.get("/payouts")
async def list_payouts(
    limit: int = 10,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List payout history for seller."""
    from nexus.billing.models import SellerAccount, MarketplacePayout
    from sqlalchemy import select
    from nexus.users.models import User

    if not hasattr(agent, "user_id") or not agent.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent not associated with user account",
        )

    result = await db.execute(select(User).where(User.id == agent.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find seller account
    result = await db.execute(
        select(SellerAccount).join(Account).where(Account.email == user.email)
    )
    seller = result.scalar_one_or_none()

    if not seller:
        return {"items": []}

    # Get payouts
    result = await db.execute(
        select(MarketplacePayout)
        .where(MarketplacePayout.seller_account_id == seller.account_id)
        .order_by(MarketplacePayout.created_at.desc())
        .limit(limit)
    )
    payouts = result.scalars().all()

    return {
        "items": [
            {
                "id": str(p.id),
                "status": p.status.value,
                "gross_amount": p.gross_amount_cents / 100,
                "platform_fees": p.platform_fees_cents / 100,
                "net_amount": p.net_amount_cents / 100,
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "processed_at": p.processed_at.isoformat() if p.processed_at else None,
                "destination_last4": p.destination_last4,
            }
            for p in payouts
        ]
    }


# --- Stripe Connect Webhooks ---

@router.post("/webhooks/stripe-connect")
async def stripe_connect_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe Connect webhooks."""
    from nexus.billing.stripe_client import construct_webhook_event
    from nexus.billing.models import SellerAccount
    from nexus.config import get_settings
    from sqlalchemy import select

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

    # Handle Connect events
    if event.type == "account.updated":
        account = event.data.object
        stripe_account_id = account.id

        # Find and update seller account
        result = await db.execute(
            select(SellerAccount).where(SellerAccount.stripe_account_id == stripe_account_id)
        )
        seller = result.scalar_one_or_none()

        if seller:
            seller.stripe_charges_enabled = account.charges_enabled
            seller.stripe_payouts_enabled = account.payouts_enabled
            seller.stripe_onboarding_complete = account.details_submitted
            await db.commit()

    elif event.type == "payout.paid":
        payout = event.data.object
        # Could update payout status here if needed

    elif event.type == "payout.failed":
        payout = event.data.object
        # Handle failed payout notification

    return {"received": True}
