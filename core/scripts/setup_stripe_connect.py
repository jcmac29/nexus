#!/usr/bin/env python3
"""
Stripe Connect Setup Script for Nexus

This script configures Stripe Connect for marketplace seller payouts.
Run this after setting up your basic Stripe configuration.

Usage:
    STRIPE_SECRET_KEY=sk_test_xxx python scripts/setup_stripe_connect.py

Requirements:
    - Stripe account with Connect enabled
    - stripe Python package installed
"""

import os
import sys
import stripe

# Stripe API key from environment
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")

if not STRIPE_SECRET_KEY:
    print("Error: STRIPE_SECRET_KEY environment variable not set")
    print("Usage: STRIPE_SECRET_KEY=sk_test_xxx python scripts/setup_stripe_connect.py")
    sys.exit(1)

stripe.api_key = STRIPE_SECRET_KEY


def check_connect_enabled() -> bool:
    """Check if Stripe Connect is enabled on this account."""
    try:
        # Try to list Connect accounts - this will fail if Connect isn't enabled
        stripe.Account.list(limit=1)
        return True
    except stripe.error.PermissionError:
        return False
    except stripe.error.InvalidRequestError as e:
        if "Connect" in str(e):
            return False
        raise


def get_platform_settings() -> dict:
    """Get current platform settings."""
    try:
        account = stripe.Account.retrieve()
        return {
            "account_id": account.id,
            "country": account.country,
            "business_type": account.business_type,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
        }
    except Exception as e:
        print(f"Error getting account: {e}")
        return {}


def setup_connect_settings() -> None:
    """Configure Connect settings."""
    print("\nConfiguring Stripe Connect settings...")

    # Note: Most Connect settings are configured in the Stripe Dashboard
    # This script provides guidance and verification

    print("""
Stripe Connect Configuration Checklist:
========================================

1. Enable Connect in your Stripe Dashboard:
   https://dashboard.stripe.com/settings/connect

2. Configure your Connect branding:
   https://dashboard.stripe.com/settings/connect/branding
   - Add your logo
   - Set your brand color
   - Configure your business name

3. Set up Connect onboarding:
   https://dashboard.stripe.com/settings/connect/onboarding
   - Choose "Express" for easiest seller onboarding
   - Configure required information

4. Configure payout settings:
   https://dashboard.stripe.com/settings/connect/payouts
   - Set default payout schedule (daily, weekly, monthly)
   - Configure minimum payout amounts

5. Set up Connect webhooks:
   https://dashboard.stripe.com/webhooks
   - Create a webhook for Connect events
   - URL: https://api.yourdomain.com/api/v1/billing/webhooks/stripe-connect
   - Events to listen for:
     * account.updated
     * account.application.authorized
     * account.application.deauthorized
     * payout.created
     * payout.paid
     * payout.failed
     * transfer.created
     * transfer.reversed

6. Configure your platform fee:
   The default is 10% for subscriptions, 15% for one-time purchases.
   This is configured in:
   core/nexus/billing/marketplace_service.py

7. Test with Stripe CLI:
   stripe listen --forward-to localhost:8000/api/v1/billing/webhooks/stripe-connect
""")


def create_test_connect_account() -> None:
    """Create a test Connect account for development."""
    print("\nCreating test Connect account...")

    try:
        account = stripe.Account.create(
            type="express",
            country="US",
            email="test-seller@example.com",
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            metadata={
                "test_account": "true",
                "created_by": "setup_script",
            },
        )
        print(f"Created test account: {account.id}")

        # Create onboarding link
        link = stripe.AccountLink.create(
            account=account.id,
            refresh_url="http://localhost:3000/earnings?refresh=true",
            return_url="http://localhost:3000/earnings?complete=true",
            type="account_onboarding",
        )
        print(f"Onboarding URL: {link.url}")
        print("\nOpen this URL to complete test seller onboarding.")

    except stripe.error.InvalidRequestError as e:
        print(f"Error creating test account: {e}")


def main():
    print("=" * 60)
    print("NEXUS STRIPE CONNECT SETUP")
    print("=" * 60)
    print(f"\nUsing Stripe API key: {STRIPE_SECRET_KEY[:12]}...")
    print(f"Mode: {'TEST' if 'test' in STRIPE_SECRET_KEY else 'LIVE'}")
    print()

    # Check if Connect is enabled
    print("Checking Stripe Connect status...")
    if check_connect_enabled():
        print("Stripe Connect is ENABLED")
    else:
        print("Stripe Connect is NOT ENABLED")
        print("\nPlease enable Connect in your Stripe Dashboard:")
        print("https://dashboard.stripe.com/settings/connect")
        sys.exit(1)

    # Get platform settings
    print("\nPlatform account info:")
    settings = get_platform_settings()
    for key, value in settings.items():
        print(f"  {key}: {value}")

    # Show setup instructions
    setup_connect_settings()

    # Offer to create test account
    if "test" in STRIPE_SECRET_KEY:
        print("\n" + "=" * 60)
        print("TEST ACCOUNT CREATION")
        print("=" * 60)
        response = input("\nCreate a test Connect account? (y/n): ").lower().strip()
        if response == "y":
            create_test_connect_account()

    print("\n" + "=" * 60)
    print("ENVIRONMENT VARIABLES")
    print("=" * 60)
    print("""
Add to your .env file:

# Stripe Connect Webhook Secret
STRIPE_CONNECT_WEBHOOK_SECRET=whsec_xxx
""")

    print("\nSetup complete!")


if __name__ == "__main__":
    main()
