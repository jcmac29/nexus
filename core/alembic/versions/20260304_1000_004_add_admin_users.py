"""Add admin users tables.

Revision ID: 004_add_admin_users
Revises: 003_add_ai_efficiency_modules
Create Date: 2026-03-04 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_add_admin_users"
down_revision: Union[str, None] = "003_add_ai_efficiency_modules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create admin_users table
    op.create_table(
        "admin_users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "role",
            sa.Enum("super_admin", "admin", "viewer", name="adminrole"),
            nullable=False,
        ),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    # Create admin_sessions table
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("admin_id", sa.UUID(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admin_users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_sessions_admin_id", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
    op.execute("DROP TYPE IF EXISTS adminrole")
