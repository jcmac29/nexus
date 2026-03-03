"""Stripe integration for billing."""

import stripe
from typing import Any

from nexus.config import get_settings
from nexus.billing.plans import PLANS, PlanType

settings = get_settings()

# Configure Stripe
stripe.api_key = settings.stripe_secret_key if hasattr(settings, 'stripe_secret_key') else None

# Stripe Price IDs (to be configured)
STRIPE_PRICE_IDS = {
    PlanType.STARTER: {
        "monthly": "price_starter_monthly",
        "annual": "price_starter_annual",
    },
    PlanType.PRO: {
        "monthly": "price_pro_monthly",
        "annual": "price_pro_annual",
    },
    PlanType.BUSINESS: {
        "monthly": "price_business_monthly",
        "annual": "price_business_annual",
    },
}


class StripeClient:
    """Client for Stripe operations."""

    def __init__(self):
        if not stripe.api_key:
            self.enabled = False
        else:
            self.enabled = True

    def create_customer(
        self,
        email: str,
        name: str,
        metadata: dict[str, str] | None = None,
    ) -> str | None:
        """Create a Stripe customer."""
        if not self.enabled:
            return None

        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata=metadata or {},
        )
        return customer.id

    def create_checkout_session(
        self,
        customer_id: str,
        plan_type: PlanType,
        annual: bool,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        """Create a checkout session for subscription."""
        if not self.enabled:
            return {"checkout_url": "", "session_id": ""}

        price_id = STRIPE_PRICE_IDS[plan_type]["annual" if annual else "monthly"]

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "plan_type": plan_type.value,
                "annual": str(annual),
            },
        )

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    def create_billing_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> str:
        """Create a billing portal session."""
        if not self.enabled:
            return ""

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True,
    ) -> dict[str, Any]:
        """Cancel a subscription."""
        if not self.enabled:
            return {}

        if cancel_at_period_end:
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True,
            )
        else:
            subscription = stripe.Subscription.cancel(subscription_id)

        return {
            "id": subscription.id,
            "status": subscription.status,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        }

    def get_subscription(self, subscription_id: str) -> dict[str, Any] | None:
        """Get subscription details."""
        if not self.enabled:
            return None

        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_start": subscription.current_period_start,
                "current_period_end": subscription.current_period_end,
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }
        except stripe.error.InvalidRequestError:
            return None

    def list_invoices(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List invoices for a customer."""
        if not self.enabled:
            return []

        invoices = stripe.Invoice.list(customer=customer_id, limit=limit)

        return [
            {
                "id": inv.id,
                "amount_due": inv.amount_due / 100,
                "amount_paid": inv.amount_paid / 100,
                "status": inv.status,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "pdf_url": inv.invoice_pdf,
            }
            for inv in invoices.data
        ]

    def create_usage_record(
        self,
        subscription_item_id: str,
        quantity: int,
        timestamp: int | None = None,
    ) -> dict[str, Any]:
        """Create a usage record for metered billing."""
        if not self.enabled:
            return {}

        record = stripe.SubscriptionItem.create_usage_record(
            subscription_item_id,
            quantity=quantity,
            timestamp=timestamp,
            action="increment",
        )
        return {"id": record.id, "quantity": record.quantity}


def construct_webhook_event(
    payload: bytes,
    sig_header: str,
    webhook_secret: str,
) -> stripe.Event | None:
    """Construct and verify a Stripe webhook event."""
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event
    except (ValueError, stripe.error.SignatureVerificationError):
        return None


# Singleton client
stripe_client = StripeClient()
