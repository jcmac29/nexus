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
    ) -> CreditTransaction:
        """Add credits to a balance."""
        balance = await self.get_or_create_balance(owner_type, owner_id)

        # Update balance
        balance.available_balance += amount
        if transaction_type == TransactionType.PURCHASE:
            balance.total_purchased += amount
        elif transaction_type == TransactionType.EARNING:
            balance.total_earned += amount

        # Record transaction
        transaction = CreditTransaction(
            balance_id=balance.id,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=balance.available_balance,
            description=description or f"Added {amount} credits",
            payment_intent_id=payment_intent_id,
            metadata=metadata or {},
        )
        self.session.add(transaction)

        return transaction

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
        """Deduct credits from a balance."""
        balance = await self.get_or_create_balance(owner_type, owner_id)

        if check_balance and balance.available_balance < amount:
            raise InsufficientCreditsError(
                f"Insufficient credits. Available: {balance.available_balance}, Required: {amount}"
            )

        # Update balance
        balance.available_balance -= amount
        balance.total_spent += amount

        # Record transaction
        transaction = CreditTransaction(
            balance_id=balance.id,
            transaction_type=TransactionType.USAGE,
            amount=-amount,  # Negative for debit
            balance_after=balance.available_balance,
            description=description or f"Used {amount} credits",
            job_id=job_id,
            service_id=service_id,
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
        """Reserve credits for an in-progress job."""
        balance = await self.get_or_create_balance(owner_type, owner_id)

        if balance.available_balance < amount:
            raise InsufficientCreditsError(
                f"Insufficient credits. Available: {balance.available_balance}, Required: {amount}"
            )

        # Move from available to reserved
        balance.available_balance -= amount
        balance.reserved_balance += amount

        # Create reservation
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
        """Transfer credits between accounts."""
        from_balance = await self.get_or_create_balance(from_owner_type, from_owner_id)

        if from_balance.available_balance < amount:
            raise InsufficientCreditsError(
                f"Insufficient credits for transfer"
            )

        to_balance = await self.get_or_create_balance(to_owner_type, to_owner_id)

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
        """Request payout of earnings."""
        balance = await self.get_or_create_balance(owner_type, owner_id)

        if balance.available_balance < amount:
            raise InsufficientCreditsError("Insufficient balance for payout")

        # Minimum payout
        if amount < Decimal("10.00"):
            raise ValueError("Minimum payout is $10.00")

        # Deduct and record
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
