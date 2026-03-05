"""Credit routes - API endpoints for prepaid balance system."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.credits.service import CreditService, InsufficientCreditsError
from nexus.credits.models import TransactionType
from nexus.identity.models import Agent

router = APIRouter(prefix="/credits", tags=["credits"])
logger = logging.getLogger(__name__)


def _verify_ownership(
    owner_type: str,
    owner_id: UUID,
    agent: Agent,
) -> None:
    """Verify the requesting agent has access to this balance."""
    # Agents can only access their own balance
    if owner_type == "agent" and owner_id != agent.id:
        logger.warning(
            f"Unauthorized credit access attempt: agent {agent.id} tried to access {owner_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="You can only access your own balance"
        )


# --- Request/Response Models ---

class BalanceResponse(BaseModel):
    available_balance: float
    pending_balance: float
    reserved_balance: float
    total_balance: float
    total_earned: float
    total_spent: float
    currency: str


class AddCreditsRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount of credits to add")
    payment_method_id: Optional[str] = None


class TransferRequest(BaseModel):
    to_owner_type: str
    to_owner_id: UUID
    amount: float = Field(..., gt=0)
    description: Optional[str] = None


class PayoutRequest(BaseModel):
    amount: float = Field(..., ge=10, description="Minimum $10 payout")


class TransactionResponse(BaseModel):
    id: str
    type: str
    amount: float
    balance_after: float
    description: Optional[str]
    status: str
    created_at: str


class PackageResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    credit_amount: float
    bonus_credits: float
    total_credits: float
    price: float
    currency: str


# --- Endpoints ---

@router.get("/balance/{owner_type}/{owner_id}", response_model=BalanceResponse)
async def get_balance(
    owner_type: str,
    owner_id: UUID,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get credit balance for an owner. Requires authentication."""
    # SECURITY: Verify ownership
    _verify_ownership(owner_type, owner_id, agent)

    service = CreditService(session)
    balance = await service.get_or_create_balance(owner_type, owner_id)

    return BalanceResponse(
        available_balance=float(balance.available_balance),
        pending_balance=float(balance.pending_balance),
        reserved_balance=float(balance.reserved_balance),
        total_balance=float(balance.total_balance),
        total_earned=float(balance.total_earned),
        total_spent=float(balance.total_spent),
        currency=balance.currency,
    )


@router.post("/balance/{owner_type}/{owner_id}/add")
async def add_credits(
    owner_type: str,
    owner_id: UUID,
    request: AddCreditsRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Add credits to a balance (purchase). Requires authentication."""
    # SECURITY: Verify ownership
    _verify_ownership(owner_type, owner_id, agent)

    service = CreditService(session)

    # In production, this would process payment first
    # For now, just add the credits
    transaction = await service.add_credits(
        owner_type=owner_type,
        owner_id=owner_id,
        amount=Decimal(str(request.amount)),
        transaction_type=TransactionType.PURCHASE,
        description=f"Purchased {request.amount} credits",
    )

    await session.commit()

    return {
        "status": "success",
        "transaction": transaction.to_dict(),
        "message": f"Added {request.amount} credits",
    }


@router.post("/transfer")
async def transfer_credits(
    request: TransferRequest,
    from_owner_type: str = Query(...),
    from_owner_id: UUID = Query(...),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Transfer credits between accounts. Requires authentication."""
    # SECURITY: Verify sender ownership
    _verify_ownership(from_owner_type, from_owner_id, agent)

    service = CreditService(session)

    try:
        from_tx, to_tx = await service.transfer_credits(
            from_owner_type=from_owner_type,
            from_owner_id=from_owner_id,
            to_owner_type=request.to_owner_type,
            to_owner_id=request.to_owner_id,
            amount=Decimal(str(request.amount)),
            description=request.description,
        )

        await session.commit()

        return {
            "status": "success",
            "from_transaction": from_tx.to_dict(),
            "to_transaction": to_tx.to_dict(),
        }

    except InsufficientCreditsError:
        raise HTTPException(status_code=400, detail="Insufficient credits for transfer")


@router.post("/payout/{owner_type}/{owner_id}")
async def request_payout(
    owner_type: str,
    owner_id: UUID,
    request: PayoutRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Request a payout of earnings. Requires authentication."""
    # SECURITY: Verify ownership
    _verify_ownership(owner_type, owner_id, agent)

    service = CreditService(session)

    try:
        transaction = await service.request_payout(
            owner_type=owner_type,
            owner_id=owner_id,
            amount=Decimal(str(request.amount)),
        )

        await session.commit()

        return {
            "status": "pending",
            "transaction": transaction.to_dict(),
            "message": f"Payout of ${request.amount} requested. Processing within 3-5 business days.",
        }

    except InsufficientCreditsError:
        raise HTTPException(status_code=400, detail="Insufficient balance for payout")
    except ValueError:
        raise HTTPException(status_code=400, detail="Minimum payout is $10.00")


@router.get("/transactions/{owner_type}/{owner_id}")
async def get_transactions(
    owner_type: str,
    owner_id: UUID,
    limit: int = Query(50, le=100),
    offset: int = 0,
    transaction_type: Optional[str] = None,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Get transaction history. Requires authentication."""
    # SECURITY: Verify ownership
    _verify_ownership(owner_type, owner_id, agent)

    service = CreditService(session)

    tx_type = None
    if transaction_type:
        try:
            tx_type = TransactionType(transaction_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid transaction type")

    transactions = await service.get_transaction_history(
        owner_type=owner_type,
        owner_id=owner_id,
        limit=limit,
        offset=offset,
        transaction_type=tx_type,
    )

    return {
        "transactions": [tx.to_dict() for tx in transactions],
        "count": len(transactions),
    }


@router.get("/packages", response_model=list[PackageResponse])
async def get_packages(
    session: AsyncSession = Depends(get_db),
):
    """Get available credit packages."""
    service = CreditService(session)
    packages = await service.get_packages()

    return [
        PackageResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            credit_amount=float(p.credit_amount),
            bonus_credits=float(p.bonus_credits),
            total_credits=float(p.credit_amount + p.bonus_credits),
            price=p.price_cents / 100,
            currency=p.currency,
        )
        for p in packages
    ]


@router.post("/packages/{package_id}/purchase")
async def purchase_package(
    package_id: UUID,
    owner_type: str = Query(...),
    owner_id: UUID = Query(...),
    payment_method_id: Optional[str] = None,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Purchase a credit package."""
    from sqlalchemy import select
    from nexus.credits.models import CreditPackage

    # SECURITY: Verify ownership before adding credits
    _verify_ownership(owner_type, owner_id, agent)

    # Get package
    result = await session.execute(
        select(CreditPackage).where(CreditPackage.id == package_id)
    )
    package = result.scalar_one_or_none()

    if not package or not package.is_active:
        raise HTTPException(status_code=404, detail="Package not found")

    # In production, process payment here
    # For now, just add credits

    service = CreditService(session)
    total_credits = package.credit_amount + package.bonus_credits

    transaction = await service.add_credits(
        owner_type=owner_type,
        owner_id=owner_id,
        amount=total_credits,
        transaction_type=TransactionType.PURCHASE,
        description=f"Purchased {package.name} package",
        metadata={
            "package_id": str(package_id),
            "package_name": package.name,
            "credit_amount": float(package.credit_amount),
            "bonus_credits": float(package.bonus_credits),
        },
    )

    await session.commit()

    return {
        "status": "success",
        "credits_added": float(total_credits),
        "transaction": transaction.to_dict(),
    }
