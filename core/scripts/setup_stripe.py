#!/usr/bin/env python3
"""
Stripe Setup Script for Nexus

This script creates the necessary Stripe products and prices for the Nexus platform.
Run this once after setting up your Stripe account.

Usage:
    STRIPE_SECRET_KEY=sk_test_xxx python scripts/setup_stripe.py

Requirements:
    - Stripe account with API keys
    - stripe Python package installed
"""

import os
import sys
import stripe

# Stripe API key from environment
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")

if not STRIPE_SECRET_KEY:
    print("Error: STRIPE_SECRET_KEY environment variable not set")
    print("Usage: STRIPE_SECRET_KEY=sk_test_xxx python scripts/setup_stripe.py")
    sys.exit(1)

stripe.api_key = STRIPE_SECRET_KEY

# Plan definitions (must match plans.py)
PLANS = {
    "starter": {
        "name": "Starter Plan",
        "description": "For individual developers - 10 agents, 100K memory ops/month",
        "monthly_price_cents": 2900,  # $29
        "annual_price_cents": 27840,  # $278.40 (20% off)
    },
    "pro": {
        "name": "Pro Plan",
        "description": "For teams and production - 50 agents, 1M memory ops/month",
        "monthly_price_cents": 9900,  # $99
        "annual_price_cents": 95040,  # $950.40 (20% off)
    },
    "business": {
        "name": "Business Plan",
        "description": "For growing companies - 500 agents, 10M memory ops/month",
        "monthly_price_cents": 49900,  # $499
        "annual_price_cents": 479040,  # $4,790.40 (20% off)
    },
}


def create_product(plan_key: str, plan_data: dict) -> stripe.Product:
    """Create or retrieve a Stripe product."""
    # Search for existing product
    products = stripe.Product.search(
        query=f"metadata['plan_key']:'{plan_key}'"
    )

    if products.data:
        print(f"  Product already exists: {products.data[0].id}")
        return products.data[0]

    # Create new product
    product = stripe.Product.create(
        name=plan_data["name"],
        description=plan_data["description"],
        metadata={"plan_key": plan_key},
    )
    print(f"  Created product: {product.id}")
    return product


def create_price(
    product_id: str,
    plan_key: str,
    amount_cents: int,
    interval: str,
) -> stripe.Price:
    """Create or retrieve a Stripe price."""
    # Search for existing price
    prices = stripe.Price.search(
        query=f"product:'{product_id}' AND metadata['interval']:'{interval}'"
    )

    if prices.data:
        print(f"    Price already exists ({interval}): {prices.data[0].id}")
        return prices.data[0]

    # Create new price
    interval_count = 1 if interval == "month" else 1
    price = stripe.Price.create(
        product=product_id,
        unit_amount=amount_cents,
        currency="usd",
        recurring={
            "interval": "month" if interval == "month" else "year",
            "interval_count": interval_count,
        },
        metadata={
            "plan_key": plan_key,
            "interval": interval,
        },
    )
    print(f"    Created price ({interval}): {price.id}")
    return price


def setup_billing_portal() -> None:
    """Configure the Stripe billing portal."""
    print("""
Note: Billing portal requires manual configuration in Stripe Dashboard.
Go to: https://dashboard.stripe.com/settings/billing/portal

Configure these settings:
- Enable subscription cancellation (at period end)
- Enable payment method updates
- Enable invoice history
- Set return URL to your app's billing page
""")
    print("Billing portal setup instructions provided.")


def setup_webhooks() -> None:
    """Print webhook setup instructions."""
    print("\n" + "=" * 60)
    print("WEBHOOK SETUP")
    print("=" * 60)
    print("""
To receive Stripe events, configure a webhook in your Stripe dashboard:

1. Go to https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. Enter your webhook URL:
   - Production: https://api.yourdomain.com/api/v1/billing/webhooks/stripe
   - Development: Use Stripe CLI or ngrok

4. Select these events:
   - checkout.session.completed
   - customer.subscription.created
   - customer.subscription.updated
   - customer.subscription.deleted
   - invoice.payment_succeeded
   - invoice.payment_failed
   - account.updated (for Connect)
   - account.application.authorized (for Connect)
   - account.application.deauthorized (for Connect)

5. Copy the webhook signing secret and set it as:
   STRIPE_WEBHOOK_SECRET=whsec_xxx

For local development with Stripe CLI:
   stripe listen --forward-to localhost:8000/api/v1/billing/webhooks/stripe
""")


def main():
    print("=" * 60)
    print("NEXUS STRIPE SETUP")
    print("=" * 60)
    print(f"\nUsing Stripe API key: {STRIPE_SECRET_KEY[:12]}...")
    print(f"Mode: {'TEST' if 'test' in STRIPE_SECRET_KEY else 'LIVE'}")
    print()

    created_prices = {}

    for plan_key, plan_data in PLANS.items():
        print(f"\nSetting up {plan_data['name']}...")

        # Create product
        product = create_product(plan_key, plan_data)

        # Create monthly price
        monthly_price = create_price(
            product.id,
            plan_key,
            plan_data["monthly_price_cents"],
            "month",
        )
        created_prices[f"{plan_key}_monthly"] = monthly_price.id

        # Create annual price
        annual_price = create_price(
            product.id,
            plan_key,
            plan_data["annual_price_cents"],
            "year",
        )
        created_prices[f"{plan_key}_annual"] = annual_price.id

    # Set up billing portal
    print("\nConfiguring billing portal...")
    setup_billing_portal()

    # Print environment variables to set
    print("\n" + "=" * 60)
    print("CONFIGURATION")
    print("=" * 60)
    print("\nAdd these price IDs to your stripe_client.py or environment:\n")

    print("STRIPE_PRICE_IDS = {")
    print('    PlanType.STARTER: {')
    print(f'        "monthly": "{created_prices.get("starter_monthly", "price_xxx")}",')
    print(f'        "annual": "{created_prices.get("starter_annual", "price_xxx")}",')
    print('    },')
    print('    PlanType.PRO: {')
    print(f'        "monthly": "{created_prices.get("pro_monthly", "price_xxx")}",')
    print(f'        "annual": "{created_prices.get("pro_annual", "price_xxx")}",')
    print('    },')
    print('    PlanType.BUSINESS: {')
    print(f'        "monthly": "{created_prices.get("business_monthly", "price_xxx")}",')
    print(f'        "annual": "{created_prices.get("business_annual", "price_xxx")}",')
    print('    },')
    print("}")

    # Print webhook instructions
    setup_webhooks()

    print("\n" + "=" * 60)
    print("ENVIRONMENT VARIABLES")
    print("=" * 60)
    print("""
Add to your .env file:

# Stripe API Keys
STRIPE_SECRET_KEY=sk_test_xxx          # Your secret key
STRIPE_PUBLISHABLE_KEY=pk_test_xxx     # Your publishable key
STRIPE_WEBHOOK_SECRET=whsec_xxx        # Webhook signing secret

# For production, use live keys:
# STRIPE_SECRET_KEY=sk_live_xxx
# STRIPE_PUBLISHABLE_KEY=pk_live_xxx
""")

    print("\nSetup complete!")


if __name__ == "__main__":
    main()
