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
        """Execute MongoDB operation using motor for async."""
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError:
            raise RuntimeError("motor package required for MongoDB. Install with: pip install motor")

        config = connector.connection_config
        connection_string = config.get("connection_string", "mongodb://localhost:27017")
        database = config.get("database", "test")
        collection_name = params.get("collection") if params else None

        if not collection_name:
            raise ValueError("MongoDB operations require 'collection' parameter")

        client = AsyncIOMotorClient(connection_string)
        db = client[database]
        collection = db[collection_name]

        try:
            if operation == "read":
                # Find documents
                filter_query = params.get("filter", {}) if params else {}
                projection = params.get("projection") if params else None
                limit = params.get("limit", 100) if params else 100
                skip = params.get("skip", 0) if params else 0

                cursor = collection.find(filter_query, projection).skip(skip).limit(limit)
                documents = await cursor.to_list(length=limit)

                # Convert ObjectId to string for JSON serialization
                for doc in documents:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])

                return {"documents": documents, "count": len(documents)}

            elif operation == "write":
                # Insert document(s)
                document = params.get("document") if params else None
                documents = params.get("documents") if params else None

                if document:
                    result = await collection.insert_one(document)
                    return {"inserted_id": str(result.inserted_id)}
                elif documents:
                    result = await collection.insert_many(documents)
                    return {"inserted_ids": [str(id) for id in result.inserted_ids]}
                else:
                    raise ValueError("write operation requires 'document' or 'documents' parameter")

            elif operation == "update":
                filter_query = params.get("filter", {}) if params else {}
                update = params.get("update") if params else None
                upsert = params.get("upsert", False) if params else False

                if not update:
                    raise ValueError("update operation requires 'update' parameter")

                result = await collection.update_many(filter_query, update, upsert=upsert)
                return {
                    "matched_count": result.matched_count,
                    "modified_count": result.modified_count,
                    "upserted_id": str(result.upserted_id) if result.upserted_id else None,
                }

            elif operation == "delete":
                filter_query = params.get("filter", {}) if params else {}
                result = await collection.delete_many(filter_query)
                return {"deleted_count": result.deleted_count}

            elif operation == "aggregate":
                pipeline = params.get("pipeline", []) if params else []
                cursor = collection.aggregate(pipeline)
                results = await cursor.to_list(length=1000)

                for doc in results:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])

                return {"results": results, "count": len(results)}

            else:
                raise ValueError(f"Unknown MongoDB operation: {operation}")

        finally:
            client.close()

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
        """Execute S3 operation using aioboto3."""
        try:
            import aioboto3
        except ImportError:
            raise RuntimeError("aioboto3 package required for S3. Install with: pip install aioboto3")

        config = connector.connection_config
        region = config.get("region", "us-east-1")
        access_key = config.get("access_key")
        secret_key = config.get("secret_key")
        endpoint_url = config.get("endpoint_url")  # For S3-compatible services like MinIO

        session = aioboto3.Session()
        client_config = {
            "region_name": region,
        }
        if access_key and secret_key:
            client_config["aws_access_key_id"] = access_key
            client_config["aws_secret_access_key"] = secret_key
        if endpoint_url:
            client_config["endpoint_url"] = endpoint_url

        params = params or {}
        bucket = params.get("bucket")

        async with session.client("s3", **client_config) as s3:
            if operation == "read" or operation == "get":
                if not bucket:
                    raise ValueError("S3 read requires 'bucket' parameter")

                key = params.get("key")
                if not key:
                    raise ValueError("S3 read requires 'key' parameter")

                response = await s3.get_object(Bucket=bucket, Key=key)
                body = await response["Body"].read()

                # Try to decode as text, otherwise return base64
                try:
                    content = body.decode("utf-8")
                    return {
                        "bucket": bucket,
                        "key": key,
                        "content": content,
                        "content_type": response.get("ContentType"),
                        "size": len(body),
                    }
                except UnicodeDecodeError:
                    import base64
                    return {
                        "bucket": bucket,
                        "key": key,
                        "content_base64": base64.b64encode(body).decode(),
                        "content_type": response.get("ContentType"),
                        "size": len(body),
                    }

            elif operation == "write" or operation == "put":
                if not bucket:
                    raise ValueError("S3 write requires 'bucket' parameter")

                key = params.get("key")
                content = params.get("content")
                content_type = params.get("content_type", "application/octet-stream")

                if not key or content is None:
                    raise ValueError("S3 write requires 'key' and 'content' parameters")

                # Handle base64-encoded binary content
                if isinstance(content, str) and params.get("base64"):
                    import base64
                    content = base64.b64decode(content)
                elif isinstance(content, str):
                    content = content.encode("utf-8")

                await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=content,
                    ContentType=content_type,
                )

                return {
                    "bucket": bucket,
                    "key": key,
                    "size": len(content),
                    "status": "uploaded",
                }

            elif operation == "delete":
                if not bucket:
                    raise ValueError("S3 delete requires 'bucket' parameter")

                key = params.get("key")
                keys = params.get("keys")

                if key:
                    await s3.delete_object(Bucket=bucket, Key=key)
                    return {"bucket": bucket, "key": key, "status": "deleted"}
                elif keys:
                    # Bulk delete
                    objects = [{"Key": k} for k in keys]
                    response = await s3.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": objects},
                    )
                    deleted = response.get("Deleted", [])
                    return {
                        "bucket": bucket,
                        "deleted": [d["Key"] for d in deleted],
                        "count": len(deleted),
                    }
                else:
                    raise ValueError("S3 delete requires 'key' or 'keys' parameter")

            elif operation == "list":
                if not bucket:
                    raise ValueError("S3 list requires 'bucket' parameter")

                prefix = params.get("prefix", "")
                max_keys = params.get("max_keys", 1000)

                response = await s3.list_objects_v2(
                    Bucket=bucket,
                    Prefix=prefix,
                    MaxKeys=max_keys,
                )

                contents = response.get("Contents", [])
                return {
                    "bucket": bucket,
                    "prefix": prefix,
                    "objects": [
                        {
                            "key": obj["Key"],
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                        }
                        for obj in contents
                    ],
                    "count": len(contents),
                    "truncated": response.get("IsTruncated", False),
                }

            elif operation == "head":
                if not bucket:
                    raise ValueError("S3 head requires 'bucket' parameter")

                key = params.get("key")
                if not key:
                    raise ValueError("S3 head requires 'key' parameter")

                try:
                    response = await s3.head_object(Bucket=bucket, Key=key)
                    return {
                        "bucket": bucket,
                        "key": key,
                        "exists": True,
                        "size": response.get("ContentLength"),
                        "content_type": response.get("ContentType"),
                        "last_modified": response.get("LastModified").isoformat() if response.get("LastModified") else None,
                    }
                except Exception:
                    return {"bucket": bucket, "key": key, "exists": False}

            elif operation == "copy":
                if not bucket:
                    raise ValueError("S3 copy requires 'bucket' parameter")

                source_key = params.get("source_key")
                dest_key = params.get("dest_key")
                source_bucket = params.get("source_bucket", bucket)

                if not source_key or not dest_key:
                    raise ValueError("S3 copy requires 'source_key' and 'dest_key' parameters")

                await s3.copy_object(
                    Bucket=bucket,
                    Key=dest_key,
                    CopySource={"Bucket": source_bucket, "Key": source_key},
                )

                return {
                    "source_bucket": source_bucket,
                    "source_key": source_key,
                    "dest_bucket": bucket,
                    "dest_key": dest_key,
                    "status": "copied",
                }

            else:
                raise ValueError(f"Unknown S3 operation: {operation}")

    async def _execute_redis(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute Redis operation using redis-py async."""
        import redis.asyncio as aioredis

        config = connector.connection_config
        host = config.get("host", "localhost")
        port = config.get("port", 6379)
        db = config.get("db", 0)
        password = config.get("password")

        client = aioredis.Redis(host=host, port=port, db=db, password=password)

        try:
            params = params or {}

            if operation == "read":
                # Get key(s)
                key = params.get("key")
                keys = params.get("keys")
                pattern = params.get("pattern")

                if key:
                    value = await client.get(key)
                    return {"key": key, "value": value.decode() if value else None}
                elif keys:
                    values = await client.mget(*keys)
                    return {
                        "keys": keys,
                        "values": {k: v.decode() if v else None for k, v in zip(keys, values)},
                    }
                elif pattern:
                    matching_keys = []
                    async for k in client.scan_iter(match=pattern, count=100):
                        matching_keys.append(k.decode())
                        if len(matching_keys) >= 100:
                            break
                    return {"pattern": pattern, "keys": matching_keys}
                else:
                    raise ValueError("read operation requires 'key', 'keys', or 'pattern' parameter")

            elif operation == "write":
                key = params.get("key")
                value = params.get("value")
                ttl = params.get("ttl")  # seconds
                mapping = params.get("mapping")  # for mset

                if key and value is not None:
                    if ttl:
                        await client.setex(key, ttl, value)
                    else:
                        await client.set(key, value)
                    return {"key": key, "status": "set"}
                elif mapping:
                    await client.mset(mapping)
                    return {"keys": list(mapping.keys()), "status": "set"}
                else:
                    raise ValueError("write operation requires 'key'+'value' or 'mapping' parameter")

            elif operation == "delete":
                key = params.get("key")
                keys = params.get("keys")
                pattern = params.get("pattern")

                if key:
                    deleted = await client.delete(key)
                    return {"key": key, "deleted": deleted}
                elif keys:
                    deleted = await client.delete(*keys)
                    return {"keys": keys, "deleted": deleted}
                elif pattern:
                    # Delete by pattern (be careful with this)
                    deleted_count = 0
                    async for k in client.scan_iter(match=pattern, count=100):
                        await client.delete(k)
                        deleted_count += 1
                        if deleted_count >= 1000:  # Safety limit
                            break
                    return {"pattern": pattern, "deleted": deleted_count}
                else:
                    raise ValueError("delete operation requires 'key', 'keys', or 'pattern' parameter")

            elif operation == "hash_read":
                key = params.get("key")
                field = params.get("field")
                fields = params.get("fields")

                if not key:
                    raise ValueError("hash operations require 'key' parameter")

                if field:
                    value = await client.hget(key, field)
                    return {"key": key, "field": field, "value": value.decode() if value else None}
                elif fields:
                    values = await client.hmget(key, *fields)
                    return {
                        "key": key,
                        "values": {f: v.decode() if v else None for f, v in zip(fields, values)},
                    }
                else:
                    all_values = await client.hgetall(key)
                    return {
                        "key": key,
                        "values": {k.decode(): v.decode() for k, v in all_values.items()},
                    }

            elif operation == "hash_write":
                key = params.get("key")
                mapping = params.get("mapping", {})

                if not key or not mapping:
                    raise ValueError("hash_write requires 'key' and 'mapping' parameters")

                await client.hset(key, mapping=mapping)
                return {"key": key, "fields": list(mapping.keys()), "status": "set"}

            elif operation == "list_read":
                key = params.get("key")
                start = params.get("start", 0)
                end = params.get("end", -1)

                if not key:
                    raise ValueError("list operations require 'key' parameter")

                values = await client.lrange(key, start, end)
                return {"key": key, "values": [v.decode() for v in values]}

            elif operation == "list_write":
                key = params.get("key")
                values = params.get("values", [])
                position = params.get("position", "right")  # left or right

                if not key:
                    raise ValueError("list_write requires 'key' parameter")

                if position == "left":
                    await client.lpush(key, *values)
                else:
                    await client.rpush(key, *values)
                return {"key": key, "added": len(values), "position": position}

            elif operation == "incr":
                key = params.get("key")
                amount = params.get("amount", 1)

                if not key:
                    raise ValueError("incr requires 'key' parameter")

                new_value = await client.incrby(key, amount)
                return {"key": key, "value": new_value}

            elif operation == "expire":
                key = params.get("key")
                ttl = params.get("ttl")

                if not key or not ttl:
                    raise ValueError("expire requires 'key' and 'ttl' parameters")

                result = await client.expire(key, ttl)
                return {"key": key, "ttl": ttl, "success": result}

            else:
                raise ValueError(f"Unknown Redis operation: {operation}")

        finally:
            await client.close()

    async def _execute_elasticsearch(
        self,
        connector: Connector,
        operation: str,
        query: str | None,
        params: dict | None,
    ) -> dict:
        """Execute Elasticsearch operation using elasticsearch-py async."""
        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError:
            raise RuntimeError("elasticsearch package required. Install with: pip install elasticsearch[async]")

        config = connector.connection_config
        hosts = config.get("hosts", ["http://localhost:9200"])
        api_key = config.get("api_key")
        username = config.get("username")
        password = config.get("password")

        # Build client config
        client_config = {"hosts": hosts}
        if api_key:
            client_config["api_key"] = api_key
        elif username and password:
            client_config["basic_auth"] = (username, password)

        client = AsyncElasticsearch(**client_config)

        try:
            params = params or {}
            index = params.get("index")

            if operation == "read" or operation == "search":
                if not index:
                    raise ValueError("search requires 'index' parameter")

                query_body = params.get("query", {"match_all": {}})
                size = params.get("size", 10)
                from_ = params.get("from", 0)
                sort = params.get("sort")
                source = params.get("_source")

                body = {"query": query_body, "size": size, "from": from_}
                if sort:
                    body["sort"] = sort
                if source:
                    body["_source"] = source

                result = await client.search(index=index, body=body)

                hits = result.get("hits", {})
                return {
                    "total": hits.get("total", {}).get("value", 0),
                    "hits": [
                        {
                            "_id": hit["_id"],
                            "_score": hit.get("_score"),
                            "_source": hit.get("_source", {}),
                        }
                        for hit in hits.get("hits", [])
                    ],
                }

            elif operation == "write" or operation == "index":
                if not index:
                    raise ValueError("index operation requires 'index' parameter")

                document = params.get("document")
                doc_id = params.get("id")

                if not document:
                    raise ValueError("index operation requires 'document' parameter")

                result = await client.index(index=index, id=doc_id, document=document)
                return {
                    "_id": result["_id"],
                    "result": result["result"],
                    "_version": result.get("_version"),
                }

            elif operation == "bulk":
                if not index:
                    raise ValueError("bulk operation requires 'index' parameter")

                documents = params.get("documents", [])
                if not documents:
                    raise ValueError("bulk operation requires 'documents' parameter")

                # Build bulk operations
                operations = []
                for doc in documents:
                    doc_id = doc.pop("_id", None)
                    operations.append({"index": {"_index": index, "_id": doc_id}})
                    operations.append(doc)

                result = await client.bulk(operations=operations)
                return {
                    "took": result.get("took"),
                    "errors": result.get("errors"),
                    "items_count": len(result.get("items", [])),
                }

            elif operation == "delete":
                if not index:
                    raise ValueError("delete operation requires 'index' parameter")

                doc_id = params.get("id")
                query_body = params.get("query")

                if doc_id:
                    result = await client.delete(index=index, id=doc_id)
                    return {"_id": doc_id, "result": result["result"]}
                elif query_body:
                    result = await client.delete_by_query(index=index, query=query_body)
                    return {
                        "deleted": result.get("deleted", 0),
                        "total": result.get("total", 0),
                    }
                else:
                    raise ValueError("delete requires 'id' or 'query' parameter")

            elif operation == "get":
                if not index:
                    raise ValueError("get operation requires 'index' parameter")

                doc_id = params.get("id")
                if not doc_id:
                    raise ValueError("get operation requires 'id' parameter")

                result = await client.get(index=index, id=doc_id)
                return {
                    "_id": result["_id"],
                    "_source": result.get("_source", {}),
                    "found": result.get("found", True),
                }

            elif operation == "count":
                if not index:
                    raise ValueError("count operation requires 'index' parameter")

                query_body = params.get("query", {"match_all": {}})
                result = await client.count(index=index, query=query_body)
                return {"count": result["count"]}

            elif operation == "update":
                if not index:
                    raise ValueError("update operation requires 'index' parameter")

                doc_id = params.get("id")
                doc = params.get("doc")
                script = params.get("script")

                if not doc_id:
                    raise ValueError("update requires 'id' parameter")

                if doc:
                    result = await client.update(index=index, id=doc_id, doc=doc)
                elif script:
                    result = await client.update(index=index, id=doc_id, script=script)
                else:
                    raise ValueError("update requires 'doc' or 'script' parameter")

                return {
                    "_id": result["_id"],
                    "result": result["result"],
                    "_version": result.get("_version"),
                }

            elif operation == "aggregate":
                if not index:
                    raise ValueError("aggregate operation requires 'index' parameter")

                aggs = params.get("aggs", {})
                query_body = params.get("query", {"match_all": {}})

                result = await client.search(
                    index=index,
                    body={"query": query_body, "aggs": aggs, "size": 0},
                )

                return {"aggregations": result.get("aggregations", {})}

            else:
                raise ValueError(f"Unknown Elasticsearch operation: {operation}")

        finally:
            await client.close()

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
