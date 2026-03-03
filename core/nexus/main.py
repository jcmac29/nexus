"""Main FastAPI application."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus import __version__
from nexus.config import get_settings
from nexus.database import init_db
from nexus.billing import routes as billing_routes
from nexus.discovery import routes as discovery_routes
from nexus.identity import routes as identity_routes
from nexus.memory import routes as memory_routes
from nexus.messaging import routes as messaging_routes
from nexus.webhooks import routes as webhook_routes
from nexus.streaming import routes as streaming_routes
from nexus.workflows import routes as workflow_routes
from nexus.analytics import routes as analytics_routes
from nexus.ratelimit import routes as ratelimit_routes
from nexus.health import routes as health_routes
from nexus.marketplace import routes as marketplace_routes
from nexus.teams import routes as teams_routes
from nexus.media import routes as media_routes
from nexus.federation import routes as federation_routes
from nexus.public import routes as public_routes
from nexus.profiles import routes as profile_routes

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    await init_db()
    yield
    # Shutdown (if needed)


app = FastAPI(
    title=settings.app_name,
    description="The connective layer for AI agents - Identity, Memory, Discovery",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health Check ---


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "version": __version__}


@app.get("/", tags=["system"])
async def root() -> dict:
    """Root endpoint with API info."""
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


# --- Wire up routes with auth ---

# Identity routes (registration is public, others need auth)
app.include_router(
    identity_routes.router,
    prefix=settings.api_prefix,
)

# Memory routes (all authenticated)
app.include_router(
    memory_routes.router,
    prefix=settings.api_prefix,
)

# Discovery routes (mixed: discovery is public, capability registration needs auth)
app.include_router(
    discovery_routes.router,
    prefix=settings.api_prefix,
)

# Billing routes
app.include_router(
    billing_routes.router,
    prefix=settings.api_prefix,
)

# Messaging routes (agent-to-agent communication)
app.include_router(
    messaging_routes.router,
    prefix=settings.api_prefix,
)

# Webhook routes
app.include_router(
    webhook_routes.router,
    prefix=settings.api_prefix,
)

# Streaming routes (SSE)
app.include_router(
    streaming_routes.router,
    prefix=settings.api_prefix,
)

# Workflow routes
app.include_router(
    workflow_routes.router,
    prefix=settings.api_prefix,
)

# Analytics routes
app.include_router(
    analytics_routes.router,
    prefix=settings.api_prefix,
)

# Rate limiting routes
app.include_router(
    ratelimit_routes.router,
    prefix=settings.api_prefix,
)

# Health monitoring routes
app.include_router(
    health_routes.router,
    prefix=settings.api_prefix,
)

# Marketplace routes
app.include_router(
    marketplace_routes.router,
    prefix=settings.api_prefix,
)

# Team collaboration routes
app.include_router(
    teams_routes.router,
    prefix=settings.api_prefix,
)

# Media storage routes
app.include_router(
    media_routes.router,
    prefix=settings.api_prefix,
)

# Federation routes (connect Nexus instances)
app.include_router(
    federation_routes.router,
    prefix=settings.api_prefix,
)

# Public marketplace routes (safe public capability sharing)
app.include_router(
    public_routes.router,
    prefix=settings.api_prefix,
)

# Profile, settings, prompts, and subscription routes
app.include_router(
    profile_routes.router,
    prefix=settings.api_prefix,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "nexus.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
