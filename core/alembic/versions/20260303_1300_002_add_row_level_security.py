"""Add row-level security policies for multi-tenant isolation.

Revision ID: 002
Revises: 001
Create Date: 2026-03-03 13:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable RLS and create tenant isolation policies."""

    # ========================================
    # Helper function for setting tenant context
    # ========================================

    # Create function to set tenant context from current user
    op.execute("""
        CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id uuid)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', tenant_id::text, true);
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create function to get current tenant
    op.execute("""
        CREATE OR REPLACE FUNCTION current_tenant_id()
        RETURNS uuid AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.current_tenant', true), '')::uuid;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # ========================================
    # Enable RLS on key tables
    # ========================================

    # Agents table
    op.execute("ALTER TABLE agents ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_agents ON agents
            USING (
                account_id IS NULL  -- Allow if no tenant (legacy/admin)
                OR account_id = current_tenant_id()
                OR current_tenant_id() IS NULL  -- Bypass if no tenant context set
            )
    """)

    # Memories table
    op.execute("ALTER TABLE memories ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_memories ON memories
            USING (
                account_id IS NULL
                OR account_id = current_tenant_id()
                OR current_tenant_id() IS NULL
            )
    """)

    # Memory shares table
    op.execute("ALTER TABLE memory_shares ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_memory_shares ON memory_shares
            USING (
                memory_id IN (
                    SELECT id FROM memories
                    WHERE account_id IS NULL
                       OR account_id = current_tenant_id()
                       OR current_tenant_id() IS NULL
                )
            )
    """)

    # API keys table
    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_api_keys ON api_keys
            USING (
                agent_id IN (
                    SELECT id FROM agents
                    WHERE account_id IS NULL
                       OR account_id = current_tenant_id()
                       OR current_tenant_id() IS NULL
                )
            )
    """)

    # Capabilities table (if it exists with account_id)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'capabilities' AND column_name = 'account_id'
            ) THEN
                EXECUTE 'ALTER TABLE capabilities ENABLE ROW LEVEL SECURITY';
                EXECUTE '
                    CREATE POLICY tenant_isolation_capabilities ON capabilities
                        USING (
                            account_id IS NULL
                            OR account_id = current_tenant_id()
                            OR current_tenant_id() IS NULL
                        )
                ';
            END IF;
        END $$;
    """)

    # Webhook endpoints table
    op.execute("ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_webhooks ON webhook_endpoints
            USING (
                agent_id IN (
                    SELECT id FROM agents
                    WHERE account_id IS NULL
                       OR account_id = current_tenant_id()
                       OR current_tenant_id() IS NULL
                )
            )
    """)

    # Webhook delivery logs (through webhook_endpoints)
    op.execute("ALTER TABLE webhook_delivery_logs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_webhook_logs ON webhook_delivery_logs
            USING (
                webhook_endpoint_id IN (
                    SELECT id FROM webhook_endpoints
                    WHERE agent_id IN (
                        SELECT id FROM agents
                        WHERE account_id IS NULL
                           OR account_id = current_tenant_id()
                           OR current_tenant_id() IS NULL
                    )
                )
            )
    """)

    # Memory relationships table
    op.execute("ALTER TABLE memory_relationships ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_relationships ON memory_relationships
            USING (
                created_by_agent_id IS NULL
                OR created_by_agent_id IN (
                    SELECT id FROM agents
                    WHERE account_id IS NULL
                       OR account_id = current_tenant_id()
                       OR current_tenant_id() IS NULL
                )
            )
    """)

    # Analytics tables (hourly_metrics, daily_metrics, endpoint_metrics, storage_usage)
    for table in ["hourly_metrics", "daily_metrics", "endpoint_metrics", "storage_usage"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
                USING (
                    agent_id IN (
                        SELECT id FROM agents
                        WHERE account_id IS NULL
                           OR account_id = current_tenant_id()
                           OR current_tenant_id() IS NULL
                    )
                )
        """)

    # Tenant settings (own tenant only)
    op.execute("ALTER TABLE tenant_settings ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_settings ON tenant_settings
            USING (
                account_id = current_tenant_id()
                OR current_tenant_id() IS NULL
            )
    """)

    # Tenant invites (own tenant only)
    op.execute("ALTER TABLE tenant_invites ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_invites ON tenant_invites
            USING (
                account_id = current_tenant_id()
                OR current_tenant_id() IS NULL
            )
    """)

    # Teams table (if exists)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'teams') THEN
                EXECUTE 'ALTER TABLE teams ENABLE ROW LEVEL SECURITY';
                EXECUTE '
                    CREATE POLICY tenant_isolation_teams ON teams
                        USING (
                            owner_agent_id IN (
                                SELECT id FROM agents
                                WHERE account_id IS NULL
                                   OR account_id = current_tenant_id()
                                   OR current_tenant_id() IS NULL
                            )
                        )
                ';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove RLS policies and disable RLS."""

    # Drop policies and disable RLS in reverse order

    # Teams
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'teams') THEN
                EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_teams ON teams';
                EXECUTE 'ALTER TABLE teams DISABLE ROW LEVEL SECURITY';
            END IF;
        END $$;
    """)

    # Tenant tables
    op.execute("DROP POLICY IF EXISTS tenant_isolation_invites ON tenant_invites")
    op.execute("ALTER TABLE tenant_invites DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_settings ON tenant_settings")
    op.execute("ALTER TABLE tenant_settings DISABLE ROW LEVEL SECURITY")

    # Analytics tables
    for table in ["storage_usage", "endpoint_metrics", "daily_metrics", "hourly_metrics"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Relationships
    op.execute("DROP POLICY IF EXISTS tenant_isolation_relationships ON memory_relationships")
    op.execute("ALTER TABLE memory_relationships DISABLE ROW LEVEL SECURITY")

    # Webhook logs
    op.execute("DROP POLICY IF EXISTS tenant_isolation_webhook_logs ON webhook_delivery_logs")
    op.execute("ALTER TABLE webhook_delivery_logs DISABLE ROW LEVEL SECURITY")

    # Webhooks
    op.execute("DROP POLICY IF EXISTS tenant_isolation_webhooks ON webhook_endpoints")
    op.execute("ALTER TABLE webhook_endpoints DISABLE ROW LEVEL SECURITY")

    # Capabilities
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'capabilities' AND column_name = 'account_id'
            ) THEN
                EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_capabilities ON capabilities';
                EXECUTE 'ALTER TABLE capabilities DISABLE ROW LEVEL SECURITY';
            END IF;
        END $$;
    """)

    # API keys
    op.execute("DROP POLICY IF EXISTS tenant_isolation_api_keys ON api_keys")
    op.execute("ALTER TABLE api_keys DISABLE ROW LEVEL SECURITY")

    # Memory shares
    op.execute("DROP POLICY IF EXISTS tenant_isolation_memory_shares ON memory_shares")
    op.execute("ALTER TABLE memory_shares DISABLE ROW LEVEL SECURITY")

    # Memories
    op.execute("DROP POLICY IF EXISTS tenant_isolation_memories ON memories")
    op.execute("ALTER TABLE memories DISABLE ROW LEVEL SECURITY")

    # Agents
    op.execute("DROP POLICY IF EXISTS tenant_isolation_agents ON agents")
    op.execute("ALTER TABLE agents DISABLE ROW LEVEL SECURITY")

    # Drop helper functions
    op.execute("DROP FUNCTION IF EXISTS current_tenant_id()")
    op.execute("DROP FUNCTION IF EXISTS set_tenant_context(uuid)")
