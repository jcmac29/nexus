"""Configuration management for Nexus."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
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

    # Media Storage (MinIO/S3)
    storage_endpoint: str = "http://minio:9000"
    storage_access_key: str = "nexus"
    storage_secret_key: str = "nexus-secret-key"
    storage_bucket: str = "nexus-media"

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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
