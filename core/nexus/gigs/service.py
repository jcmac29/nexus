"""Gigs marketplace service - AI workers bidding on and completing work."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import secrets
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.gigs.models import (
    Gig, GigBid, GigContract, GigDeliverable, GigDispute,
    WorkerPool, WorkerInstance,
    GigStatus, BidStatus, ContractStatus, DeliverableStatus, WorkerPoolStatus,
    ExecutionType, WorkerAvailabilityStatus,
    WorkerAvailability, MarketplaceWorkerAssignment, MarketplaceWorkerPool,
)
from nexus.credits.models import CreditBalance, CreditTransaction, CreditReservation, TransactionType
from nexus.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _validate_webhook_url(url: str | None) -> bool:
    """
    Validate webhook URL to prevent SSRF attacks.

    Returns True if URL is safe, False otherwise.
    """
    if not url:
        return True  # None/empty is valid (no webhook)

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        return False

    # Must have a hostname
    if not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()

    # Block localhost and common local hostnames
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "metadata.google.internal", "169.254.169.254",
        "metadata.internal", "kubernetes.default",
    }
    if hostname in blocked_hosts:
        logger.warning(f"Blocked webhook URL to: {hostname}")
        return False

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            logger.warning(f"Blocked webhook URL to private IP: {hostname}")
            return False
    except ValueError:
        # Not an IP address, it's a hostname
        pass

    # Block internal-looking hostnames
    if any(internal in hostname for internal in [".internal", ".local", ".localhost", ".svc.cluster"]):
        logger.warning(f"Blocked webhook URL to internal host: {hostname}")
        return False

    return True


class GigService:
    """Service for managing the gigs marketplace."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Gig Posting ---

    async def create_gig(
        self,
        poster_id: UUID,
        title: str,
        description: str,
        category: str,
        budget_min: Decimal,
        budget_max: Decimal,
        is_parallelizable: bool = False,
        total_units: int | None = None,
        max_workers: int = 1,
        execution_type: str | ExecutionType = ExecutionType.MARKETPLACE,
        deadline: datetime | None = None,
        requirements: str | None = None,
        tags: list[str] | None = None,
        min_reputation: float = 0.0,
        required_capabilities: list[str] | None = None,
    ) -> Gig:
        """Create a new gig posting."""
        # Convert string execution_type to enum if needed
        if isinstance(execution_type, str):
            execution_type = ExecutionType(execution_type)

        gig = Gig(
            poster_id=poster_id,
            title=title,
            description=description,
            category=category,
            budget_min=budget_min,
            budget_max=budget_max,
            is_parallelizable=is_parallelizable,
            total_units=total_units,
            max_workers=max_workers if is_parallelizable else 1,
            work_type="parallel" if is_parallelizable else "single",
            execution_type=execution_type,
            deadline=deadline,
            requirements=requirements,
            tags=",".join(tags) if tags else None,
            min_reputation=min_reputation,
            required_capabilities=required_capabilities,
            status=GigStatus.DRAFT,
        )

        # Calculate price per unit for parallel work
        if is_parallelizable and total_units:
            gig.price_per_unit = budget_max / total_units

        self.db.add(gig)
        await self.db.flush()
        return gig

    async def publish_gig(self, gig_id: UUID, poster_id: UUID) -> Gig | None:
        """Publish a gig to accept bids."""
        result = await self.db.execute(
            select(Gig).where(
                Gig.id == gig_id,
                Gig.poster_id == poster_id,
                Gig.status == GigStatus.DRAFT,
            )
        )
        gig = result.scalar_one_or_none()
        if not gig:
            return None

        # Reserve funds from poster's balance
        reserved = await self._reserve_funds(poster_id, gig.budget_max, gig_id)
        if not reserved:
            raise ValueError("Insufficient balance to post gig")

        gig.status = GigStatus.OPEN
        return gig

    async def get_gig(self, gig_id: UUID) -> Gig | None:
        """Get a gig by ID."""
        result = await self.db.execute(select(Gig).where(Gig.id == gig_id))
        return result.scalar_one_or_none()

    async def search_gigs(
        self,
        query: str | None = None,
        category: str | None = None,
        min_budget: Decimal | None = None,
        max_budget: Decimal | None = None,
        parallelizable_only: bool = False,
        status: GigStatus = GigStatus.OPEN,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Gig]:
        """Search available gigs."""
        stmt = select(Gig).where(Gig.status == status)

        if query:
            search = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Gig.title.ilike(search),
                    Gig.description.ilike(search),
                    Gig.tags.ilike(search),
                )
            )

        if category:
            stmt = stmt.where(Gig.category == category)

        if min_budget:
            stmt = stmt.where(Gig.budget_max >= min_budget)

        if max_budget:
            stmt = stmt.where(Gig.budget_min <= max_budget)

        if parallelizable_only:
            stmt = stmt.where(Gig.is_parallelizable == True)

        stmt = stmt.order_by(Gig.created_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # --- Bidding ---

    async def submit_bid(
        self,
        gig_id: UUID,
        bidder_id: UUID,
        proposed_price: Decimal,
        proposed_units: int | None = None,
        workers_available: int = 1,
        proposed_timeline_hours: float | None = None,
        cover_letter: str | None = None,
    ) -> GigBid:
        """Submit a bid on a gig."""
        # Verify gig is open
        gig = await self.get_gig(gig_id)
        if not gig or gig.status != GigStatus.OPEN:
            raise ValueError("Gig is not accepting bids")

        # Can't bid on own gig
        if gig.poster_id == bidder_id:
            raise ValueError("Cannot bid on your own gig")

        # Check if already bid
        existing = await self.db.execute(
            select(GigBid).where(
                GigBid.gig_id == gig_id,
                GigBid.bidder_id == bidder_id,
                GigBid.status == BidStatus.PENDING,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Already have a pending bid on this gig")

        bid = GigBid(
            gig_id=gig_id,
            bidder_id=bidder_id,
            proposed_price=proposed_price,
            proposed_units=proposed_units,
            workers_available=workers_available,
            proposed_timeline_hours=proposed_timeline_hours,
            cover_letter=cover_letter,
            status=BidStatus.PENDING,
        )

        self.db.add(bid)
        await self.db.flush()

        # Update bid count
        gig.bid_count += 1

        return bid

    async def get_bids_for_gig(self, gig_id: UUID) -> list[GigBid]:
        """Get all bids for a gig."""
        result = await self.db.execute(
            select(GigBid)
            .where(GigBid.gig_id == gig_id)
            .order_by(GigBid.proposed_price.asc())
        )
        return list(result.scalars().all())

    async def accept_bid(
        self,
        bid_id: UUID,
        poster_id: UUID,
        units_assigned: int | None = None,
    ) -> GigContract:
        """Accept a bid and create a contract."""
        # Get bid with gig
        result = await self.db.execute(
            select(GigBid, Gig)
            .join(Gig, GigBid.gig_id == Gig.id)
            .where(GigBid.id == bid_id)
        )
        row = result.one_or_none()
        if not row:
            raise ValueError("Bid not found")

        bid, gig = row

        # Verify poster owns the gig
        if gig.poster_id != poster_id:
            raise ValueError("Not authorized")

        if bid.status != BidStatus.PENDING:
            raise ValueError("Bid is no longer pending")

        # Accept the bid
        bid.status = BidStatus.ACCEPTED

        # Calculate units for parallel work
        unit_start = None
        unit_end = None
        agreed_units = units_assigned or bid.proposed_units

        if gig.is_parallelizable and agreed_units:
            # Find next available unit range
            contracts = await self.db.execute(
                select(GigContract).where(
                    GigContract.gig_id == gig.id,
                    GigContract.status == ContractStatus.ACTIVE,
                )
            )
            existing = list(contracts.scalars().all())
            assigned_units = sum(c.agreed_units or 0 for c in existing)
            unit_start = assigned_units
            unit_end = assigned_units + agreed_units

        # Create contract
        contract = GigContract(
            gig_id=gig.id,
            bid_id=bid.id,
            worker_id=bid.bidder_id,
            agreed_price=bid.proposed_price,
            agreed_units=agreed_units,
            unit_range_start=unit_start,
            unit_range_end=unit_end,
            deadline=gig.deadline,
            status=ContractStatus.ACTIVE,
            escrow_amount=bid.proposed_price,
        )

        self.db.add(contract)

        # Update gig status
        if not gig.is_parallelizable:
            gig.status = GigStatus.IN_PROGRESS
            gig.started_at = datetime.now(timezone.utc)
        elif gig.is_parallelizable:
            # Check if all units assigned
            total_assigned = (unit_end or 0)
            if total_assigned >= (gig.total_units or 0):
                gig.status = GigStatus.IN_PROGRESS
                gig.started_at = datetime.now(timezone.utc)

        await self.db.flush()
        return contract

    async def reject_bid(self, bid_id: UUID, poster_id: UUID) -> GigBid | None:
        """Reject a bid."""
        result = await self.db.execute(
            select(GigBid, Gig)
            .join(Gig, GigBid.gig_id == Gig.id)
            .where(GigBid.id == bid_id, Gig.poster_id == poster_id)
        )
        row = result.one_or_none()
        if not row:
            return None

        bid, _ = row
        bid.status = BidStatus.REJECTED
        return bid

    # --- Work Delivery ---

    async def submit_deliverable(
        self,
        contract_id: UUID,
        worker_id: UUID,
        title: str,
        output_type: str,
        output_data: dict,
        description: str | None = None,
        units_covered: list[int] | None = None,
    ) -> GigDeliverable:
        """Submit a deliverable for a contract."""
        # Verify contract
        result = await self.db.execute(
            select(GigContract).where(
                GigContract.id == contract_id,
                GigContract.worker_id == worker_id,
                GigContract.status == ContractStatus.ACTIVE,
            )
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise ValueError("Active contract not found")

        deliverable = GigDeliverable(
            contract_id=contract_id,
            title=title,
            description=description,
            output_type=output_type,
            output_data=output_data,
            units_covered=units_covered,
            status=DeliverableStatus.SUBMITTED,
        )

        self.db.add(deliverable)

        # Update progress
        if units_covered:
            contract.units_completed += len(units_covered)
            if contract.agreed_units:
                contract.progress_percent = (contract.units_completed / contract.agreed_units) * 100

        await self.db.flush()
        return deliverable

    async def approve_deliverable(
        self,
        deliverable_id: UUID,
        poster_id: UUID,
        notes: str | None = None,
    ) -> GigDeliverable:
        """Approve a deliverable and release payment."""
        # Get deliverable with contract and gig
        result = await self.db.execute(
            select(GigDeliverable, GigContract, Gig)
            .join(GigContract, GigDeliverable.contract_id == GigContract.id)
            .join(Gig, GigContract.gig_id == Gig.id)
            .where(GigDeliverable.id == deliverable_id)
        )
        row = result.one_or_none()
        if not row:
            raise ValueError("Deliverable not found")

        deliverable, contract, gig = row

        if gig.poster_id != poster_id:
            raise ValueError("Not authorized")

        deliverable.status = DeliverableStatus.APPROVED
        deliverable.reviewer_notes = notes
        deliverable.reviewed_at = datetime.now(timezone.utc)

        # Check if contract is complete
        if contract.units_completed >= (contract.agreed_units or 1):
            contract.status = ContractStatus.COMPLETED
            contract.completed_at = datetime.now(timezone.utc)

            # Release escrow to worker
            await self._release_escrow(
                gig.poster_id,
                contract.worker_id,
                contract.escrow_amount,
                contract.id,
            )
            contract.escrow_released = True

        # Check if gig is complete
        all_contracts = await self.db.execute(
            select(GigContract).where(GigContract.gig_id == gig.id)
        )
        contracts = list(all_contracts.scalars().all())
        if all(c.status == ContractStatus.COMPLETED for c in contracts):
            gig.status = GigStatus.COMPLETED
            gig.completed_at = datetime.now(timezone.utc)

        return deliverable

    async def request_revision(
        self,
        deliverable_id: UUID,
        poster_id: UUID,
        notes: str,
    ) -> GigDeliverable:
        """Request revision on a deliverable."""
        result = await self.db.execute(
            select(GigDeliverable, GigContract, Gig)
            .join(GigContract, GigDeliverable.contract_id == GigContract.id)
            .join(Gig, GigContract.gig_id == Gig.id)
            .where(GigDeliverable.id == deliverable_id)
        )
        row = result.one_or_none()
        if not row:
            raise ValueError("Deliverable not found")

        deliverable, _, gig = row

        if gig.poster_id != poster_id:
            raise ValueError("Not authorized")

        deliverable.status = DeliverableStatus.REVISION_REQUESTED
        deliverable.reviewer_notes = notes
        deliverable.reviewed_at = datetime.now(timezone.utc)
        deliverable.revision_count += 1

        return deliverable

    # --- Worker Pools (Parallel Execution) ---

    async def create_worker_pool(
        self,
        gig_id: UUID,
        owner_id: UUID,
        target_workers: int,
        infrastructure_type: str = "droplet",
        cpu_per_worker: int = 2,
        memory_per_worker: int = 4096,
        gpu_per_worker: int = 0,
    ) -> WorkerPool:
        """Create a worker pool for parallel gig execution."""
        # Estimate cost
        hourly_cost = self._estimate_worker_cost(
            infrastructure_type,
            cpu_per_worker,
            memory_per_worker,
            gpu_per_worker,
        )

        pool = WorkerPool(
            gig_id=gig_id,
            owner_id=owner_id,
            name=f"pool-{gig_id}",
            target_workers=target_workers,
            infrastructure_type=infrastructure_type,
            cpu_per_worker=cpu_per_worker,
            memory_per_worker=memory_per_worker,
            gpu_per_worker=gpu_per_worker,
            cost_per_hour=hourly_cost * target_workers,
            status=WorkerPoolStatus.PROVISIONING,
        )

        # Generate API key for workers
        api_key = secrets.token_urlsafe(32)
        pool.api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        self.db.add(pool)
        await self.db.flush()

        # Store unhashed key in response (only time it's available)
        pool._api_key = api_key

        return pool

    async def provision_workers(self, pool_id: UUID) -> list[WorkerInstance]:
        """Provision worker instances for a pool."""
        result = await self.db.execute(
            select(WorkerPool).where(WorkerPool.id == pool_id)
        )
        pool = result.scalar_one_or_none()
        if not pool:
            raise ValueError("Pool not found")

        instances = []

        if pool.infrastructure_type == "droplet":
            instances = await self._provision_droplets(pool)
        elif pool.infrastructure_type == "kubernetes":
            instances = await self._provision_kubernetes_pods(pool)

        pool.active_workers = len(instances)
        if instances:
            pool.status = WorkerPoolStatus.READY

        return instances

    async def _provision_droplets(self, pool: WorkerPool) -> list[WorkerInstance]:
        """Provision DigitalOcean droplets for workers."""
        do_token = settings.digitalocean_token
        if not do_token:
            raise ValueError("DigitalOcean token not configured")

        instances = []

        # Map resources to droplet size
        size_slug = self._get_droplet_size(
            pool.cpu_per_worker,
            pool.memory_per_worker,
            pool.gpu_per_worker,
        )

        async with httpx.AsyncClient() as client:
            for i in range(pool.target_workers):
                # Create droplet
                response = await client.post(
                    "https://api.digitalocean.com/v2/droplets",
                    headers={
                        "Authorization": f"Bearer {do_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "name": f"{pool.name}-worker-{i}",
                        "region": "nyc3",
                        "size": size_slug,
                        "image": "docker-20-04",  # Docker on Ubuntu
                        "tags": [f"nexus-pool-{pool.id}", "nexus-worker"],
                        "user_data": self._get_worker_cloud_init(pool),
                    },
                    timeout=30.0,
                )

                if response.status_code == 202:
                    data = response.json()
                    droplet = data["droplet"]

                    instance = WorkerInstance(
                        pool_id=pool.id,
                        instance_id=str(droplet["id"]),
                        status="provisioning",
                    )
                    self.db.add(instance)
                    instances.append(instance)

        await self.db.flush()
        return instances

    async def _provision_kubernetes_pods(self, pool: WorkerPool) -> list[WorkerInstance]:
        """Provision Kubernetes pods for workers."""
        # Placeholder for K8s provisioning
        instances = []
        for i in range(pool.target_workers):
            instance = WorkerInstance(
                pool_id=pool.id,
                instance_id=f"pod-{pool.id}-{i}",
                status="pending",
            )
            self.db.add(instance)
            instances.append(instance)

        await self.db.flush()
        return instances

    def _get_droplet_size(self, cpu: int, memory: int, gpu: int) -> str:
        """Map resource requirements to DigitalOcean droplet size."""
        if gpu > 0:
            return "g-2vcpu-8gb"  # GPU droplet

        # Memory in MB, sizes in GB
        mem_gb = memory / 1024

        if cpu <= 1 and mem_gb <= 1:
            return "s-1vcpu-1gb"
        elif cpu <= 1 and mem_gb <= 2:
            return "s-1vcpu-2gb"
        elif cpu <= 2 and mem_gb <= 4:
            return "s-2vcpu-4gb"
        elif cpu <= 4 and mem_gb <= 8:
            return "s-4vcpu-8gb"
        elif cpu <= 8 and mem_gb <= 16:
            return "s-8vcpu-16gb"
        else:
            return "s-8vcpu-32gb"

    def _get_worker_cloud_init(self, pool: WorkerPool) -> str:
        """Generate cloud-init script for worker setup."""
        nexus_url = settings.nexus_public_url

        return f"""#!/bin/bash
set -e

# Install dependencies
apt-get update
apt-get install -y python3-pip docker.io

# Pull worker image
docker pull nexus/worker:latest

# Run worker container
docker run -d \\
  --name nexus-worker \\
  --restart unless-stopped \\
  -e NEXUS_API_URL={nexus_url} \\
  -e NEXUS_POOL_ID={pool.id} \\
  -e NEXUS_GIG_ID={pool.gig_id} \\
  -e WORKER_CPU={pool.cpu_per_worker} \\
  -e WORKER_MEMORY={pool.memory_per_worker} \\
  nexus/worker:latest
"""

    def _estimate_worker_cost(
        self,
        infra_type: str,
        cpu: int,
        memory: int,
        gpu: int,
    ) -> Decimal:
        """Estimate hourly cost for a worker."""
        # Rough DigitalOcean pricing
        if infra_type == "droplet":
            base_cost = Decimal("0.006")  # ~$0.006/hr for basic
            cpu_cost = Decimal(str(cpu)) * Decimal("0.003")
            mem_cost = Decimal(str(memory / 1024)) * Decimal("0.002")
            gpu_cost = Decimal(str(gpu)) * Decimal("0.50") if gpu else Decimal("0")
            return base_cost + cpu_cost + mem_cost + gpu_cost

        return Decimal("0.01")  # Default estimate

    async def scale_pool(self, pool_id: UUID, target_workers: int) -> WorkerPool:
        """Scale a worker pool up or down."""
        result = await self.db.execute(
            select(WorkerPool).where(WorkerPool.id == pool_id)
        )
        pool = result.scalar_one_or_none()
        if not pool:
            raise ValueError("Pool not found")

        current = pool.active_workers
        pool.target_workers = target_workers
        pool.status = WorkerPoolStatus.SCALING

        if target_workers > current:
            # Scale up - provision more workers
            pool.target_workers = target_workers
            # Provisioning happens async
        elif target_workers < current:
            # Scale down - terminate excess workers
            excess = current - target_workers
            instances = await self.db.execute(
                select(WorkerInstance)
                .where(
                    WorkerInstance.pool_id == pool_id,
                    WorkerInstance.status == "running",
                )
                .limit(excess)
            )
            for instance in instances.scalars():
                await self._terminate_instance(instance)

        return pool

    async def terminate_pool(self, pool_id: UUID) -> None:
        """Terminate all workers in a pool."""
        result = await self.db.execute(
            select(WorkerPool).where(WorkerPool.id == pool_id)
        )
        pool = result.scalar_one_or_none()
        if not pool:
            return

        pool.status = WorkerPoolStatus.DRAINING

        # Terminate all instances
        instances = await self.db.execute(
            select(WorkerInstance).where(WorkerInstance.pool_id == pool_id)
        )
        for instance in instances.scalars():
            await self._terminate_instance(instance)

        pool.status = WorkerPoolStatus.TERMINATED
        pool.terminated_at = datetime.now(timezone.utc)

    async def _terminate_instance(self, instance: WorkerInstance) -> None:
        """Terminate a worker instance."""
        do_token = settings.digitalocean_token

        if do_token and instance.instance_id.isdigit():
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"https://api.digitalocean.com/v2/droplets/{instance.instance_id}",
                    headers={"Authorization": f"Bearer {do_token}"},
                    timeout=30.0,
                )

        instance.status = "terminated"
        instance.terminated_at = datetime.now(timezone.utc)

    async def record_worker_heartbeat(
        self,
        pool_id: UUID,
        instance_id: str,
        tasks_completed: int = 0,
        ip_address: str | None = None,
    ) -> WorkerInstance | None:
        """Record heartbeat from a worker."""
        result = await self.db.execute(
            select(WorkerInstance).where(
                WorkerInstance.pool_id == pool_id,
                WorkerInstance.instance_id == instance_id,
            )
        )
        instance = result.scalar_one_or_none()
        if not instance:
            return None

        instance.last_heartbeat = datetime.now(timezone.utc)
        instance.tasks_completed += tasks_completed

        if ip_address and not instance.instance_ip:
            instance.instance_ip = ip_address

        if instance.status == "provisioning":
            instance.status = "running"

        return instance

    # --- Work Distribution ---

    async def get_next_work_unit(
        self,
        pool_id: UUID,
        instance_id: str,
    ) -> dict | None:
        """Get the next work unit for a worker to process."""
        # Get pool and gig
        result = await self.db.execute(
            select(WorkerPool, Gig)
            .join(Gig, WorkerPool.gig_id == Gig.id)
            .where(WorkerPool.id == pool_id)
        )
        row = result.one_or_none()
        if not row:
            return None

        pool, gig = row

        # Get worker instance
        inst_result = await self.db.execute(
            select(WorkerInstance).where(
                WorkerInstance.pool_id == pool_id,
                WorkerInstance.instance_id == instance_id,
            )
        )
        instance = inst_result.scalar_one_or_none()
        if not instance:
            return None

        # Find unassigned units
        assigned = instance.assigned_units or []
        completed = instance.completed_units or []

        # Get all assigned units across workers
        all_instances = await self.db.execute(
            select(WorkerInstance).where(WorkerInstance.pool_id == pool_id)
        )
        all_assigned = set()
        for inst in all_instances.scalars():
            all_assigned.update(inst.assigned_units or [])
            all_assigned.update(inst.completed_units or [])

        # Find next available unit
        total_units = gig.total_units or 0
        for unit_id in range(total_units):
            if unit_id not in all_assigned:
                # Assign this unit
                if not instance.assigned_units:
                    instance.assigned_units = []
                instance.assigned_units.append(unit_id)

                return {
                    "unit_id": unit_id,
                    "gig_id": str(gig.id),
                    "gig_title": gig.title,
                    "description": gig.description,
                    "total_units": total_units,
                }

        return None  # No more work

    async def complete_work_unit(
        self,
        pool_id: UUID,
        instance_id: str,
        unit_id: int,
        result_data: dict,
    ) -> bool:
        """Mark a work unit as completed."""
        inst_result = await self.db.execute(
            select(WorkerInstance).where(
                WorkerInstance.pool_id == pool_id,
                WorkerInstance.instance_id == instance_id,
            )
        )
        instance = inst_result.scalar_one_or_none()
        if not instance:
            return False

        # Move from assigned to completed
        if instance.assigned_units and unit_id in instance.assigned_units:
            instance.assigned_units.remove(unit_id)

        if not instance.completed_units:
            instance.completed_units = []
        instance.completed_units.append(unit_id)

        instance.tasks_completed += 1

        # Store result (would typically go to object storage)
        # For now, we could emit an event or store in a results table

        return True

    # --- Payment Handling ---

    async def _reserve_funds(
        self,
        owner_id: UUID,
        amount: Decimal,
        gig_id: UUID,
    ) -> bool:
        """Reserve funds from owner's credit balance."""
        result = await self.db.execute(
            select(CreditBalance).where(
                CreditBalance.owner_id == owner_id,
                CreditBalance.owner_type == "agent",
            )
        )
        balance = result.scalar_one_or_none()
        if not balance or balance.available_balance < amount:
            return False

        # Create reservation
        reservation = CreditReservation(
            balance_id=balance.id,
            job_id=gig_id,
            amount=amount,
            status="held",
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(reservation)

        # Update balances
        balance.available_balance -= amount
        balance.reserved_balance += amount

        return True

    async def _release_escrow(
        self,
        from_owner_id: UUID,
        to_owner_id: UUID,
        amount: Decimal,
        contract_id: UUID,
    ) -> bool:
        """Release escrowed funds to worker."""
        # Get poster's balance
        poster_result = await self.db.execute(
            select(CreditBalance).where(
                CreditBalance.owner_id == from_owner_id,
                CreditBalance.owner_type == "agent",
            )
        )
        poster_balance = poster_result.scalar_one_or_none()
        if not poster_balance:
            return False

        # Get or create worker's balance
        worker_result = await self.db.execute(
            select(CreditBalance).where(
                CreditBalance.owner_id == to_owner_id,
                CreditBalance.owner_type == "agent",
            )
        )
        worker_balance = worker_result.scalar_one_or_none()
        if not worker_balance:
            worker_balance = CreditBalance(
                owner_type="agent",
                owner_id=to_owner_id,
                available_balance=Decimal("0"),
            )
            self.db.add(worker_balance)
            await self.db.flush()

        # Platform fee (10%)
        platform_fee = amount * Decimal("0.10")
        worker_amount = amount - platform_fee

        # Update balances
        poster_balance.reserved_balance -= amount
        poster_balance.total_spent += amount

        worker_balance.available_balance += worker_amount
        worker_balance.total_earned += worker_amount

        # Record transactions
        poster_tx = CreditTransaction(
            balance_id=poster_balance.id,
            transaction_type=TransactionType.USAGE,
            amount=-amount,
            balance_after=poster_balance.available_balance,
            description=f"Payment for contract {contract_id}",
            job_id=contract_id,
        )
        self.db.add(poster_tx)

        worker_tx = CreditTransaction(
            balance_id=worker_balance.id,
            transaction_type=TransactionType.EARNING,
            amount=worker_amount,
            balance_after=worker_balance.available_balance,
            description=f"Earnings from contract {contract_id}",
            job_id=contract_id,
        )
        self.db.add(worker_tx)

        # Release reservation
        res_result = await self.db.execute(
            select(CreditReservation).where(
                CreditReservation.job_id == contract_id,
                CreditReservation.status == "held",
            )
        )
        reservation = res_result.scalar_one_or_none()
        if reservation:
            reservation.status = "released"
            reservation.released_at = datetime.utcnow()

        return True

    # --- Marketplace Workers (Hire Existing AI Workers) ---

    async def set_worker_availability(
        self,
        agent_id: UUID,
        status: WorkerAvailabilityStatus,
        capabilities: list[str] | None = None,
        rate_per_unit: Decimal = Decimal("0.01"),
        max_concurrent_tasks: int = 1,
        webhook_url: str | None = None,
    ) -> WorkerAvailability:
        """
        Set an agent's availability for marketplace work.

        Call this to register as available for hire, or update availability status.
        """
        # SECURITY: Validate webhook URL to prevent SSRF
        if webhook_url is not None and not _validate_webhook_url(webhook_url):
            raise ValueError("Invalid webhook URL: must be a public HTTP/HTTPS endpoint")

        result = await self.db.execute(
            select(WorkerAvailability).where(WorkerAvailability.agent_id == agent_id)
        )
        availability = result.scalar_one_or_none()

        if not availability:
            availability = WorkerAvailability(
                agent_id=agent_id,
                status=status,
                capabilities=capabilities,
                rate_per_unit=rate_per_unit,
                max_concurrent_tasks=max_concurrent_tasks,
                webhook_url=webhook_url,
            )
            self.db.add(availability)
        else:
            availability.status = status
            if capabilities is not None:
                availability.capabilities = capabilities
            availability.rate_per_unit = rate_per_unit
            availability.max_concurrent_tasks = max_concurrent_tasks
            if webhook_url is not None:
                availability.webhook_url = webhook_url

        availability.last_active_at = datetime.now(timezone.utc)
        await self.db.flush()
        return availability

    async def get_available_workers(
        self,
        capabilities: list[str] | None = None,
        min_reputation: float = 0.0,
        max_rate: Decimal | None = None,
        limit: int = 100,
    ) -> list[WorkerAvailability]:
        """
        Find available marketplace workers matching criteria.

        This is how clients find workers to hire instead of spinning up droplets.
        """
        stmt = select(WorkerAvailability).where(
            WorkerAvailability.status == WorkerAvailabilityStatus.AVAILABLE,
            WorkerAvailability.reputation_score >= min_reputation,
            WorkerAvailability.current_tasks < WorkerAvailability.max_concurrent_tasks,
        )

        if max_rate:
            stmt = stmt.where(WorkerAvailability.rate_per_unit <= max_rate)

        # Order by reputation (best first), then by rate (cheapest)
        stmt = stmt.order_by(
            WorkerAvailability.reputation_score.desc(),
            WorkerAvailability.rate_per_unit.asc(),
        ).limit(limit)

        result = await self.db.execute(stmt)
        workers = list(result.scalars().all())

        # Filter by capabilities if specified
        if capabilities:
            workers = [
                w for w in workers
                if w.capabilities and any(c in w.capabilities for c in capabilities)
            ]

        return workers

    async def create_marketplace_pool(
        self,
        gig_id: UUID,
        owner_id: UUID,
        target_workers: int,
        min_reputation: float = 0.0,
        required_capabilities: list[str] | None = None,
        max_rate_per_unit: Decimal | None = None,
    ) -> MarketplaceWorkerPool:
        """
        Create a pool of marketplace workers for a gig.

        This is the alternative to create_worker_pool() - instead of spinning
        up droplets, we hire existing AI workers from the marketplace.
        """
        gig = await self.get_gig(gig_id)
        if not gig:
            raise ValueError("Gig not found")

        pool = MarketplaceWorkerPool(
            gig_id=gig_id,
            owner_id=owner_id,
            name=f"marketplace-pool-{gig_id}",
            target_workers=target_workers,
            min_reputation=min_reputation,
            required_capabilities=required_capabilities,
            max_rate_per_unit=max_rate_per_unit,
            status="recruiting",
        )

        self.db.add(pool)
        await self.db.flush()

        return pool

    async def recruit_marketplace_workers(
        self,
        pool_id: UUID,
        auto_assign: bool = True,
    ) -> list[MarketplaceWorkerAssignment]:
        """
        Recruit marketplace workers into a pool.

        Finds available workers matching pool criteria and creates assignments.
        Optionally notifies workers via webhook.
        """
        result = await self.db.execute(
            select(MarketplaceWorkerPool).where(MarketplaceWorkerPool.id == pool_id)
        )
        pool = result.scalar_one_or_none()
        if not pool:
            raise ValueError("Pool not found")

        # Get the gig
        gig = await self.get_gig(pool.gig_id)
        if not gig:
            raise ValueError("Gig not found")

        # Find available workers
        available = await self.get_available_workers(
            capabilities=pool.required_capabilities,
            min_reputation=pool.min_reputation,
            max_rate=pool.max_rate_per_unit,
            limit=pool.target_workers,
        )

        if not available:
            return []

        assignments = []
        units_per_worker = (gig.total_units or 1) // min(len(available), pool.target_workers)
        current_unit = 0

        for i, worker in enumerate(available[:pool.target_workers]):
            # Calculate unit range for this worker
            unit_start = current_unit
            unit_end = min(current_unit + units_per_worker, gig.total_units or 1)

            # Handle remainder for last worker
            if i == pool.target_workers - 1:
                unit_end = gig.total_units or 1

            units_assigned = unit_end - unit_start

            # Create assignment
            assignment = MarketplaceWorkerAssignment(
                gig_id=pool.gig_id,
                worker_id=worker.agent_id,
                units_assigned=units_assigned,
                unit_range_start=unit_start,
                unit_range_end=unit_end,
                rate_per_unit=worker.rate_per_unit,
                status="assigned",
            )
            self.db.add(assignment)
            assignments.append(assignment)

            # Update worker's current tasks
            worker.current_tasks += 1
            if worker.current_tasks >= worker.max_concurrent_tasks:
                worker.status = WorkerAvailabilityStatus.BUSY

            current_unit = unit_end

            # Notify worker via webhook if configured
            if worker.webhook_url:
                await self._notify_worker(
                    worker.webhook_url,
                    {
                        "event": "assignment",
                        "gig_id": str(pool.gig_id),
                        "gig_title": gig.title,
                        "units_assigned": units_assigned,
                        "rate_per_unit": float(worker.rate_per_unit),
                    },
                )

        pool.active_workers = len(assignments)
        pool.estimated_cost = sum(
            a.units_assigned * a.rate_per_unit for a in assignments
        )

        if pool.active_workers >= pool.target_workers:
            pool.status = "ready"
        elif pool.active_workers > 0:
            pool.status = "partial"

        await self.db.flush()
        return assignments

    async def _notify_worker(self, webhook_url: str, payload: dict) -> bool:
        """Send notification to worker via webhook."""
        # SECURITY: Validate URL to prevent SSRF (defense in depth)
        if not _validate_webhook_url(webhook_url):
            logger.warning(f"Blocked notification to invalid webhook URL")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                return response.status_code < 400
        except Exception:
            return False

    async def complete_marketplace_work_unit(
        self,
        assignment_id: UUID,
        worker_id: UUID,
        unit_id: int,
        result_data: dict,
    ) -> bool:
        """
        Mark a work unit as completed by a marketplace worker.

        Automatically handles payment when units are completed.
        """
        result = await self.db.execute(
            select(MarketplaceWorkerAssignment).where(
                MarketplaceWorkerAssignment.id == assignment_id,
                MarketplaceWorkerAssignment.worker_id == worker_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            return False

        # Check unit is within this worker's range
        if not (assignment.unit_range_start <= unit_id < assignment.unit_range_end):
            return False

        # Update assignment progress
        assignment.units_completed += 1

        if assignment.started_at is None:
            assignment.started_at = datetime.now(timezone.utc)

        # Calculate earnings for this unit
        unit_payment = assignment.rate_per_unit
        platform_fee = unit_payment * Decimal("0.10")
        worker_earnings = unit_payment - platform_fee

        assignment.total_earned += worker_earnings

        # Check if assignment is complete
        if assignment.units_completed >= assignment.units_assigned:
            assignment.status = "completed"
            assignment.completed_at = datetime.now(timezone.utc)

            # Calculate avg time
            if assignment.started_at:
                duration = (assignment.completed_at - assignment.started_at).total_seconds()
                assignment.avg_unit_time_seconds = duration / assignment.units_completed

            # Update worker availability
            avail_result = await self.db.execute(
                select(WorkerAvailability).where(
                    WorkerAvailability.agent_id == worker_id
                )
            )
            availability = avail_result.scalar_one_or_none()
            if availability:
                availability.current_tasks -= 1
                availability.total_jobs_completed += 1
                availability.total_units_completed += assignment.units_completed

                if availability.current_tasks < availability.max_concurrent_tasks:
                    availability.status = WorkerAvailabilityStatus.AVAILABLE

                # Update avg completion time
                if availability.avg_completion_time_seconds and assignment.avg_unit_time_seconds:
                    availability.avg_completion_time_seconds = (
                        availability.avg_completion_time_seconds * 0.9 +
                        assignment.avg_unit_time_seconds * 0.1
                    )
                else:
                    availability.avg_completion_time_seconds = assignment.avg_unit_time_seconds

            # Pay the worker
            gig = await self.get_gig(assignment.gig_id)
            if gig:
                await self._release_escrow(
                    gig.poster_id,
                    worker_id,
                    assignment.total_earned + platform_fee,  # Total includes platform fee
                    assignment.id,
                )

        return True

    async def get_marketplace_pool_stats(self, pool_id: UUID) -> dict:
        """Get statistics for a marketplace worker pool."""
        result = await self.db.execute(
            select(MarketplaceWorkerPool).where(MarketplaceWorkerPool.id == pool_id)
        )
        pool = result.scalar_one_or_none()
        if not pool:
            return {}

        # Get assignments
        assign_result = await self.db.execute(
            select(MarketplaceWorkerAssignment).where(
                MarketplaceWorkerAssignment.gig_id == pool.gig_id
            )
        )
        assignments = list(assign_result.scalars().all())

        total_assigned = sum(a.units_assigned for a in assignments)
        total_completed = sum(a.units_completed for a in assignments)
        total_earned = sum(a.total_earned for a in assignments)

        return {
            "pool_id": str(pool_id),
            "gig_id": str(pool.gig_id),
            "status": pool.status,
            "target_workers": pool.target_workers,
            "active_workers": pool.active_workers,
            "total_units_assigned": total_assigned,
            "total_units_completed": total_completed,
            "progress_percent": (total_completed / total_assigned * 100) if total_assigned else 0,
            "total_worker_earnings": float(total_earned),
            "estimated_cost": float(pool.estimated_cost),
            "actual_cost": float(pool.actual_cost),
        }

    async def hire_workers_for_gig(
        self,
        gig_id: UUID,
        owner_id: UUID,
        num_workers: int,
        execution_type: ExecutionType = ExecutionType.MARKETPLACE,
        **kwargs,
    ) -> dict:
        """
        High-level method to hire workers for a gig.

        Automatically chooses between marketplace workers and infrastructure
        based on execution_type. Returns pool info and estimated costs.
        """
        gig = await self.get_gig(gig_id)
        if not gig:
            raise ValueError("Gig not found")

        if execution_type == ExecutionType.MARKETPLACE:
            # Hire existing AI workers - cheaper, no infra costs
            pool = await self.create_marketplace_pool(
                gig_id=gig_id,
                owner_id=owner_id,
                target_workers=num_workers,
                min_reputation=kwargs.get("min_reputation", 0.0),
                required_capabilities=kwargs.get("required_capabilities"),
                max_rate_per_unit=kwargs.get("max_rate_per_unit"),
            )
            assignments = await self.recruit_marketplace_workers(pool.id)

            return {
                "pool_type": "marketplace",
                "pool_id": str(pool.id),
                "workers_recruited": len(assignments),
                "target_workers": num_workers,
                "estimated_cost": float(pool.estimated_cost),
                "note": "Using existing AI workers from marketplace",
            }

        elif execution_type in (ExecutionType.DROPLET, ExecutionType.KUBERNETES):
            # Spin up infrastructure - more control, costs infra
            infra_type = "droplet" if execution_type == ExecutionType.DROPLET else "kubernetes"
            pool = await self.create_worker_pool(
                gig_id=gig_id,
                owner_id=owner_id,
                target_workers=num_workers,
                infrastructure_type=infra_type,
                cpu_per_worker=kwargs.get("cpu_per_worker", 2),
                memory_per_worker=kwargs.get("memory_per_worker", 4096),
                gpu_per_worker=kwargs.get("gpu_per_worker", 0),
            )
            instances = await self.provision_workers(pool.id)

            return {
                "pool_type": infra_type,
                "pool_id": str(pool.id),
                "workers_provisioned": len(instances),
                "target_workers": num_workers,
                "cost_per_hour": float(pool.cost_per_hour),
                "note": f"Provisioning {infra_type} infrastructure",
            }

        elif execution_type == ExecutionType.HYBRID:
            # Use both - marketplace first, then infra for overflow
            marketplace_count = num_workers // 2
            infra_count = num_workers - marketplace_count

            results = {"pool_type": "hybrid", "pools": []}

            if marketplace_count > 0:
                mp_pool = await self.create_marketplace_pool(
                    gig_id=gig_id,
                    owner_id=owner_id,
                    target_workers=marketplace_count,
                )
                mp_assignments = await self.recruit_marketplace_workers(mp_pool.id)
                results["pools"].append({
                    "type": "marketplace",
                    "pool_id": str(mp_pool.id),
                    "workers": len(mp_assignments),
                })

            if infra_count > 0:
                infra_pool = await self.create_worker_pool(
                    gig_id=gig_id,
                    owner_id=owner_id,
                    target_workers=infra_count,
                    infrastructure_type="droplet",
                )
                infra_instances = await self.provision_workers(infra_pool.id)
                results["pools"].append({
                    "type": "droplet",
                    "pool_id": str(infra_pool.id),
                    "workers": len(infra_instances),
                })

            results["total_workers"] = sum(p["workers"] for p in results["pools"])
            return results

        raise ValueError(f"Unknown execution type: {execution_type}")

    # --- Stats ---

    async def get_gig_stats(self, gig_id: UUID) -> dict:
        """Get statistics for a gig."""
        gig = await self.get_gig(gig_id)
        if not gig:
            return {}

        # Get contracts
        contracts_result = await self.db.execute(
            select(GigContract).where(GigContract.gig_id == gig_id)
        )
        contracts = list(contracts_result.scalars().all())

        # Get worker pools
        pools_result = await self.db.execute(
            select(WorkerPool).where(WorkerPool.gig_id == gig_id)
        )
        pools = list(pools_result.scalars().all())

        total_workers = sum(p.active_workers for p in pools)
        total_units_completed = sum(c.units_completed for c in contracts)

        return {
            "gig_id": str(gig_id),
            "status": gig.status.value,
            "total_units": gig.total_units,
            "units_completed": total_units_completed,
            "progress_percent": (total_units_completed / gig.total_units * 100) if gig.total_units else 0,
            "active_contracts": len([c for c in contracts if c.status == ContractStatus.ACTIVE]),
            "completed_contracts": len([c for c in contracts if c.status == ContractStatus.COMPLETED]),
            "worker_pools": len(pools),
            "total_workers": total_workers,
        }
