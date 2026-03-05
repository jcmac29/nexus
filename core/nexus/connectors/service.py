"""Connector service for external system integration."""

from __future__ import annotations

import ipaddress
import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.connectors.models import Connector, ConnectorExecution, ConnectorType

logger = logging.getLogger(__name__)


def _validate_connector_url(url: str) -> bool:
    """
    Validate connector URL to prevent SSRF attacks.

    Returns True if URL is safe, False otherwise.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        return False

    # Must have a hostname
    if not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()

    # Block localhost and common local hostnames
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "metadata.google.internal", "169.254.169.254",
        "metadata.internal", "kubernetes.default",
    }
    if hostname in blocked_hosts:
        logger.warning(f"Blocked connector URL to: {hostname}")
        return False

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            logger.warning(f"Blocked connector URL to private IP: {hostname}")
            return False
    except ValueError:
        # Not an IP address, it's a hostname
        pass

    # Block internal-looking hostnames
    if any(internal in hostname for internal in [".internal", ".local", ".localhost", ".svc.cluster"]):
        logger.warning(f"Blocked connector URL to internal host: {hostname}")
        return False

    return True


class ConnectorService:
    """Service for managing external connectors."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._connection_pools: dict[UUID, Any] = {}

    async def create_connector(
        self,
        name: str,
        slug: str,
        connector_type: ConnectorType,
        owner_id: UUID,
        connection_config: dict,
        description: str | None = None,
        allowed_operations: list[str] | None = None,
        query_templates: dict | None = None,
        **kwargs,
    ) -> Connector:
        """Create a new connector."""
        # SECURITY: Validate URLs for REST/GraphQL connectors to prevent SSRF
        if connector_type in [ConnectorType.REST, ConnectorType.GRAPHQL]:
            url = connection_config.get("base_url") or connection_config.get("endpoint")
            if url and not _validate_connector_url(url):
                raise ValueError("Invalid connector URL: must be a public HTTP/HTTPS endpoint")

        connector = Connector(
            name=name,
            slug=slug,
            description=description,
            connector_type=connector_type,
            owner_id=owner_id,
            connection_config=connection_config,
            allowed_operations=allowed_operations or ["read", "write"],
            query_templates=query_templates or {},
            **kwargs,
        )
        self.db.add(connector)
        await self.db.commit()
        await self.db.refresh(connector)
        return connector

    async def get_connector(self, connector_id: UUID) -> Connector | None:
        """Get a connector by ID."""
        result = await self.db.execute(select(Connector).where(Connector.id == connector_id))
        return result.scalar_one_or_none()

    async def get_connector_by_slug(self, slug: str) -> Connector | None:
        """Get a connector by slug."""
        result = await self.db.execute(select(Connector).where(Connector.slug == slug))
        return result.scalar_one_or_none()

    async def list_connectors(
        self,
        owner_id: UUID | None = None,
        connector_type: ConnectorType | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[Connector]:
        """List connectors."""
        query = select(Connector)

        if owner_id:
            query = query.where(Connector.owner_id == owner_id)
        if connector_type:
            query = query.where(Connector.connector_type == connector_type)
        if active_only:
            query = query.where(Connector.is_active == True)

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def execute(
        self,
        connector_id: UUID,
        operation: str,
        executor_id: UUID,
        executor_type: str = "agent",
        query: str | None = None,
        template_name: str | None = None,
        params: dict | None = None,
    ) -> ConnectorExecution:
        """Execute an operation on a connector."""
        connector = await self.get_connector(connector_id)
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")

        if not connector.is_active:
            raise ValueError(f"Connector {connector.name} is not active")

        # Check operation is allowed
        if operation not in connector.allowed_operations:
            raise ValueError(f"Operation {operation} not allowed")

        # Get query from template if specified
        actual_query = query
        if template_name:
            template = connector.query_templates.get(template_name)
            if template:
                actual_query = template.get("query", "")
                # Merge template params with provided params
                template_params = template.get("default_params", {})
                params = {**template_params, **(params or {})}

        # Create execution record
        execution = ConnectorExecution(
            connector_id=connector_id,
            executor_id=executor_id,
            executor_type=executor_type,
            operation=operation,
            template_name=template_name,
            query=actual_query,
            params=params,
            status="running",
        )
        self.db.add(execution)
        await self.db.flush()

        start_time = time.time()

        try:
            # Execute based on connector type
            if connector.connector_type in [ConnectorType.POSTGRESQL, ConnectorType.MYSQL, ConnectorType.SQLITE]:
                result = await self._execute_sql(connector, operation, actual_query, params)
            elif connector.connector_type == ConnectorType.MONGODB:
                result = await self._execute_mongodb(connector, operation, actual_query, params)
            elif connector.connector_type == ConnectorType.REST:
                result = await self._execute_rest(connector, operation, actual_query, params)
            elif connector.connector_type == ConnectorType.GRAPHQL:
                result = await self._execute_graphql(connector, operation, actual_query, params)
            elif connector.connector_type in [ConnectorType.AWS_S3, ConnectorType.S3_COMPATIBLE]:
                result = await self._execute_s3(connector, operation, params)
            elif connector.connector_type == ConnectorType.REDIS:
                result = await self._execute_redis(connector, operation, actual_query, params)
            elif connector.connector_type == ConnectorType.ELASTICSEARCH:
                result = await self._execute_elasticsearch(connector, operation, actual_query, params)
            else:
                result = {"status": "executed", "type": connector.connector_type.value}

            execution.status = "success"
            execution.result = result
            if isinstance(result, dict):
                execution.rows_affected = result.get("rows_affected")

            connector.successful_operations += 1

        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
            connector.failed_operations += 1
            raise

        finally:
            execution.completed_at = datetime.utcnow()
            execution.duration_ms = (time.time() - start_time) * 1000

            connector.total_operations += 1
            connector.last_used_at = datetime.utcnow()

            # Update average latency
            if connector.successful_operations > 0:
                connector.avg_latency_ms = (
                    (connector.avg_latency_ms * (connector.successful_operations - 1) + execution.duration_ms)
                    / connector.successful_operations
                )

            await self.db.commit()

        await self.db.refresh(execution)
        return execution

    async def _execute_sql(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute SQL operation."""
        # In production, use proper connection pooling
        # This is a simplified implementation
        import asyncpg

        # SECURITY: Validate query to prevent SQL injection
        if not query:
            raise ValueError("Query is required for SQL operations")

        # Only allow queries from predefined templates (query must match a template)
        # Raw SQL queries are rejected for security
        allowed_queries = set(
            tpl.get("query", "") for tpl in connector.query_templates.values()
        )
        if query not in allowed_queries:
            raise ValueError(
                "Only predefined query templates are allowed. "
                "Raw SQL queries are rejected for security reasons."
            )

        config = connector.connection_config
        conn = await asyncpg.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            database=config.get("database", "postgres"),
            user=config.get("user", "postgres"),
            password=config.get("password", ""),
        )

        try:
            # SECURITY: Use proper parameter binding with positional params
            # Convert dict params to ordered list matching $1, $2, etc. in query
            param_values = []
            if params:
                # Parameters must be passed as $1, $2, etc. in the query template
                # Extract them in order
                for i in range(1, len(params) + 1):
                    key = f"p{i}"  # Expected keys: p1, p2, p3, ...
                    if key in params:
                        param_values.append(params[key])

            if operation == "read":
                rows = await conn.fetch(query, *param_values)
                return {
                    "rows": [dict(row) for row in rows],
                    "count": len(rows),
                }
            elif operation in ["write", "execute"]:
                result = await conn.execute(query, *param_values)
                return {
                    "status": "executed",
                    "result": result,
                }
        finally:
            await conn.close()

    async def _execute_mongodb(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute MongoDB operation."""
        # Placeholder - would use motor for async MongoDB
        return {"type": "mongodb", "operation": operation}

    async def _execute_rest(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute REST API call."""
        import httpx

        config = connector.connection_config
        base_url = config.get("base_url", "")

        # SECURITY: Validate URL to prevent SSRF (defense in depth)
        if not _validate_connector_url(base_url):
            raise ValueError("Invalid connector URL: must be a public HTTP/HTTPS endpoint")

        headers = dict(config.get("headers", {}))

        # Add authentication
        auth_type = config.get("auth_type", "none")
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {config.get('auth_config', {}).get('token', '')}"
        elif auth_type == "api_key":
            header_name = config.get("auth_config", {}).get("header_name", "X-API-Key")
            headers[header_name] = config.get("auth_config", {}).get("api_key", "")

        # SECURITY: Validate HTTP method against whitelist
        allowed_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        method = (params.get("method", "GET") if params else "GET").upper()
        if method not in allowed_methods:
            raise ValueError(f"Invalid HTTP method: {method}")

        path = query or params.get("path", "") if params else ""

        # SECURITY: Sanitize path to prevent URL manipulation
        # Strip any protocol/host prefix that could redirect the request
        if path:
            # Remove leading slashes and dangerous characters
            path = path.lstrip("/")
            # Reject paths that could change the host (e.g., @attacker.com, //evil.com)
            if "@" in path or path.startswith("/") or "://" in path:
                raise ValueError("Invalid path: contains forbidden characters")

        body = params.get("body", {}) if params else {}

        # Build final URL and re-validate to ensure path didn't bypass SSRF protection
        final_url = f"{base_url.rstrip('/')}/{path}" if path else base_url
        if not _validate_connector_url(final_url):
            raise ValueError("Invalid final URL: SSRF protection triggered")

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(final_url, headers=headers, params=body)
            elif method == "POST":
                response = await client.post(final_url, headers=headers, json=body)
            elif method == "PUT":
                response = await client.put(final_url, headers=headers, json=body)
            elif method == "DELETE":
                response = await client.delete(final_url, headers=headers)
            else:
                response = await client.request(method, final_url, headers=headers, json=body)

            try:
                return response.json()
            except (json.JSONDecodeError, ValueError):
                return {"text": response.text, "status_code": response.status_code}

    async def _execute_graphql(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute GraphQL query."""
        import httpx

        config = connector.connection_config
        endpoint = config.get("endpoint", "")

        # SECURITY: Validate URL to prevent SSRF (defense in depth)
        if not _validate_connector_url(endpoint):
            raise ValueError("Invalid connector URL: must be a public HTTP/HTTPS endpoint")

        headers = dict(config.get("headers", {}))
        headers["Content-Type"] = "application/json"

        variables = params.get("variables", {}) if params else {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                json={"query": query, "variables": variables},
            )
            return response.json()

    async def _execute_s3(
        self,
        connector: Connector,
        operation: str,
        params: dict | None,
    ) -> dict:
        """Execute S3 operation."""
        # Placeholder - would use aioboto3 or minio
        return {"type": "s3", "operation": operation}

    async def _execute_redis(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute Redis operation."""
        # Placeholder - would use aioredis
        return {"type": "redis", "operation": operation}

    async def _execute_elasticsearch(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute Elasticsearch operation."""
        # Placeholder - would use elasticsearch-py async
        return {"type": "elasticsearch", "operation": operation}

    async def health_check(self, connector_id: UUID) -> dict:
        """Perform health check on a connector."""
        connector = await self.get_connector(connector_id)
        if not connector:
            return {"status": "error", "message": "Connector not found"}

        try:
            # Try a simple operation based on type
            if connector.connector_type in [ConnectorType.REST, ConnectorType.GRAPHQL]:
                import httpx
                config = connector.connection_config
                base_url = config.get("base_url", config.get("endpoint", ""))

                # SECURITY: Validate URL to prevent SSRF
                if not _validate_connector_url(base_url):
                    return {"status": "error", "message": "Invalid URL - SSRF protection"}

                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(base_url)
                    status = "healthy" if response.status_code < 400 else "unhealthy"
            else:
                # For databases, try a simple query
                status = "healthy"  # Would do actual connection test
        except Exception as e:
            status = "unhealthy"

        connector.last_health_check = datetime.utcnow()
        connector.health_status = status
        await self.db.commit()

        return {"status": status, "checked_at": connector.last_health_check.isoformat()}

    async def discover_schema(self, connector_id: UUID) -> dict:
        """Discover schema/structure of the connected system."""
        connector = await self.get_connector(connector_id)
        if not connector:
            return {}

        schema = {}

        if connector.connector_type in [ConnectorType.POSTGRESQL, ConnectorType.MYSQL]:
            # Would query information_schema
            schema = {"tables": [], "discovered_at": datetime.utcnow().isoformat()}
        elif connector.connector_type == ConnectorType.MONGODB:
            # Would list collections
            schema = {"collections": [], "discovered_at": datetime.utcnow().isoformat()}
        elif connector.connector_type == ConnectorType.REST:
            # Would try to fetch OpenAPI spec if available
            schema = {"endpoints": [], "discovered_at": datetime.utcnow().isoformat()}

        connector.schema_info = schema
        await self.db.commit()

        return schema
