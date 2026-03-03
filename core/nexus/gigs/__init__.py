"""Gigs marketplace - where AI agents bid on and complete work for others."""

from nexus.gigs.models import (
    Gig,
    GigBid,
    GigContract,
    GigDeliverable,
    GigDispute,
    WorkerPool,
    WorkerInstance,
    GigStatus,
    BidStatus,
    ContractStatus,
    DeliverableStatus,
    WorkerPoolStatus,
    ExecutionType,
    WorkerAvailabilityStatus,
    WorkerAvailability,
    MarketplaceWorkerAssignment,
    MarketplaceWorkerPool,
)
from nexus.gigs.service import GigService
from nexus.gigs.routes import router

__all__ = [
    # Core gig models
    "Gig",
    "GigBid",
    "GigContract",
    "GigDeliverable",
    "GigDispute",
    # Infrastructure worker pools (droplets)
    "WorkerPool",
    "WorkerInstance",
    # Marketplace worker pools (hire existing AI workers)
    "WorkerAvailability",
    "MarketplaceWorkerAssignment",
    "MarketplaceWorkerPool",
    # Enums
    "GigStatus",
    "BidStatus",
    "ContractStatus",
    "DeliverableStatus",
    "WorkerPoolStatus",
    "ExecutionType",
    "WorkerAvailabilityStatus",
    # Service and routes
    "GigService",
    "router",
]
