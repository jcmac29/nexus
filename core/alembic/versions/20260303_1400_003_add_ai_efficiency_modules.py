"""Add AI efficiency modules: swarm, learning, reputation, goals, context, budgets, vitals.

Revision ID: 003
Revises: 002
Create Date: 2026-03-03 14:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables for AI efficiency modules."""

    # ========================================
    # SWARM MODULE
    # ========================================

    # Create enum types for swarm
    op.execute("CREATE TYPE swarmstatus AS ENUM ('forming', 'active', 'paused', 'disbanded')")
    op.execute("CREATE TYPE memberrole AS ENUM ('leader', 'worker')")
    op.execute("CREATE TYPE memberstatus AS ENUM ('connected', 'busy', 'idle', 'disconnected')")
    op.execute(
        "CREATE TYPE swarmtaskstatus AS ENUM "
        "('pending', 'assigned', 'in_progress', 'completed', 'failed', 'reassigned')"
    )

    # swarms table
    op.create_table(
        "swarms",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("join_code", sa.String(6), nullable=False),
        sa.Column("owner_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Enum("forming", "active", "paused", "disbanded", name="swarmstatus", create_type=False), server_default="forming", nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("disbanded_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("join_code"),
    )
    op.create_index("ix_swarms_join_code", "swarms", ["join_code"])
    op.create_index("ix_swarms_owner_status", "swarms", ["owner_agent_id", "status"])

    # swarm_tasks table (before swarm_members due to FK)
    op.create_table(
        "swarm_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("swarm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", sa.String(100), server_default="general", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column("input_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("required_capabilities", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("status", sa.Enum("pending", "assigned", "in_progress", "completed", "failed", "reassigned", name="swarmtaskstatus", create_type=False), server_default="pending", nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), server_default="300", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["swarm_id"], ["swarms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_task_id"], ["swarm_tasks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_swarm_tasks_swarm_id", "swarm_tasks", ["swarm_id"])
    op.create_index("ix_swarm_tasks_swarm_status", "swarm_tasks", ["swarm_id", "status"])
    op.create_index("ix_swarm_tasks_priority_status", "swarm_tasks", ["priority", "status"])

    # swarm_members table
    op.create_table(
        "swarm_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("swarm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Enum("leader", "worker", name="memberrole", create_type=False), server_default="worker", nullable=False),
        sa.Column("status", sa.Enum("connected", "busy", "idle", "disconnected", name="memberstatus", create_type=False), server_default="idle", nullable=False),
        sa.Column("capabilities", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("current_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tasks_completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["swarm_id"], ["swarms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_task_id"], ["swarm_tasks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_swarm_members_swarm_id", "swarm_members", ["swarm_id"])
    op.create_index("ix_swarm_members_agent_id", "swarm_members", ["agent_id"])
    op.create_index("ix_swarm_members_swarm_status", "swarm_members", ["swarm_id", "status"])
    op.create_index("ix_swarm_members_agent_swarm", "swarm_members", ["agent_id", "swarm_id"])

    # Add FK from swarm_tasks to swarm_members (now that members exists)
    op.create_foreign_key("fk_swarm_tasks_assigned_to", "swarm_tasks", "swarm_members", ["assigned_to"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_swarm_tasks_created_by", "swarm_tasks", "swarm_members", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_swarm_tasks_assigned_status", "swarm_tasks", ["assigned_to", "status"])

    # swarm_task_results table
    op.create_table(
        "swarm_task_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("success", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["swarm_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["swarm_members.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_swarm_task_results_task_id", "swarm_task_results", ["task_id"])
    op.create_index("ix_swarm_task_results_member_id", "swarm_task_results", ["member_id"])

    # ========================================
    # LEARNING MODULE
    # ========================================

    op.execute("CREATE TYPE feedbacktype AS ENUM ('success', 'failure', 'partial', 'timeout', 'error')")
    op.execute("CREATE TYPE improvementstatus AS ENUM ('suggested', 'accepted', 'rejected', 'implemented')")

    # learning_feedback table
    op.create_table(
        "learning_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_description", sa.Text(), nullable=True),
        sa.Column("input_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("feedback_type", sa.Enum("success", "failure", "partial", "timeout", "error", name="feedbacktype", create_type=False), nullable=False),
        sa.Column("output_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("context_tags", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("related_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_agent_id"], ["agents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_learning_feedback_agent_id", "learning_feedback", ["agent_id"])
    op.create_index("ix_learning_feedback_action_type", "learning_feedback", ["action_type"])
    op.create_index("ix_learning_feedback_agent_action", "learning_feedback", ["agent_id", "action_type"])
    op.create_index("ix_learning_feedback_agent_type", "learning_feedback", ["agent_id", "feedback_type"])

    # learning_patterns table
    op.create_table(
        "learning_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("context_signature", sa.String(500), nullable=False),
        sa.Column("total_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_rate", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("avg_duration_ms", sa.Integer(), nullable=True),
        sa.Column("best_practices", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("failure_modes", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("recommended_approach", sa.Text(), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_learning_patterns_agent_id", "learning_patterns", ["agent_id"])
    op.create_index("ix_learning_patterns_action_type", "learning_patterns", ["action_type"])
    op.create_index("ix_learning_patterns_agent_action", "learning_patterns", ["agent_id", "action_type"])

    # learning_improvements table
    op.create_table(
        "learning_improvements",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pattern_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("improvement_type", sa.String(50), nullable=False),
        sa.Column("expected_impact", sa.Text(), nullable=True),
        sa.Column("priority_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("status", sa.Enum("suggested", "accepted", "rejected", "implemented", name="improvementstatus", create_type=False), server_default="suggested", nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("implementation_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pattern_id"], ["learning_patterns.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_learning_improvements_agent_id", "learning_improvements", ["agent_id"])
    op.create_index("ix_learning_improvements_agent_status", "learning_improvements", ["agent_id", "status"])

    # ========================================
    # REPUTATION MODULE
    # ========================================

    op.execute("CREATE TYPE disputestatus AS ENUM ('open', 'investigating', 'resolved_valid', 'resolved_invalid', 'dismissed')")

    # reputation_scores table
    op.create_table(
        "reputation_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("overall_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("reliability_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("quality_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("responsiveness_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("collaboration_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("total_interactions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("successful_interactions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("vouches_received", sa.Integer(), server_default="0", nullable=False),
        sa.Column("vouches_given", sa.Integer(), server_default="0", nullable=False),
        sa.Column("disputes_received", sa.Integer(), server_default="0", nullable=False),
        sa.Column("disputes_resolved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tier", sa.String(20), server_default="bronze", nullable=False),
        sa.Column("tier_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_calculated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("agent_id"),
    )
    op.create_index("ix_reputation_scores_agent_id", "reputation_scores", ["agent_id"])

    # reputation_vouches table
    op.create_table(
        "reputation_vouches",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("voucher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vouchee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("strength", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capabilities", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["voucher_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vouchee_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("voucher_id", "vouchee_id", "category", name="uq_vouch_unique"),
    )
    op.create_index("ix_reputation_vouches_voucher_id", "reputation_vouches", ["voucher_id"])
    op.create_index("ix_reputation_vouches_vouchee_id", "reputation_vouches", ["vouchee_id"])
    op.create_index("ix_vouches_vouchee_active", "reputation_vouches", ["vouchee_id", "is_active"])

    # reputation_disputes table
    op.create_table(
        "reputation_disputes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accused_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), server_default="medium", nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Enum("open", "investigating", "resolved_valid", "resolved_invalid", "dismissed", name="disputestatus", create_type=False), server_default="open", nullable=False),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reputation_impact", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["reporter_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accused_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by"], ["agents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_reputation_disputes_reporter_id", "reputation_disputes", ["reporter_id"])
    op.create_index("ix_reputation_disputes_accused_id", "reputation_disputes", ["accused_id"])
    op.create_index("ix_disputes_accused_status", "reputation_disputes", ["accused_id", "status"])

    # reputation_events table
    op.create_table(
        "reputation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("score_delta", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("category_affected", sa.String(50), nullable=True),
        sa.Column("source_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_agent_id"], ["agents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_reputation_events_agent_id", "reputation_events", ["agent_id"])
    op.create_index("ix_reputation_events_event_type", "reputation_events", ["event_type"])
    op.create_index("ix_reputation_events_agent_type", "reputation_events", ["agent_id", "event_type"])

    # ========================================
    # GOALS MODULE
    # ========================================

    op.execute("CREATE TYPE goalstatus AS ENUM ('draft', 'active', 'in_progress', 'blocked', 'completed', 'failed', 'cancelled', 'paused')")
    op.execute("CREATE TYPE goalpriority AS ENUM ('critical', 'high', 'medium', 'low', 'background')")

    # goals table
    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("success_criteria", sa.Text(), nullable=True),
        sa.Column("goal_type", sa.String(50), server_default="general", nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("status", sa.Enum("draft", "active", "in_progress", "blocked", "completed", "failed", "cancelled", "paused", name="goalstatus", create_type=False), server_default="draft", nullable=False),
        sa.Column("priority", sa.Enum("critical", "high", "medium", "low", "background", name="goalpriority", create_type=False), server_default="medium", nullable=False),
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress_notes", sa.Text(), nullable=True),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("outcome_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("constraints", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_goal_id"], ["goals.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_goals_agent_id", "goals", ["agent_id"])
    op.create_index("ix_goals_agent_status", "goals", ["agent_id", "status"])
    op.create_index("ix_goals_agent_priority", "goals", ["agent_id", "priority"])

    # goal_milestones table
    op.create_table(
        "goal_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_goal_milestones_goal_id", "goal_milestones", ["goal_id"])
    op.create_index("ix_milestones_goal_order", "goal_milestones", ["goal_id", "order"])

    # goal_blockers table
    op.create_table(
        "goal_blockers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("blocker_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), server_default="medium", nullable=False),
        sa.Column("is_resolved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocking_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blocking_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocking_agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["blocking_goal_id"], ["goals.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_goal_blockers_goal_id", "goal_blockers", ["goal_id"])
    op.create_index("ix_blockers_goal_resolved", "goal_blockers", ["goal_id", "is_resolved"])

    # goal_delegations table
    op.create_table(
        "goal_delegations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delegator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delegate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("constraints", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("result", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delegator_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delegate_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_goal_id"], ["goals.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_goal_delegations_goal_id", "goal_delegations", ["goal_id"])
    op.create_index("ix_goal_delegations_delegator_id", "goal_delegations", ["delegator_id"])
    op.create_index("ix_goal_delegations_delegate_id", "goal_delegations", ["delegate_id"])
    op.create_index("ix_delegations_delegate_status", "goal_delegations", ["delegate_id", "status"])

    # ========================================
    # CONTEXT MODULE
    # ========================================

    op.execute("CREATE TYPE transferstatus AS ENUM ('initiated', 'sent', 'received', 'accepted', 'rejected', 'applied', 'failed')")

    # context_packages table
    op.create_table(
        "context_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("goals", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("memories", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("conversation_history", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("reasoning_trace", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("decisions_made", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("constraints", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("preferences", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("allowed_agents", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_agent_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_context_packages_owner_agent_id", "context_packages", ["owner_agent_id"])
    op.create_index("ix_context_packages_owner_name", "context_packages", ["owner_agent_id", "name"])

    # context_transfers table
    op.create_table(
        "context_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receiver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("initiated", "sent", "received", "accepted", "rejected", "applied", "failed", name="transferstatus", create_type=False), server_default="initiated", nullable=False),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("changes", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("related_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["package_id"], ["context_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receiver_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_context_transfers_package_id", "context_transfers", ["package_id"])
    op.create_index("ix_context_transfers_sender_id", "context_transfers", ["sender_id"])
    op.create_index("ix_context_transfers_receiver_id", "context_transfers", ["receiver_id"])
    op.create_index("ix_context_transfers_receiver_status", "context_transfers", ["receiver_id", "status"])
    op.create_index("ix_context_transfers_sender", "context_transfers", ["sender_id"])

    # ========================================
    # BUDGETS MODULE
    # ========================================

    op.execute("CREATE TYPE budgettype AS ENUM ('api_calls', 'tokens', 'credits', 'compute_seconds', 'storage_bytes', 'bandwidth_bytes', 'custom')")
    op.execute("CREATE TYPE reservationstatus AS ENUM ('pending', 'confirmed', 'consumed', 'released', 'expired')")

    # budgets table
    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_type", sa.Enum("api_calls", "tokens", "credits", "compute_seconds", "storage_bytes", "bandwidth_bytes", "custom", name="budgettype", create_type=False), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("total_limit", sa.BigInteger(), nullable=False),
        sa.Column("used_amount", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("reserved_amount", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("period_type", sa.String(20), server_default="monthly", nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_threshold", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("alert_sent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_exceeded", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("agent_id", "budget_type", "name", name="uq_budget_agent_type_name"),
    )
    op.create_index("ix_budgets_agent_id", "budgets", ["agent_id"])
    op.create_index("ix_budgets_agent_type", "budgets", ["agent_id", "budget_type"])

    # budget_reservations table
    op.create_table(
        "budget_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("pending", "confirmed", "consumed", "released", "expired", name="reservationstatus", create_type=False), server_default="pending", nullable=False),
        sa.Column("actual_amount", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_budget_reservations_budget_id", "budget_reservations", ["budget_id"])
    op.create_index("ix_budget_reservations_agent_id", "budget_reservations", ["agent_id"])
    op.create_index("ix_reservations_budget_status", "budget_reservations", ["budget_id", "status"])

    # budget_usage_records table
    op.create_table(
        "budget_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["budget_reservations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_budget_usage_records_budget_id", "budget_usage_records", ["budget_id"])
    op.create_index("ix_budget_usage_records_agent_id", "budget_usage_records", ["agent_id"])
    op.create_index("ix_usage_records_budget_created", "budget_usage_records", ["budget_id", "created_at"])

    # ========================================
    # VITALS MODULE
    # ========================================

    op.execute("CREATE TYPE healthstatus AS ENUM ('healthy', 'degraded', 'unhealthy', 'unknown', 'offline')")

    # agent_vitals table
    op.create_table(
        "agent_vitals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Enum("healthy", "degraded", "unhealthy", "unknown", "offline", name="healthstatus", create_type=False), server_default="unknown", nullable=False),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("is_online", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_busy", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("current_load", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("max_concurrent_tasks", sa.Integer(), server_default="1", nullable=False),
        sa.Column("current_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_response_time_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("p95_response_time_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("p99_response_time_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_rate", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("uptime_percent", sa.Float(), server_default="100.0", nullable=False),
        sa.Column("last_downtime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_uptime_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("queue_depth", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_wait_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("capabilities_status", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_interval_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.Column("missed_heartbeats", sa.Integer(), server_default="0", nullable=False),
        sa.Column("agent_version", sa.String(50), nullable=True),
        sa.Column("last_deployed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("agent_id"),
    )
    op.create_index("ix_agent_vitals_agent_id", "agent_vitals", ["agent_id"])
    op.create_index("ix_agent_vitals_status_online", "agent_vitals", ["status", "is_online"])

    # vitals_subscriptions table
    op.create_table(
        "vitals_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("subscriber_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notify_on", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("threshold_load", sa.Float(), nullable=True),
        sa.Column("threshold_error_rate", sa.Float(), nullable=True),
        sa.Column("threshold_response_time_ms", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("webhook_url", sa.String(2048), nullable=True),
        sa.Column("last_notified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["subscriber_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_agent_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vitals_subscriptions_subscriber_id", "vitals_subscriptions", ["subscriber_id"])
    op.create_index("ix_vitals_subscriptions_target_agent_id", "vitals_subscriptions", ["target_agent_id"])
    op.create_index("ix_vitals_subs_subscriber_active", "vitals_subscriptions", ["subscriber_id", "is_active"])
    op.create_index("ix_vitals_subs_target", "vitals_subscriptions", ["target_agent_id"])

    # vitals_snapshots table
    op.create_table(
        "vitals_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Enum("healthy", "degraded", "unhealthy", "unknown", "offline", name="healthstatus", create_type=False), nullable=False),
        sa.Column("is_online", sa.Boolean(), nullable=False),
        sa.Column("current_load", sa.Float(), nullable=False),
        sa.Column("current_tasks", sa.Integer(), nullable=False),
        sa.Column("avg_response_time_ms", sa.Integer(), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("queue_depth", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vitals_snapshots_agent_id", "vitals_snapshots", ["agent_id"])
    op.create_index("ix_vitals_snapshots_agent_created", "vitals_snapshots", ["agent_id", "created_at"])


def downgrade() -> None:
    """Drop all AI efficiency module tables."""

    # Vitals
    op.drop_table("vitals_snapshots")
    op.drop_table("vitals_subscriptions")
    op.drop_table("agent_vitals")
    op.execute("DROP TYPE healthstatus")

    # Budgets
    op.drop_table("budget_usage_records")
    op.drop_table("budget_reservations")
    op.drop_table("budgets")
    op.execute("DROP TYPE reservationstatus")
    op.execute("DROP TYPE budgettype")

    # Context
    op.drop_table("context_transfers")
    op.drop_table("context_packages")
    op.execute("DROP TYPE transferstatus")

    # Goals
    op.drop_table("goal_delegations")
    op.drop_table("goal_blockers")
    op.drop_table("goal_milestones")
    op.drop_table("goals")
    op.execute("DROP TYPE goalpriority")
    op.execute("DROP TYPE goalstatus")

    # Reputation
    op.drop_table("reputation_events")
    op.drop_table("reputation_disputes")
    op.drop_table("reputation_vouches")
    op.drop_table("reputation_scores")
    op.execute("DROP TYPE disputestatus")

    # Learning
    op.drop_table("learning_improvements")
    op.drop_table("learning_patterns")
    op.drop_table("learning_feedback")
    op.execute("DROP TYPE improvementstatus")
    op.execute("DROP TYPE feedbacktype")

    # Swarm
    op.drop_constraint("fk_swarm_tasks_assigned_to", "swarm_tasks", type_="foreignkey")
    op.drop_constraint("fk_swarm_tasks_created_by", "swarm_tasks", type_="foreignkey")
    op.drop_table("swarm_task_results")
    op.drop_table("swarm_members")
    op.drop_table("swarm_tasks")
    op.drop_table("swarms")
    op.execute("DROP TYPE swarmtaskstatus")
    op.execute("DROP TYPE memberstatus")
    op.execute("DROP TYPE memberrole")
    op.execute("DROP TYPE swarmstatus")
