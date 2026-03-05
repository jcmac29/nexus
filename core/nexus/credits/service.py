"""Credit service - Manages prepaid balances for Nexus."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.credits.models import (
    CreditBalance,
    CreditTransaction,
    CreditPackage,
    CreditReservation,
    TransactionType,
)

if TYPE_CHECKING:
    from uuid import UUID


class InsufficientCreditsError(Exception):
    """Raised when user doesn't have enough credits."""
    pass


class CreditService:
    """Service for managing prepaid credit balances."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_balance(
        self,
        owner_type: str,
        owner_id: "UUID",
    ) -> CreditBalance:
        """Get or create a credit balance for an owner."""
        result = await self.session.execute(
            select(CreditBalance).where(
                CreditBalance.owner_type == owner_type,
                CreditBalance.owner_id == owner_id,
            )
        )
        balance = result.scalar_one_or_none()

        if not balance:
            balance = CreditBalance(
                owner_type=owner_type,
                owner_id=owner_id,
                available_balance=Decimal("0"),
                pending_balance=Decimal("0"),
                reserved_balance=Decimal("0"),
                promotional_balance=Decimal("0"),
            )
            self.session.add(balance)
            await self.session.flush()

        return balance

    async def get_balance(
        self,
        owner_type: str,
        owner_id: "UUID",
    ) -> Optional[CreditBalance]:
        """Get credit balance for an owner."""
        result = await self.session.execute(
            select(CreditBalance).where(
                CreditBalance.owner_type == owner_type,
                CreditBalance.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_credits(
        self,
        owner_type: str,
        owner_id: "UUID",
        amount: Decimal,
        transaction_type: TransactionType = TransactionType.PURCHASE,
        description: str = None,
        payment_intent_id: str = None,
        metadata: dict = None,
        is_promotional: bool = False,
    ) -> CreditTransaction:
        """Add credits to a balance.

        Args:
            is_promotional: If True, credits are added to promotional_balance
                           and cannot be withdrawn (only spent on platform).
        """
        balance = await self.get_or_create_balance(owner_type, owner_id)

        # Update balance - promotional credits go to separate bucket
        if is_promotional:
            balance.promotional_balance += amount
        else:
            balance.available_balance += amount
            if transaction_type == TransactionType.PURCHASE:
                balance.total_purchased += amount
            elif transaction_type == TransactionType.EARNING:
                balance.total_earned += amount

        # Record transaction
        tx_metadata = metadata or {}
        if is_promotional:
            tx_metadata["is_promotional"] = True

        transaction = CreditTransaction(
            balance_id=balance.id,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=balance.spendable_balance,
            description=description or f"Added {amount} credits" + (" (promotional)" if is_promotional else ""),
            payment_intent_id=payment_intent_id,
            metadata_=tx_metadata,
        )
        self.session.add(transaction)

        return transaction

    async def add_promotional_credits(
        self,
        owner_type: str,
        owner_id: "UUID",
        amount: Decimal,
        description: str = None,
    ) -> CreditTransaction:
        """Add non-withdrawable promotional credits (e.g., signup bonus).

        Promotional credits:
        - Can be spent on platform services (hiring AI workers, API usage)
        - Cannot be withdrawn or converted to cash
        - Are used after available balance is depleted
        """
        return await self.add_credits(
            owner_type=owner_type,
            owner_id=owner_id,
            amount=amount,
            transaction_type=TransactionType.BONUS,
            description=description or f"Promotional credit: ${amount}",
            is_promotional=True,
        )

    async def deduct_credits(
        self,
        owner_type: str,
        owner_id: "UUID",
        amount: Decimal,
        description: str = None,
        job_id: "UUID" = None,
        service_id: "UUID" = None,
        check_balance: bool = True,
    ) -> CreditTransaction:
        """Deduct credits from a balance.

        Deduction order:
        1. First use available_balance (withdrawable credits)
        2. Then use promotional_balance (non-withdrawable credits)
        """
        balance = await self.get_or_create_balance(owner_type, owner_id)

        total_spendable = balance.available_balance + balance.promotional_balance

        if check_balance and total_spendable < amount:
            raise InsufficientCreditsError(
                f"Insufficient credits. Spendable: {total_spendable}, Required: {amount}"
            )

        # Deduct from available first, then promotional
        remaining = amount
        from_available = Decimal("0")
        from_promotional = Decimal("0")

        if balance.available_balance >= remaining:
            from_available = remaining
            balance.available_balance -= remaining
        else:
            from_available = balance.available_balance
            remaining -= balance.available_balance
            balance.available_balance = Decimal("0")

            from_promotional = remaining
            balance.promotional_balance -= remaining

        balance.total_spent += amount

        # Record transaction with breakdown
        tx_metadata = {}
        if from_promotional > 0:
            tx_metadata["from_promotional"] = float(from_promotional)
            tx_metadata["from_available"] = float(from_available)

        transaction = CreditTransaction(
            balance_id=balance.id,
            transaction_type=TransactionType.USAGE,
            amount=-amount,  # Negative for debit
            balance_after=balance.spendable_balance,
            description=description or f"Used {amount} credits",
            job_id=job_id,
            service_id=service_id,
            metadata_=tx_metadata if tx_metadata else {},
        )
        self.session.add(transaction)

        return transaction

    async def reserve_credits(
        self,
        owner_type: str,
        owner_id: "UUID",
        amount: Decimal,
        job_id: "UUID",
    ) -> CreditReservation:
        """Reserve credits for an in-progress job.

        Uses SELECT FOR UPDATE to prevent race conditions.
        Reserves from available_balance first, then promotional_balance.
        """
        # First get or create balance (without lock)
        balance = await self.get_or_create_balance(owner_type, owner_id)

        # Now lock the balance row for this transaction
        result = await self.session.execute(
            select(CreditBalance)
            .where(CreditBalance.id == balance.id)
            .with_for_update()  # SECURITY: Lock row to prevent race condition
        )
        balance = result.scalar_one()

        total_spendable = balance.available_balance + balance.promotional_balance
        if total_spendable < amount:
            raise InsufficientCreditsError(
                f"Insufficient credits. Spendable: {total_spendable}, Required: {amount}"
            )

        # Reserve from available first, then promotional
        remaining = amount
        from_available = Decimal("0")
        from_promotional = Decimal("0")

        if balance.available_balance >= remaining:
            from_available = remaining
            balance.available_balance -= remaining
        else:
            from_available = balance.available_balance
            remaining -= balance.available_balance
            balance.available_balance = Decimal("0")

            from_promotional = remaining
            balance.promotional_balance -= remaining

        balance.reserved_balance += amount

        # Create reservation with breakdown
        reservation = CreditReservation(
            balance_id=balance.id,
            job_id=job_id,
            amount=amount,
            status="held",
        )
        self.session.add(reservation)

        return reservation

    async def capture_reservation(
        self,
        reservation_id: "UUID",
        actual_amount: Decimal = None,
        provider_id: "UUID" = None,
    ) -> CreditTransaction:
        """Capture a reservation (job completed)."""
        result = await self.session.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()

        if not reservation or reservation.status != "held":
            raise ValueError("Invalid reservation")

        # Get balance
        result = await self.session.execute(
            select(CreditBalance).where(CreditBalance.id == reservation.balance_id)
        )
        balance = result.scalar_one()

        # Use actual amount or reserved amount
        capture_amount = actual_amount if actual_amount else reservation.amount
        refund_amount = reservation.amount - capture_amount

        # Update balance
        balance.reserved_balance -= reservation.amount
        if refund_amount > 0:
            balance.available_balance += refund_amount
        balance.total_spent += capture_amount

        # Mark reservation as captured
        reservation.status = "captured"
        reservation.released_at = datetime.utcnow()

        # Record transaction
        transaction = CreditTransaction(
            balance_id=balance.id,
            transaction_type=TransactionType.USAGE,
            amount=-capture_amount,
            balance_after=balance.available_balance,
            description=f"Job completed - {capture_amount} credits",
            job_id=reservation.job_id,
            counterparty_id=provider_id,
        )
        self.session.add(transaction)

        # Pay the provider
        if provider_id:
            await self.add_credits(
                owner_type="agent",
                owner_id=provider_id,
                amount=capture_amount * Decimal("0.9"),  # 90% to provider (10% platform fee)
                transaction_type=TransactionType.EARNING,
                description=f"Earned from job {reservation.job_id}",
                metadata={"job_id": str(reservation.job_id)},
            )

        return transaction

    async def release_reservation(
        self,
        reservation_id: "UUID",
    ):
        """Release a reservation (job cancelled)."""
        result = await self.session.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()

        if not reservation or reservation.status != "held":
            raise ValueError("Invalid reservation")

        # Get balance
        result = await self.session.execute(
            select(CreditBalance).where(CreditBalance.id == reservation.balance_id)
        )
        balance = result.scalar_one()

        # Return to available
        balance.reserved_balance -= reservation.amount
        balance.available_balance += reservation.amount

        # Mark as released
        reservation.status = "released"
        reservation.released_at = datetime.utcnow()

    async def transfer_credits(
        self,
        from_owner_type: str,
        from_owner_id: "UUID",
        to_owner_type: str,
        to_owner_id: "UUID",
        amount: Decimal,
        description: str = None,
    ) -> tuple[CreditTransaction, CreditTransaction]:
        """Transfer credits between accounts.

        Uses SELECT FOR UPDATE to prevent race conditions.
        """
        # Get or create balances first
        from_balance = await self.get_or_create_balance(from_owner_type, from_owner_id)
        to_balance = await self.get_or_create_balance(to_owner_type, to_owner_id)

        # Lock both balance rows (in consistent order to prevent deadlocks)
        balance_ids = sorted([from_balance.id, to_balance.id])
        result = await self.session.execute(
            select(CreditBalance)
            .where(CreditBalance.id.in_(balance_ids))
            .with_for_update()  # SECURITY: Lock rows to prevent race condition
            .order_by(CreditBalance.id)
        )
        locked_balances = {b.id: b for b in result.scalars().all()}
        from_balance = locked_balances[from_balance.id]
        to_balance = locked_balances[to_balance.id]

        if from_balance.available_balance < amount:
            raise InsufficientCreditsError(
                f"Insufficient credits for transfer"
            )

        # Deduct from sender
        from_balance.available_balance -= amount
        from_tx = CreditTransaction(
            balance_id=from_balance.id,
            transaction_type=TransactionType.TRANSFER_OUT,
            amount=-amount,
            balance_after=from_balance.available_balance,
            description=description or f"Transfer to {to_owner_id}",
            counterparty_id=to_owner_id,
        )
        self.session.add(from_tx)

        # Add to receiver
        to_balance.available_balance += amount
        to_tx = CreditTransaction(
            balance_id=to_balance.id,
            transaction_type=TransactionType.TRANSFER_IN,
            amount=amount,
            balance_after=to_balance.available_balance,
            description=description or f"Transfer from {from_owner_id}",
            counterparty_id=from_owner_id,
        )
        self.session.add(to_tx)

        return from_tx, to_tx

    async def request_payout(
        self,
        owner_type: str,
        owner_id: "UUID",
        amount: Decimal,
    ) -> CreditTransaction:
        """Request payout of earnings.

        Note: Only available_balance can be withdrawn.
        Promotional credits cannot be withdrawn.
        """
        balance = await self.get_or_create_balance(owner_type, owner_id)

        # Only withdrawable balance (excludes promotional credits)
        if balance.available_balance < amount:
            raise InsufficientCreditsError(
                f"Insufficient withdrawable balance. "
                f"Withdrawable: ${balance.available_balance}, Requested: ${amount}. "
                f"Note: Promotional credits (${balance.promotional_balance}) cannot be withdrawn."
            )

        # Minimum payout
        if amount < Decimal("10.00"):
            raise ValueError("Minimum payout is $10.00")

        # Deduct and record (only from available, not promotional)
        balance.available_balance -= amount
        balance.total_withdrawn += amount

        transaction = CreditTransaction(
            balance_id=balance.id,
            transaction_type=TransactionType.PAYOUT,
            amount=-amount,
            balance_after=balance.available_balance,
            description=f"Payout request for ${amount}",
            status="pending",  # Will be processed by billing system
        )
        self.session.add(transaction)

        return transaction

    async def get_transaction_history(
        self,
        owner_type: str,
        owner_id: "UUID",
        limit: int = 50,
        offset: int = 0,
        transaction_type: TransactionType = None,
    ) -> list[CreditTransaction]:
        """Get transaction history for a balance."""
        balance = await self.get_balance(owner_type, owner_id)
        if not balance:
            return []

        query = (
            select(CreditTransaction)
            .where(CreditTransaction.balance_id == balance.id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if transaction_type:
            query = query.where(CreditTransaction.transaction_type == transaction_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_packages(self, active_only: bool = True) -> list[CreditPackage]:
        """Get available credit packages."""
        query = select(CreditPackage).order_by(CreditPackage.sort_order)
        if active_only:
            query = query.where(CreditPackage.is_active == True)

        result = await self.session.execute(query)
        return list(result.scalars().all())


# Convenience functions
async def get_balance(session: AsyncSession, owner_type: str, owner_id: "UUID") -> Optional[CreditBalance]:
    """Get credit balance."""
    service = CreditService(session)
    return await service.get_balance(owner_type, owner_id)


async def add_credits(
    session: AsyncSession,
    owner_type: str,
    owner_id: "UUID",
    amount: Decimal,
    **kwargs,
) -> CreditTransaction:
    """Add credits to a balance."""
    service = CreditService(session)
    return await service.add_credits(owner_type, owner_id, amount, **kwargs)


async def deduct_credits(
    session: AsyncSession,
    owner_type: str,
    owner_id: "UUID",
    amount: Decimal,
    **kwargs,
) -> CreditTransaction:
    """Deduct credits from a balance."""
    service = CreditService(session)
    return await service.deduct_credits(owner_type, owner_id, amount, **kwargs)


async def transfer_credits(
    session: AsyncSession,
    from_owner_type: str,
    from_owner_id: "UUID",
    to_owner_type: str,
    to_owner_id: "UUID",
    amount: Decimal,
    **kwargs,
) -> tuple[CreditTransaction, CreditTransaction]:
    """Transfer credits between accounts."""
    service = CreditService(session)
    return await service.transfer_credits(
        from_owner_type, from_owner_id,
        to_owner_type, to_owner_id,
        amount, **kwargs
    )


async def add_promotional_credits(
    session: AsyncSession,
    owner_type: str,
    owner_id: "UUID",
    amount: Decimal,
    description: str = None,
) -> CreditTransaction:
    """Add non-withdrawable promotional credits (signup bonus, etc.)."""
    service = CreditService(session)
    return await service.add_promotional_credits(owner_type, owner_id, amount, description)
