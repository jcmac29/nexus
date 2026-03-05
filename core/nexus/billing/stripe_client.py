"""Stripe integration for billing."""

import os
import stripe
from typing import Any

from nexus.config import get_settings
from nexus.billing.plans import PLANS, PlanType

settings = get_settings()

# Configure Stripe
stripe.api_key = settings.stripe_secret_key if hasattr(settings, 'stripe_secret_key') else None

# Stripe Price IDs - loaded from settings
# Run scripts/setup_stripe.py to create these in your Stripe account
def _get_price_ids():
    """Load price IDs from settings."""
    return {
        PlanType.STARTER: {
            "monthly": getattr(settings, 'stripe_price_starter_monthly', None) or "price_starter_monthly",
            "annual": getattr(settings, 'stripe_price_starter_annual', None) or "price_starter_annual",
        },
        PlanType.PRO: {
            "monthly": getattr(settings, 'stripe_price_pro_monthly', None) or "price_pro_monthly",
            "annual": getattr(settings, 'stripe_price_pro_annual', None) or "price_pro_annual",
        },
        PlanType.BUSINESS: {
            "monthly": getattr(settings, 'stripe_price_business_monthly', None) or "price_business_monthly",
            "annual": getattr(settings, 'stripe_price_business_annual', None) or "price_business_annual",
        },
    }

STRIPE_PRICE_IDS = _get_price_ids()


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

    # --- Stripe Connect (for seller payouts) ---

    def create_connect_account(
        self,
        email: str,
        country: str = "US",
        account_type: str = "express",
        metadata: dict[str, str] | None = None,
    ) -> str | None:
        """Create a Stripe Connect account for a seller."""
        if not self.enabled:
            return None

        account = stripe.Account.create(
            type=account_type,
            country=country,
            email=email,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            metadata=metadata or {},
        )
        return account.id

    def create_connect_onboarding_link(
        self,
        account_id: str,
        return_url: str,
        refresh_url: str,
    ) -> str:
        """Create onboarding link for Connect account."""
        if not self.enabled:
            return ""

        link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )
        return link.url

    def create_connect_login_link(self, account_id: str) -> str:
        """Create login link for Connect Express dashboard."""
        if not self.enabled:
            return ""

        link = stripe.Account.create_login_link(account_id)
        return link.url

    def get_connect_account(self, account_id: str) -> dict[str, Any] | None:
        """Get Connect account details."""
        if not self.enabled:
            return None

        try:
            account = stripe.Account.retrieve(account_id)
            return {
                "id": account.id,
                "email": account.email,
                "charges_enabled": account.charges_enabled,
                "payouts_enabled": account.payouts_enabled,
                "details_submitted": account.details_submitted,
                "country": account.country,
            }
        except stripe.error.InvalidRequestError:
            return None

    def create_transfer(
        self,
        amount_cents: int,
        destination_account_id: str,
        currency: str = "usd",
        description: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Transfer funds to a Connect account."""
        if not self.enabled:
            return {}

        transfer = stripe.Transfer.create(
            amount=amount_cents,
            currency=currency,
            destination=destination_account_id,
            description=description,
            metadata=metadata or {},
        )
        return {
            "id": transfer.id,
            "amount": transfer.amount,
            "currency": transfer.currency,
            "destination": transfer.destination,
        }

    def create_payout(
        self,
        account_id: str,
        amount_cents: int,
        currency: str = "usd",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a payout to Connect account's bank."""
        if not self.enabled:
            return {}

        payout = stripe.Payout.create(
            amount=amount_cents,
            currency=currency,
            metadata=metadata or {},
            stripe_account=account_id,
        )
        return {
            "id": payout.id,
            "amount": payout.amount,
            "status": payout.status,
            "arrival_date": payout.arrival_date,
        }

    def get_connect_balance(self, account_id: str) -> dict[str, Any] | None:
        """Get balance for a Connect account."""
        if not self.enabled:
            return None

        balance = stripe.Balance.retrieve(stripe_account=account_id)
        available = sum(b.amount for b in balance.available)
        pending = sum(b.amount for b in balance.pending)
        return {
            "available_cents": available,
            "pending_cents": pending,
            "currency": balance.available[0].currency if balance.available else "usd",
        }


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
