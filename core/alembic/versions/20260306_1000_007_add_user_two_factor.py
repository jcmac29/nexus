"""Add user two-factor authentication table.

Revision ID: 007_add_user_two_factor
Revises: 006_add_promotional_balance
Create Date: 2026-03-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_two_factor',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False, index=True),
        # TOTP secret (encrypted)
        sa.Column('totp_secret_encrypted', sa.Text(), nullable=False),
        # Backup codes (hashed, one-time use)
        sa.Column('backup_codes', ARRAY(sa.String(64)), server_default='{}', nullable=False),
        # Status flags
        sa.Column('is_enabled', sa.Boolean(), default=False, server_default='false', nullable=False),
        sa.Column('is_verified', sa.Boolean(), default=False, server_default='false', nullable=False),
        # Timestamps
        sa.Column('enabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('user_two_factor')
