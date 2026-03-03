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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
