#!/usr/bin/env python3
"""
Secret Rotation Script for Nexus

SECURITY: Run this script regularly to rotate internal secrets.
Recommended schedule: Every 90 days minimum, or immediately after any suspected breach.

Usage:
    python scripts/rotate_secrets.py

This script will:
1. Generate new secure secrets
2. Update .env file with new values
3. Log rotation timestamp for audit

IMPORTANT: After running, restart all services to pick up new secrets.
External services (Stripe, Twilio, DigitalOcean) must be rotated manually in their dashboards.
"""

import os
import re
import secrets
from datetime import datetime
from pathlib import Path


def generate_secret(length: int = 32) -> str:
    """Generate a cryptographically secure secret."""
    return secrets.token_urlsafe(length)


def rotate_env_secrets(env_path: Path) -> dict[str, str]:
    """Rotate secrets in .env file."""
    if not env_path.exists():
        print(f"ERROR: {env_path} not found")
        return {}

    content = env_path.read_text()
    rotated = {}
    today = datetime.now().strftime("%Y-%m-%d")

    # Secrets to rotate (internal only - not external API keys)
    secrets_to_rotate = {
        "SECRET_KEY": 32,
        "ADMIN_JWT_SECRET": 32,
        "STORAGE_SECRET_KEY": 24,
    }

    for secret_name, length in secrets_to_rotate.items():
        new_value = generate_secret(length)
        rotated[secret_name] = new_value

        # Update the value in content
        pattern = rf"^{secret_name}=.*$"
        replacement = f"{secret_name}={new_value}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    # Update rotation timestamp comment if exists, or add one
    if "# Rotated:" in content:
        content = re.sub(
            r"# Rotated: \d{4}-\d{2}-\d{2}",
            f"# Rotated: {today}",
            content
        )
    else:
        # Add rotation timestamp at the top
        content = f"# Rotated: {today}\n{content}"

    # Write back
    env_path.write_text(content)
    return rotated


def main():
    print("=" * 60)
    print("NEXUS SECRET ROTATION")
    print("=" * 60)
    print()

    # Find .env file
    script_dir = Path(__file__).parent
    env_path = script_dir.parent / ".env"

    if not env_path.exists():
        print(f"ERROR: .env file not found at {env_path}")
        print("Please create .env from .env.example first.")
        return 1

    print(f"Rotating secrets in: {env_path}")
    print()

    # Rotate internal secrets
    rotated = rotate_env_secrets(env_path)

    if rotated:
        print("ROTATED INTERNAL SECRETS:")
        for name in rotated:
            print(f"  - {name}")
        print()

    # Remind about external secrets
    print("=" * 60)
    print("MANUAL ROTATION REQUIRED FOR EXTERNAL SERVICES:")
    print("=" * 60)
    print()
    print("These must be rotated in their respective dashboards:")
    print()
    print("1. STRIPE (every 90 days or after exposure)")
    print("   Dashboard: https://dashboard.stripe.com/apikeys")
    print("   - STRIPE_SECRET_KEY")
    print("   - STRIPE_PUBLISHABLE_KEY")
    print("   - STRIPE_WEBHOOK_SECRET")
    print("   - STRIPE_CONNECT_WEBHOOK_SECRET")
    print()
    print("2. TWILIO (every 90 days or after exposure)")
    print("   Console: https://console.twilio.com")
    print("   - TWILIO_ACCOUNT_SID (cannot rotate)")
    print("   - TWILIO_AUTH_TOKEN (can rotate)")
    print()
    print("3. DIGITALOCEAN (every 90 days or after exposure)")
    print("   Dashboard: https://cloud.digitalocean.com/account/api/tokens")
    print("   - DIGITALOCEAN_TOKEN")
    print()
    print("=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print()
    print("1. Restart all Nexus services to pick up new secrets")
    print("2. Test that authentication still works")
    print("3. Update any external integrations with new keys")
    print()
    print(f"Next rotation recommended: {datetime.now().strftime('%Y-%m-%d')} + 90 days")
    print()

    return 0


if __name__ == "__main__":
    exit(main())
