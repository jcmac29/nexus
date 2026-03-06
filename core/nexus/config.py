"""Configuration management for Nexus."""

import os
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# Default secrets that MUST be changed in production
_INSECURE_DEFAULTS = {
    "change-me-in-production-use-a-real-secret-key",
    "change-me-admin-jwt-secret-minimum-32-chars",
    "nexus-secret-key",
    "nexus",  # Default storage access key
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined in settings
    )

    # Application
    app_name: str = "Nexus"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "change-me-in-production-use-a-real-secret-key"
    api_key_prefix: str = "nex_"
    access_token_expire_minutes: int = 60 * 24 * 7  # 1 week

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Stripe (optional - billing disabled if not set)
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_connect_webhook_secret: str | None = None  # For Connect events

    # Stripe Price IDs (created via scripts/setup_stripe.py)
    stripe_price_starter_monthly: str | None = None
    stripe_price_starter_annual: str | None = None
    stripe_price_pro_monthly: str | None = None
    stripe_price_pro_annual: str | None = None
    stripe_price_business_monthly: str | None = None
    stripe_price_business_annual: str | None = None

    # Media Storage (MinIO/S3)
    storage_endpoint: str = "http://minio:9000"
    storage_access_key: str = "nexus"
    storage_secret_key: str = "nexus-secret-key"
    storage_bucket: str = "nexus-media"
    storage_region: str = "us-east-1"

    # Twilio (SMS)
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None

    # Feature flags (simple)
    enable_federation: bool = True
    enable_marketplace: bool = True
    enable_devices: bool = True

    # Infrastructure Providers (for worker pools)
    digitalocean_token: str | None = None
    kubernetes_config_path: str | None = None

    # Gigs/Worker Pools
    nexus_public_url: str = "https://api.nexus.ai"
    worker_image: str = "nexus/worker:latest"
    default_worker_region: str = "nyc3"

    # Environment
    environment: str = "development"
    log_level: str = "INFO"

    # Multi-Tenancy (Hosted Cloud)
    multi_tenant_enabled: bool = False
    base_domain: str = "nexus-cloud.com"  # Base domain for subdomain routing
    default_subdomain: str = "api"  # Subdomain for non-tenant requests

    # Feature Flags (global defaults, can be overridden per tenant)
    feature_graph_memory: bool = True
    feature_webhooks: bool = True
    feature_federation: bool = True
    feature_marketplace: bool = True

    # Admin Authentication
    admin_jwt_secret: str = "change-me-admin-jwt-secret-minimum-32-chars"
    admin_token_expire_hours: int = 24
    admin_email: str | None = None  # Initial admin email (created on startup)
    admin_password: str | None = None  # Initial admin password

    # Frontend URLs (for CORS)
    admin_dashboard_url: str = "http://localhost:3001"
    landing_url: str = "http://localhost:3000"
    frontend_url: str = "http://localhost"  # Base URL for password reset links

    # SMTP Email (optional - password reset disabled if not set)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_tls: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@nexus.ai"


def _validate_production_secrets(settings: Settings) -> None:
    """Ensure no default secrets are used in production."""
    if settings.environment == "production" or not settings.debug:
        insecure_values = []

        if settings.secret_key in _INSECURE_DEFAULTS:
            insecure_values.append("SECRET_KEY")
        if settings.admin_jwt_secret in _INSECURE_DEFAULTS:
            insecure_values.append("ADMIN_JWT_SECRET")
        if settings.storage_access_key in _INSECURE_DEFAULTS:
            insecure_values.append("STORAGE_ACCESS_KEY")
        if settings.storage_secret_key in _INSECURE_DEFAULTS:
            insecure_values.append("STORAGE_SECRET_KEY")

        if insecure_values:
            print(
                f"\n{'='*60}\n"
                f"SECURITY ERROR: Insecure default values detected!\n"
                f"{'='*60}\n"
                f"The following secrets are using default/insecure values:\n"
                f"  - {', '.join(insecure_values)}\n\n"
                f"In production, you MUST set these to secure random values.\n"
                f"Generate secure values with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
                f"{'='*60}\n",
                file=sys.stderr,
            )
            # In production, refuse to start with insecure secrets
            if settings.environment == "production":
                sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    _validate_production_secrets(settings)
    return settings
