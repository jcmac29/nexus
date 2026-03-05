"""Tool service - Execute tools and manage tool definitions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select, and_

# SECURITY: Use sandboxed Jinja2 environment to prevent SSTI attacks
_jinja_env = SandboxedEnvironment(
    autoescape=True,
    # Disable dangerous features
    extensions=[],
)
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.tools.models import Tool, ToolExecution, ToolCategory, AuthType


class ToolService:
    """Service for managing and executing tools."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: dict[str, tuple[Any, float]] = {}  # Simple in-memory cache

    async def create_tool(
        self,
        name: str,
        slug: str,
        owner_id: UUID,
        description: str | None = None,
        category: ToolCategory = ToolCategory.CUSTOM,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        endpoint_url: str | None = None,
        http_method: str = "POST",
        headers: dict | None = None,
        auth_type: AuthType = AuthType.NONE,
        auth_config: dict | None = None,
        request_template: str | None = None,
        response_mapping: dict | None = None,
        **kwargs,
    ) -> Tool:
        """Create a new tool definition."""
        tool = Tool(
            name=name,
            slug=slug,
            description=description,
            category=category,
            owner_id=owner_id,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            endpoint_url=endpoint_url,
            http_method=http_method,
            headers=headers or {},
            auth_type=auth_type,
            auth_config=auth_config or {},
            request_template=request_template,
            response_mapping=response_mapping or {},
            **kwargs,
        )
        self.db.add(tool)
        await self.db.commit()
        await self.db.refresh(tool)
        return tool

    async def get_tool(self, tool_id: UUID) -> Tool | None:
        """Get a tool by ID."""
        result = await self.db.execute(select(Tool).where(Tool.id == tool_id))
        return result.scalar_one_or_none()

    async def get_tool_by_slug(self, slug: str) -> Tool | None:
        """Get a tool by slug."""
        result = await self.db.execute(select(Tool).where(Tool.slug == slug))
        return result.scalar_one_or_none()

    async def list_tools(
        self,
        owner_id: UUID | None = None,
        category: ToolCategory | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[Tool]:
        """List tools with optional filters."""
        query = select(Tool)

        if owner_id:
            query = query.where(Tool.owner_id == owner_id)
        if category:
            query = query.where(Tool.category == category)
        if active_only:
            query = query.where(Tool.is_active == True)

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def execute_tool(
        self,
        tool_id: UUID,
        input_data: dict,
        executor_id: UUID,
        executor_type: str = "agent",
        conversation_id: UUID | None = None,
        invocation_id: UUID | None = None,
    ) -> ToolExecution:
        """Execute a tool and return the execution record."""
        tool = await self.get_tool(tool_id)
        if not tool:
            raise ValueError(f"Tool {tool_id} not found")

        if not tool.is_active:
            raise ValueError(f"Tool {tool.name} is not active")

        # Create execution record
        execution = ToolExecution(
            tool_id=tool_id,
            executor_id=executor_id,
            executor_type=executor_type,
            conversation_id=conversation_id,
            invocation_id=invocation_id,
            input_data=input_data,
            status="running",
        )
        self.db.add(execution)
        await self.db.flush()

        start_time = time.time()

        try:
            # Check cache
            if tool.cache_enabled:
                cache_key = self._get_cache_key(tool_id, input_data)
                cached = self._get_from_cache(cache_key, tool.cache_ttl)
                if cached is not None:
                    execution.output_data = cached
                    execution.status = "success"
                    execution.completed_at = datetime.utcnow()
                    execution.duration_ms = (time.time() - start_time) * 1000
                    await self.db.commit()
                    return execution

            # Execute based on category
            if tool.category == ToolCategory.API:
                result = await self._execute_api_tool(tool, input_data, execution)
            elif tool.category == ToolCategory.DATABASE:
                result = await self._execute_database_tool(tool, input_data)
            else:
                result = await self._execute_custom_tool(tool, input_data)

            # Apply response mapping
            if tool.response_mapping:
                result = self._apply_response_mapping(result, tool.response_mapping)

            # Cache result
            if tool.cache_enabled:
                self._set_cache(cache_key, result, tool.cache_ttl)

            execution.output_data = result
            execution.status = "success"

            # Update tool stats
            tool.total_executions += 1
            tool.successful_executions += 1

        except Exception as e:
            execution.error = str(e)
            execution.status = "failed"
            tool.total_executions += 1

        execution.completed_at = datetime.utcnow()
        execution.duration_ms = (time.time() - start_time) * 1000

        # Update average latency
        if tool.successful_executions > 0:
            tool.avg_latency_ms = (
                (tool.avg_latency_ms * (tool.successful_executions - 1) + execution.duration_ms)
                / tool.successful_executions
            )

        await self.db.commit()
        await self.db.refresh(execution)
        return execution

    async def _execute_api_tool(
        self,
        tool: Tool,
        input_data: dict,
        execution: ToolExecution,
    ) -> dict:
        """Execute an API tool."""
        if not tool.endpoint_url:
            raise ValueError("API tool requires endpoint_url")

        # Build request body
        if tool.request_template:
            # SECURITY: Use sandboxed template to prevent SSTI attacks
            try:
                template = _jinja_env.from_string(tool.request_template)
                body = template.render(**input_data)
            except Exception:
                # If template rendering fails, fall back to input data
                body = input_data
            else:
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    pass  # Keep as string
        else:
            body = input_data

        # Build headers
        headers = dict(tool.headers or {})

        # Add authentication
        if tool.auth_type == AuthType.API_KEY:
            header_name = tool.auth_config.get("header_name", "X-API-Key")
            headers[header_name] = tool.auth_config.get("api_key", "")
        elif tool.auth_type == AuthType.BEARER:
            headers["Authorization"] = f"Bearer {tool.auth_config.get('token', '')}"
        elif tool.auth_type == AuthType.BASIC:
            import base64
            credentials = f"{tool.auth_config.get('username', '')}:{tool.auth_config.get('password', '')}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        # Make request with retries
        last_error = None
        for attempt in range(tool.retry_count + 1):
            try:
                async with httpx.AsyncClient(timeout=tool.timeout) as client:
                    if tool.http_method.upper() == "GET":
                        response = await client.get(
                            tool.endpoint_url,
                            headers=headers,
                            params={**tool.query_params, **input_data},
                        )
                    elif tool.http_method.upper() == "POST":
                        response = await client.post(
                            tool.endpoint_url,
                            headers=headers,
                            json=body if isinstance(body, dict) else None,
                            content=body if isinstance(body, str) else None,
                            params=tool.query_params,
                        )
                    elif tool.http_method.upper() == "PUT":
                        response = await client.put(
                            tool.endpoint_url,
                            headers=headers,
                            json=body if isinstance(body, dict) else None,
                            params=tool.query_params,
                        )
                    elif tool.http_method.upper() == "DELETE":
                        response = await client.delete(
                            tool.endpoint_url,
                            headers=headers,
                            params=tool.query_params,
                        )
                    else:
                        raise ValueError(f"Unsupported HTTP method: {tool.http_method}")

                # Log request/response for debugging
                execution.request_log = {
                    "url": str(response.url),
                    "method": tool.http_method,
                    "headers": {k: v for k, v in headers.items() if "auth" not in k.lower()},
                }
                execution.response_log = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                }

                response.raise_for_status()

                # Parse response
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {"text": response.text}

            except Exception as e:
                last_error = e
                if attempt < tool.retry_count:
                    await asyncio.sleep(tool.retry_delay * (attempt + 1))

        raise last_error or Exception("Request failed")

    async def _execute_database_tool(self, tool: Tool, input_data: dict) -> dict:
        """Execute a database tool (placeholder - needs specific DB integration)."""
        # This would integrate with the configured database
        # For now, return a placeholder
        raise NotImplementedError("Database tools require specific integration")

    async def _execute_custom_tool(self, tool: Tool, input_data: dict) -> dict:
        """Execute a custom tool (could be webhook, internal logic, etc.)."""
        # Custom tools can have their own execution logic
        # This is a placeholder that just returns the input
        return {"received": input_data, "tool": tool.name}

    def _apply_response_mapping(self, data: dict, mapping: dict) -> dict:
        """Apply response mapping to transform output."""
        if not mapping:
            return data

        result = {}
        for target_key, source_path in mapping.items():
            value = data
            for key in source_path.split("."):
                if isinstance(value, dict):
                    value = value.get(key)
                elif isinstance(value, list) and key.isdigit():
                    value = value[int(key)] if int(key) < len(value) else None
                else:
                    value = None
                    break
            result[target_key] = value

        return result

    def _get_cache_key(self, tool_id: UUID, input_data: dict) -> str:
        """Generate cache key for tool execution."""
        data_str = json.dumps(input_data, sort_keys=True)
        return f"{tool_id}:{hashlib.md5(data_str.encode()).hexdigest()}"

    def _get_from_cache(self, key: str, ttl: int) -> Any | None:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < ttl:
                return value
            del self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any, ttl: int):
        """Set value in cache."""
        self._cache[key] = (value, time.time())

    async def health_check(self, tool_id: UUID) -> dict:
        """Perform health check on a tool."""
        tool = await self.get_tool(tool_id)
        if not tool:
            return {"status": "error", "message": "Tool not found"}

        if tool.category != ToolCategory.API or not tool.endpoint_url:
            return {"status": "ok", "message": "Health check not applicable"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(tool.endpoint_url)
                status = "healthy" if response.status_code < 400 else "unhealthy"
        except Exception as e:
            status = "unhealthy"

        tool.last_health_check = datetime.utcnow()
        tool.health_status = status
        await self.db.commit()

        return {"status": status, "checked_at": tool.last_health_check.isoformat()}
