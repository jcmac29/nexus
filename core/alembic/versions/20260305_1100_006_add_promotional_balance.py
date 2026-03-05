"""Add promotional_balance to credit_balances.

Promotional credits are non-withdrawable bonuses (e.g., signup credit)
that can be spent on platform services but cannot be converted to cash.

Revision ID: 006
Revises: 005
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add promotional_balance column to credit_balances
    op.add_column(
        'credit_balances',
        sa.Column('promotional_balance', sa.Numeric(15, 2), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('credit_balances', 'promotional_balance')
