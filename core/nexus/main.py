"""Main FastAPI application."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from nexus import __version__
from nexus.config import get_settings
from nexus.database import init_db
from nexus.cache import get_cache
from nexus.observability import (
    setup_logging,
    get_metrics,
    set_app_info,
    MetricsMiddleware,
    LoggingMiddleware,
    TracingMiddleware,
    health_router,
)
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
from nexus.oauth import routes as oauth_routes
from nexus.audit import routes as audit_routes
from nexus.websockets import routes as websocket_routes
from nexus.conversations import routes as conversation_routes
from nexus.tools import routes as tools_routes
from nexus.events import routes as events_routes
from nexus.orchestration import routes as orchestration_routes
from nexus.scheduling import routes as scheduling_routes
from nexus.queues import routes as queues_routes
from nexus.connectors import routes as connectors_routes
from nexus.tracing import routes as tracing_routes
from nexus.phone import routes as phone_routes
from nexus.sms import routes as sms_routes
from nexus.email import routes as email_routes
from nexus.video import routes as video_routes
from nexus.notifications import routes as notifications_routes
from nexus.chat import routes as chat_routes
from nexus.calendar import routes as calendar_routes
from nexus.documents import routes as documents_routes
from nexus.devices import routes as devices_routes
from nexus.storage import routes as storage_routes
from nexus.search import routes as search_routes
from nexus.gigs import routes as gigs_routes
from nexus.credits import routes as credits_routes
from nexus.onboarding import routes as onboarding_routes

settings = get_settings()

# Setup structured logging
setup_logging(
    level=settings.log_level if hasattr(settings, 'log_level') else "INFO",
    format="json" if not settings.debug else "console",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    await init_db()

    # Initialize cache
    await get_cache()

    # Set application info for metrics
    set_app_info(__version__, settings.environment if hasattr(settings, 'environment') else "production")

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

# Observability middleware (order matters - tracing first, then logging, then metrics)
app.add_middleware(MetricsMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(TracingMiddleware)


# --- Health Check ---


@app.get("/metrics", tags=["system"], include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=get_metrics(), media_type="text/plain")


# Include comprehensive health checks
app.include_router(health_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Simple health check endpoint."""
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

# OAuth routes (Google, GitHub, Microsoft, Discord)
app.include_router(
    oauth_routes.router,
    prefix=settings.api_prefix,
)

# Audit logging routes
app.include_router(
    audit_routes.router,
    prefix=settings.api_prefix,
)

# WebSocket routes (real-time bidirectional)
app.include_router(
    websocket_routes.router,
    prefix=settings.api_prefix,
)

# Conversation threads
app.include_router(
    conversation_routes.router,
    prefix=settings.api_prefix,
)

# Tool registry
app.include_router(
    tools_routes.router,
    prefix=settings.api_prefix,
)

# Event bus (pub/sub)
app.include_router(
    events_routes.router,
    prefix=settings.api_prefix,
)

# Orchestration (multi-agent workflows)
app.include_router(
    orchestration_routes.router,
    prefix=settings.api_prefix,
)

# Scheduling (cron jobs)
app.include_router(
    scheduling_routes.router,
    prefix=settings.api_prefix,
)

# Priority queues
app.include_router(
    queues_routes.router,
    prefix=settings.api_prefix,
)

# External connectors (databases, APIs)
app.include_router(
    connectors_routes.router,
    prefix=settings.api_prefix,
)

# Distributed tracing
app.include_router(
    tracing_routes.router,
    prefix=settings.api_prefix,
)

# Phone/Voice communication
app.include_router(
    phone_routes.router,
    prefix=settings.api_prefix,
)

# SMS messaging
app.include_router(
    sms_routes.router,
    prefix=settings.api_prefix,
)

# Email communication
app.include_router(
    email_routes.router,
    prefix=settings.api_prefix,
)

# Video conferencing
app.include_router(
    video_routes.router,
    prefix=settings.api_prefix,
)

# Push notifications
app.include_router(
    notifications_routes.router,
    prefix=settings.api_prefix,
)

# Chat platform integrations (Slack, Discord, Telegram, etc.)
app.include_router(
    chat_routes.router,
    prefix=settings.api_prefix,
)

# Calendar and scheduling
app.include_router(
    calendar_routes.router,
    prefix=settings.api_prefix,
)

# Collaborative documents
app.include_router(
    documents_routes.router,
    prefix=settings.api_prefix,
)

# Device Gateway (IoT, drones, robotics, sensors)
app.include_router(
    devices_routes.router,
    prefix=settings.api_prefix,
)

# File storage (S3-compatible)
app.include_router(
    storage_routes.router,
    prefix=settings.api_prefix,
)

# Search (full-text and semantic)
app.include_router(
    search_routes.router,
    prefix=settings.api_prefix,
)

# Gigs marketplace (AI workers bidding on and completing work)
app.include_router(
    gigs_routes.router,
    prefix=settings.api_prefix,
)

# Credits (prepaid balance system)
app.include_router(
    credits_routes.router,
    prefix=settings.api_prefix,
)

# AI Self-Onboarding (discovery, registration, referrals)
app.include_router(
    onboarding_routes.router,
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
