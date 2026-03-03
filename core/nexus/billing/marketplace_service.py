"""Marketplace billing service for platform fees and payouts."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.billing.models import (
    MarketplaceTransaction, MarketplacePayout, PlatformFeeConfig, SellerAccount,
    MarketplaceTransactionType, MarketplaceTransactionStatus, PayoutStatus, Account
)


# Default platform fee: 10%
DEFAULT_PLATFORM_FEE_BPS = 1000  # 10% in basis points


class MarketplaceBillingService:
    """Service for marketplace billing with platform fees."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._stripe = None

    def configure_stripe(self, api_key: str):
        """Configure Stripe for payments."""
        import stripe
        stripe.api_key = api_key
        self._stripe = stripe

    async def get_fee_config(self, seller_account_id: UUID | None = None) -> PlatformFeeConfig | None:
        """Get fee configuration for a seller or default."""
        if seller_account_id:
            result = await self.db.execute(
                select(SellerAccount).where(SellerAccount.account_id == seller_account_id)
            )
            seller = result.scalar_one_or_none()
            if seller and seller.fee_config_id:
                result = await self.db.execute(
                    select(PlatformFeeConfig).where(PlatformFeeConfig.id == seller.fee_config_id)
                )
                return result.scalar_one_or_none()

        # Get default config
        result = await self.db.execute(
            select(PlatformFeeConfig).where(
                and_(
                    PlatformFeeConfig.is_default == True,
                    PlatformFeeConfig.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()

    def calculate_platform_fee(
        self,
        gross_amount_cents: int,
        transaction_type: MarketplaceTransactionType,
        fee_config: PlatformFeeConfig | None = None,
        seller_volume_cents: int = 0,
    ) -> tuple[int, int]:
        """
        Calculate platform fee.

        Returns: (platform_fee_cents, seller_amount_cents)
        """
        # Get fee rate in basis points
        if fee_config:
            if transaction_type == MarketplaceTransactionType.SUBSCRIPTION:
                fee_bps = fee_config.subscription_fee_bps
            elif transaction_type == MarketplaceTransactionType.ONE_TIME:
                fee_bps = fee_config.one_time_fee_bps
            else:
                fee_bps = fee_config.usage_fee_bps

            # Apply volume discount if enabled
            if fee_config.volume_discount_enabled and fee_config.volume_thresholds:
                for threshold_str, discounted_bps in sorted(
                    fee_config.volume_thresholds.items(),
                    key=lambda x: int(x[0]),
                    reverse=True,
                ):
                    if seller_volume_cents >= int(threshold_str):
                        fee_bps = discounted_bps
                        break

            min_fee = fee_config.min_fee_cents
        else:
            fee_bps = DEFAULT_PLATFORM_FEE_BPS
            min_fee = 50  # $0.50 minimum

        # Calculate fee
        calculated_fee = (gross_amount_cents * fee_bps) // 10000
        platform_fee = max(calculated_fee, min_fee)

        # Ensure seller gets at least something
        platform_fee = min(platform_fee, gross_amount_cents - 1)

        seller_amount = gross_amount_cents - platform_fee

        return platform_fee, seller_amount

    async def create_transaction(
        self,
        buyer_account_id: UUID,
        seller_account_id: UUID,
        gross_amount_cents: int,
        transaction_type: MarketplaceTransactionType,
        listing_id: UUID | None = None,
        description: str | None = None,
        buyer_agent_id: UUID | None = None,
        seller_agent_id: UUID | None = None,
        subscription_period_start: datetime | None = None,
        subscription_period_end: datetime | None = None,
        metadata: dict | None = None,
    ) -> MarketplaceTransaction:
        """Create a marketplace transaction with platform fee."""
        # Get seller's fee config
        fee_config = await self.get_fee_config(seller_account_id)

        # Get seller's total volume for volume discounts
        seller_volume = await self._get_seller_volume(seller_account_id)

        # Calculate fees
        platform_fee, seller_amount = self.calculate_platform_fee(
            gross_amount_cents=gross_amount_cents,
            transaction_type=transaction_type,
            fee_config=fee_config,
            seller_volume_cents=seller_volume,
        )

        # Determine fee percentage for record
        fee_percent = (platform_fee * 100) // gross_amount_cents if gross_amount_cents > 0 else 0

        transaction = MarketplaceTransaction(
            buyer_account_id=buyer_account_id,
            buyer_agent_id=buyer_agent_id,
            seller_account_id=seller_account_id,
            seller_agent_id=seller_agent_id,
            listing_id=listing_id,
            transaction_type=transaction_type,
            status=MarketplaceTransactionStatus.PENDING,
            gross_amount_cents=gross_amount_cents,
            platform_fee_cents=platform_fee,
            seller_amount_cents=seller_amount,
            platform_fee_percent=fee_percent,
            description=description,
            subscription_period_start=subscription_period_start,
            subscription_period_end=subscription_period_end,
            metadata_=metadata or {},
        )
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction

    async def process_payment(
        self,
        transaction_id: UUID,
        payment_method_id: str | None = None,
    ) -> MarketplaceTransaction:
        """Process payment for a transaction."""
        result = await self.db.execute(
            select(MarketplaceTransaction).where(MarketplaceTransaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()
        if not transaction:
            raise ValueError("Transaction not found")

        if transaction.status != MarketplaceTransactionStatus.PENDING:
            raise ValueError(f"Transaction is {transaction.status.value}, cannot process")

        # Get buyer's Stripe customer
        result = await self.db.execute(
            select(Account).where(Account.id == transaction.buyer_account_id)
        )
        buyer_account = result.scalar_one_or_none()

        # Get seller's Stripe Connect account
        result = await self.db.execute(
            select(SellerAccount).where(SellerAccount.account_id == transaction.seller_account_id)
        )
        seller = result.scalar_one_or_none()

        if self._stripe and buyer_account and seller and seller.stripe_account_id:
            try:
                # Create payment intent with transfer to seller
                payment_intent = self._stripe.PaymentIntent.create(
                    amount=transaction.gross_amount_cents,
                    currency=transaction.currency,
                    customer=buyer_account.stripe_customer_id,
                    payment_method=payment_method_id,
                    confirm=True,
                    transfer_data={
                        "destination": seller.stripe_account_id,
                        "amount": transaction.seller_amount_cents,  # Seller gets this amount
                    },
                    metadata={
                        "transaction_id": str(transaction.id),
                        "platform_fee": transaction.platform_fee_cents,
                    },
                )

                transaction.stripe_payment_intent_id = payment_intent.id
                if payment_intent.status == "succeeded":
                    transaction.status = MarketplaceTransactionStatus.COMPLETED
                    transaction.stripe_charge_id = payment_intent.latest_charge

                    # Update seller stats
                    seller.total_sales_cents += transaction.gross_amount_cents
                    seller.total_fees_paid_cents += transaction.platform_fee_cents
                    seller.pending_balance_cents += transaction.seller_amount_cents

            except Exception as e:
                transaction.status = MarketplaceTransactionStatus.FAILED
                transaction.metadata_["error"] = str(e)

        else:
            # Without Stripe, just mark as completed (for testing/internal use)
            transaction.status = MarketplaceTransactionStatus.COMPLETED

        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction

    async def _get_seller_volume(self, seller_account_id: UUID) -> int:
        """Get seller's total sales volume in last 12 months."""
        twelve_months_ago = datetime.utcnow() - timedelta(days=365)
        result = await self.db.execute(
            select(func.coalesce(func.sum(MarketplaceTransaction.gross_amount_cents), 0))
            .where(
                and_(
                    MarketplaceTransaction.seller_account_id == seller_account_id,
                    MarketplaceTransaction.status == MarketplaceTransactionStatus.COMPLETED,
                    MarketplaceTransaction.created_at >= twelve_months_ago,
                )
            )
        )
        return result.scalar() or 0

    async def create_seller_account(
        self,
        account_id: UUID,
        payout_schedule: str = "weekly",
        minimum_payout_cents: int = 1000,
    ) -> SellerAccount:
        """Create a seller account for marketplace."""
        # Check if already exists
        result = await self.db.execute(
            select(SellerAccount).where(SellerAccount.account_id == account_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        seller = SellerAccount(
            account_id=account_id,
            payout_schedule=payout_schedule,
            minimum_payout_cents=minimum_payout_cents,
        )
        self.db.add(seller)
        await self.db.commit()
        await self.db.refresh(seller)
        return seller

    async def create_stripe_connect_account(
        self,
        seller_account_id: UUID,
        email: str,
        country: str = "US",
    ) -> str:
        """Create Stripe Connect account for seller."""
        result = await self.db.execute(
            select(SellerAccount).where(SellerAccount.account_id == seller_account_id)
        )
        seller = result.scalar_one_or_none()
        if not seller:
            raise ValueError("Seller account not found")

        if self._stripe:
            account = self._stripe.Account.create(
                type="express",
                country=country,
                email=email,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )
            seller.stripe_account_id = account.id
            await self.db.commit()
            return account.id

        return ""

    async def get_connect_onboarding_link(
        self,
        seller_account_id: UUID,
        return_url: str,
        refresh_url: str,
    ) -> str:
        """Get Stripe Connect onboarding link."""
        result = await self.db.execute(
            select(SellerAccount).where(SellerAccount.account_id == seller_account_id)
        )
        seller = result.scalar_one_or_none()
        if not seller or not seller.stripe_account_id:
            raise ValueError("Seller account not found or not connected")

        if self._stripe:
            link = self._stripe.AccountLink.create(
                account=seller.stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type="account_onboarding",
            )
            return link.url

        return ""

    async def process_payouts(
        self,
        schedule: str = "weekly",  # Process payouts for this schedule
    ) -> list[MarketplacePayout]:
        """Process pending payouts for sellers."""
        # Find sellers due for payout
        result = await self.db.execute(
            select(SellerAccount).where(
                and_(
                    SellerAccount.payout_schedule == schedule,
                    SellerAccount.pending_balance_cents > 0,
                    SellerAccount.is_active == True,
                    SellerAccount.stripe_payouts_enabled == True,
                )
            )
        )
        sellers = result.scalars().all()

        payouts = []
        for seller in sellers:
            if seller.pending_balance_cents < seller.minimum_payout_cents:
                continue

            payout = await self._create_payout(seller)
            if payout:
                payouts.append(payout)

        return payouts

    async def _create_payout(self, seller: SellerAccount) -> MarketplacePayout | None:
        """Create a payout for a seller."""
        # Get unpaid transactions
        result = await self.db.execute(
            select(MarketplaceTransaction).where(
                and_(
                    MarketplaceTransaction.seller_account_id == seller.account_id,
                    MarketplaceTransaction.status == MarketplaceTransactionStatus.COMPLETED,
                    MarketplaceTransaction.payout_id.is_(None),
                )
            )
        )
        transactions = result.scalars().all()

        if not transactions:
            return None

        # Calculate totals
        gross_total = sum(t.gross_amount_cents for t in transactions)
        fees_total = sum(t.platform_fee_cents for t in transactions)
        net_total = sum(t.seller_amount_cents for t in transactions)

        # Create payout record
        payout = MarketplacePayout(
            seller_account_id=seller.account_id,
            status=PayoutStatus.PENDING,
            gross_amount_cents=gross_total,
            platform_fees_cents=fees_total,
            net_amount_cents=net_total,
            transaction_count=len(transactions),
            period_start=min(t.created_at for t in transactions),
            period_end=max(t.created_at for t in transactions),
        )
        self.db.add(payout)
        await self.db.flush()

        # Link transactions to payout
        for t in transactions:
            t.payout_id = payout.id

        # Process via Stripe
        if self._stripe and seller.stripe_account_id:
            try:
                transfer = self._stripe.Transfer.create(
                    amount=net_total,
                    currency="usd",
                    destination=seller.stripe_account_id,
                    metadata={"payout_id": str(payout.id)},
                )
                payout.stripe_transfer_group = transfer.id
                payout.status = PayoutStatus.PROCESSING
                payout.processed_at = datetime.utcnow()
            except Exception as e:
                payout.status = PayoutStatus.FAILED
                payout.failure_reason = str(e)
                payout.failed_at = datetime.utcnow()
        else:
            payout.status = PayoutStatus.COMPLETED
            payout.processed_at = datetime.utcnow()

        # Update seller balance
        seller.pending_balance_cents -= net_total
        seller.total_payouts_cents += net_total

        await self.db.commit()
        await self.db.refresh(payout)
        return payout

    async def get_seller_stats(self, seller_account_id: UUID) -> dict:
        """Get seller statistics."""
        result = await self.db.execute(
            select(SellerAccount).where(SellerAccount.account_id == seller_account_id)
        )
        seller = result.scalar_one_or_none()
        if not seller:
            return {}

        # Get recent transactions
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        result = await self.db.execute(
            select(
                func.count(MarketplaceTransaction.id),
                func.coalesce(func.sum(MarketplaceTransaction.gross_amount_cents), 0),
                func.coalesce(func.sum(MarketplaceTransaction.platform_fee_cents), 0),
                func.coalesce(func.sum(MarketplaceTransaction.seller_amount_cents), 0),
            )
            .where(
                and_(
                    MarketplaceTransaction.seller_account_id == seller_account_id,
                    MarketplaceTransaction.status == MarketplaceTransactionStatus.COMPLETED,
                    MarketplaceTransaction.created_at >= thirty_days_ago,
                )
            )
        )
        row = result.one()

        return {
            "total_sales_cents": seller.total_sales_cents,
            "total_fees_paid_cents": seller.total_fees_paid_cents,
            "total_payouts_cents": seller.total_payouts_cents,
            "pending_balance_cents": seller.pending_balance_cents,
            "last_30_days": {
                "transaction_count": row[0],
                "gross_sales_cents": row[1],
                "platform_fees_cents": row[2],
                "net_earnings_cents": row[3],
            },
            "stripe_connected": seller.stripe_account_id is not None,
            "payouts_enabled": seller.stripe_payouts_enabled,
        }

    async def get_platform_revenue(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        """Get platform revenue from fees."""
        result = await self.db.execute(
            select(
                func.count(MarketplaceTransaction.id),
                func.coalesce(func.sum(MarketplaceTransaction.gross_amount_cents), 0),
                func.coalesce(func.sum(MarketplaceTransaction.platform_fee_cents), 0),
            )
            .where(
                and_(
                    MarketplaceTransaction.status == MarketplaceTransactionStatus.COMPLETED,
                    MarketplaceTransaction.created_at >= start_date,
                    MarketplaceTransaction.created_at <= end_date,
                )
            )
        )
        row = result.one()

        return {
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "transaction_count": row[0],
            "gross_volume_cents": row[1],
            "platform_revenue_cents": row[2],
        }

    async def create_default_fee_config(self) -> PlatformFeeConfig:
        """Create default platform fee configuration."""
        # Check if default exists
        result = await self.db.execute(
            select(PlatformFeeConfig).where(PlatformFeeConfig.is_default == True)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        config = PlatformFeeConfig(
            name="default",
            description="Default platform fee configuration - 10% on all transactions",
            subscription_fee_bps=1000,  # 10%
            one_time_fee_bps=1500,  # 15%
            usage_fee_bps=1000,  # 10%
            min_fee_cents=50,  # $0.50 minimum
            volume_discount_enabled=True,
            volume_thresholds={
                "1000000": 900,   # $10k+ = 9%
                "5000000": 800,   # $50k+ = 8%
                "10000000": 700,  # $100k+ = 7%
            },
            is_default=True,
            is_active=True,
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config
