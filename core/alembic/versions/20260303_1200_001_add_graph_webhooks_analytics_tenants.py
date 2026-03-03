"""Add graph memory, webhooks, analytics, and tenant models.

Revision ID: 001
Revises: None
Create Date: 2026-03-03 12:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all new tables for roadmap features."""

    # ========================================
    # Graph Memory: memory_relationships
    # ========================================

    # Create enum types
    op.execute("CREATE TYPE nodetype AS ENUM ('memory', 'agent', 'capability')")
    op.execute(
        "CREATE TYPE relationshiptype AS ENUM ("
        "'references', 'derived_from', 'related_to', 'supersedes', "
        "'similar_to', 'reply_to', 'depends_on', 'owns', 'shared_with')"
    )

    op.create_table(
        "memory_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_type", sa.Enum("memory", "agent", "capability", name="nodetype", create_type=False), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.Enum("memory", "agent", "capability", name="nodetype", create_type=False), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "relationship_type",
            sa.Enum(
                "references", "derived_from", "related_to", "supersedes",
                "similar_to", "reply_to", "depends_on", "owns", "shared_with",
                name="relationshiptype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by_agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "relationship_type",
            name="uq_relationship_edge",
        ),
    )

    op.create_index("ix_relationships_source", "memory_relationships", ["source_type", "source_id"])
    op.create_index("ix_relationships_target", "memory_relationships", ["target_type", "target_id"])
    op.create_index("ix_relationships_type", "memory_relationships", ["relationship_type"])
    op.create_index("ix_memory_relationships_source_id", "memory_relationships", ["source_id"])
    op.create_index("ix_memory_relationships_target_id", "memory_relationships", ["target_id"])

    # ========================================
    # Webhooks: webhook_endpoints, webhook_delivery_logs
    # ========================================

    # Create enum types
    op.execute("CREATE TYPE retrypolicy AS ENUM ('exponential', 'linear', 'none')")
    op.execute("CREATE TYPE deliverystatus AS ENUM ('pending', 'delivered', 'failed', 'retrying')")

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(255), nullable=False),
        sa.Column("event_types", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "retry_policy",
            sa.Enum("exponential", "linear", "none", name="retrypolicy", create_type=False),
            server_default="exponential",
            nullable=False,
        ),
        sa.Column("max_retries", sa.Integer(), server_default="5", nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.Column("custom_headers", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("total_deliveries", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("successful_deliveries", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("failed_deliveries", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_webhook_endpoints_agent_id", "webhook_endpoints", ["agent_id"])

    op.create_table(
        "webhook_delivery_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("webhook_endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "delivered", "failed", "retrying", name="deliverystatus", create_type=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["webhook_endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_webhook_delivery_logs_webhook_endpoint_id", "webhook_delivery_logs", ["webhook_endpoint_id"])
    op.create_index("ix_webhook_delivery_logs_event_id", "webhook_delivery_logs", ["event_id"])
    op.create_index("ix_webhook_delivery_logs_event_type", "webhook_delivery_logs", ["event_type"])
    op.create_index("ix_webhook_delivery_logs_status", "webhook_delivery_logs", ["status"])
    op.create_index("ix_webhook_logs_endpoint_created", "webhook_delivery_logs", ["webhook_endpoint_id", "created_at"])
    op.create_index("ix_webhook_logs_status_retry", "webhook_delivery_logs", ["status", "next_retry_at"])

    # ========================================
    # Analytics: hourly_metrics, daily_metrics, endpoint_metrics, storage_usage
    # ========================================

    op.execute(
        "CREATE TYPE metrictype AS ENUM ("
        "'api_request', 'memory_store', 'memory_get', 'memory_search', 'memory_delete', "
        "'capability_invoke', 'capability_discover', 'webhook_delivery', "
        "'message_sent', 'event_published', 'graph_traverse')"
    )

    op.create_table(
        "hourly_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metric_type",
            sa.Enum(
                "api_request", "memory_store", "memory_get", "memory_search", "memory_delete",
                "capability_invoke", "capability_discover", "webhook_delivery",
                "message_sent", "event_published", "graph_traverse",
                name="metrictype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("sum_value", sa.BigInteger(), nullable=True),
        sa.Column("min_value", sa.BigInteger(), nullable=True),
        sa.Column("max_value", sa.BigInteger(), nullable=True),
        sa.Column("avg_value", sa.Float(), nullable=True),
        sa.Column("dimensions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_hourly_metrics_agent_id", "hourly_metrics", ["agent_id"])
    op.create_index("ix_hourly_metrics_team_id", "hourly_metrics", ["team_id"])
    op.create_index("ix_hourly_metrics_hour", "hourly_metrics", ["hour"])
    op.create_index("ix_hourly_metrics_agent_hour", "hourly_metrics", ["agent_id", "hour"])
    op.create_index("ix_hourly_metrics_team_hour", "hourly_metrics", ["team_id", "hour"])
    op.create_index("ix_hourly_metrics_type_hour", "hourly_metrics", ["metric_type", "hour"])
    op.create_index("ix_hourly_metrics_lookup", "hourly_metrics", ["agent_id", "metric_type", "hour"])

    op.create_table(
        "daily_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metric_type",
            sa.Enum(
                "api_request", "memory_store", "memory_get", "memory_search", "memory_delete",
                "capability_invoke", "capability_discover", "webhook_delivery",
                "message_sent", "event_published", "graph_traverse",
                name="metrictype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("sum_value", sa.BigInteger(), nullable=True),
        sa.Column("min_value", sa.BigInteger(), nullable=True),
        sa.Column("max_value", sa.BigInteger(), nullable=True),
        sa.Column("avg_value", sa.Float(), nullable=True),
        sa.Column("p50_value", sa.Float(), nullable=True),
        sa.Column("p95_value", sa.Float(), nullable=True),
        sa.Column("p99_value", sa.Float(), nullable=True),
        sa.Column("dimensions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_daily_metrics_agent_id", "daily_metrics", ["agent_id"])
    op.create_index("ix_daily_metrics_team_id", "daily_metrics", ["team_id"])
    op.create_index("ix_daily_metrics_date", "daily_metrics", ["date"])
    op.create_index("ix_daily_metrics_agent_date", "daily_metrics", ["agent_id", "date"])
    op.create_index("ix_daily_metrics_team_date", "daily_metrics", ["team_id", "date"])
    op.create_index("ix_daily_metrics_type_date", "daily_metrics", ["metric_type", "date"])
    op.create_index("ix_daily_metrics_lookup", "daily_metrics", ["agent_id", "metric_type", "date"])

    op.create_table(
        "endpoint_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("error_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_latency_ms", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("min_latency_ms", sa.Integer(), nullable=True),
        sa.Column("max_latency_ms", sa.Integer(), nullable=True),
        sa.Column("avg_latency_ms", sa.Float(), nullable=True),
        sa.Column("status_codes", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_endpoint_metrics_agent_id", "endpoint_metrics", ["agent_id"])
    op.create_index("ix_endpoint_metrics_endpoint", "endpoint_metrics", ["endpoint"])
    op.create_index("ix_endpoint_metrics_hour", "endpoint_metrics", ["hour"])
    op.create_index("ix_endpoint_metrics_agent_hour", "endpoint_metrics", ["agent_id", "hour"])
    op.create_index("ix_endpoint_metrics_endpoint_hour", "endpoint_metrics", ["endpoint", "hour"])

    op.create_table(
        "storage_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("memory_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("memory_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("media_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("media_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("peak_memory_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("peak_memory_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("relationship_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_storage_usage_agent_id", "storage_usage", ["agent_id"])
    op.create_index("ix_storage_usage_date", "storage_usage", ["date"])
    op.create_index("ix_storage_usage_agent_date", "storage_usage", ["agent_id", "date"], unique=True)

    # ========================================
    # Tenants: tenant_settings, tenant_invites
    # ========================================

    op.create_table(
        "tenant_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subdomain", sa.String(63), nullable=True),
        sa.Column("custom_domain", sa.String(255), nullable=True),
        sa.Column("logo_url", sa.String(2048), nullable=True),
        sa.Column("primary_color", sa.String(7), nullable=True),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("features", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("allowed_ip_ranges", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("require_2fa", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("session_timeout_minutes", sa.Integer(), server_default="10080", nullable=False),
        sa.Column("allowed_oauth_providers", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("rate_limit_multiplier", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("custom_rate_limits", postgresql.JSONB(), nullable=True),
        sa.Column("webhook_signing_version", sa.String(10), server_default="v1", nullable=False),
        sa.Column("data_region", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspension_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id"),
        sa.UniqueConstraint("subdomain"),
        sa.UniqueConstraint("custom_domain"),
    )

    op.create_index("ix_tenant_settings_account_id", "tenant_settings", ["account_id"])
    op.create_index("ix_tenant_settings_subdomain", "tenant_settings", ["subdomain"])

    op.create_table(
        "tenant_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="member", nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["agents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token"),
    )

    op.create_index("ix_tenant_invites_account_id", "tenant_invites", ["account_id"])
    op.create_index("ix_tenant_invites_email", "tenant_invites", ["email"])
    op.create_index("ix_tenant_invites_account_email", "tenant_invites", ["account_id", "email"])


def downgrade() -> None:
    """Drop all new tables."""

    # Tenants
    op.drop_table("tenant_invites")
    op.drop_table("tenant_settings")

    # Analytics
    op.drop_table("storage_usage")
    op.drop_table("endpoint_metrics")
    op.drop_table("daily_metrics")
    op.drop_table("hourly_metrics")
    op.execute("DROP TYPE metrictype")

    # Webhooks
    op.drop_table("webhook_delivery_logs")
    op.drop_table("webhook_endpoints")
    op.execute("DROP TYPE deliverystatus")
    op.execute("DROP TYPE retrypolicy")

    # Graph Memory
    op.drop_table("memory_relationships")
    op.execute("DROP TYPE relationshiptype")
    op.execute("DROP TYPE nodetype")
