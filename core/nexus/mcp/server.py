"""
MCP Server implementation for Nexus.

This module provides Nexus as an MCP server, allowing any MCP-compatible
client (like Claude) to use Nexus memory and discovery features directly.

Usage:
    Run as standalone MCP server:
    $ python -m nexus.mcp.server

    Or integrate into existing MCP setup.
"""

import json
from typing import Any

# MCP server implementation
# This is a simplified version - full implementation would use the mcp package

MCP_TOOLS = [
    {
        "name": "nexus_store_memory",
        "description": "Store a memory for later retrieval. Memories are automatically indexed for semantic search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Unique key for this memory",
                },
                "value": {
                    "type": "object",
                    "description": "The memory content (JSON object)",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace for organization (default: 'default')",
                    "default": "default",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization",
                },
                "text_content": {
                    "type": "string",
                    "description": "Text content for semantic search (auto-extracted if not provided)",
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "nexus_get_memory",
        "description": "Retrieve a stored memory by its key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The memory key to retrieve",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace (default: 'default')",
                    "default": "default",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "nexus_search_memory",
        "description": "Search memories using semantic similarity. Returns memories most relevant to the query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (natural language)",
                },
                "namespace": {
                    "type": "string",
                    "description": "Filter by namespace",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "nexus_delete_memory",
        "description": "Delete a memory by its key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The memory key to delete",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace (default: 'default')",
                    "default": "default",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "nexus_discover",
        "description": "Find AI agents with specific capabilities. Search across all registered agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic search query for capabilities",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by capability category",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 10)",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "nexus_register_capability",
        "description": "Register a capability for this agent, making it discoverable by others.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Capability name (e.g., 'text-translation')",
                },
                "description": {
                    "type": "string",
                    "description": "What this capability does",
                },
                "category": {
                    "type": "string",
                    "description": "Category (e.g., 'language', 'code', 'data')",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for filtering",
                },
            },
            "required": ["name"],
        },
    },
]


class NexusMCPServer:
    """
    MCP Server that exposes Nexus functionality.

    This allows MCP clients to use Nexus for memory and discovery.
    """

    def __init__(self, api_key: str, base_url: str = "http://localhost:8000/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self._client: Any = None

    def _get_client(self):
        """Lazy load the HTTP client."""
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
        return self._client

    def get_tools(self) -> list[dict]:
        """Return the list of MCP tools."""
        return MCP_TOOLS

    async def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Handle an MCP tool call."""
        client = self._get_client()

        if tool_name == "nexus_store_memory":
            response = client.post("/memory", json=arguments)
            response.raise_for_status()
            return {"success": True, "memory": response.json()}

        elif tool_name == "nexus_get_memory":
            key = arguments.pop("key")
            response = client.get(f"/memory/{key}", params=arguments)
            if response.status_code == 404:
                return {"success": False, "error": "Memory not found"}
            response.raise_for_status()
            return {"success": True, "memory": response.json()}

        elif tool_name == "nexus_search_memory":
            response = client.post("/memory/search", json=arguments)
            response.raise_for_status()
            return {"success": True, "results": response.json()["results"]}

        elif tool_name == "nexus_delete_memory":
            key = arguments.pop("key")
            namespace = arguments.get("namespace", "default")
            response = client.delete(f"/memory/{key}", params={"namespace": namespace})
            return {"success": response.status_code == 204}

        elif tool_name == "nexus_discover":
            response = client.get("/discover", params=arguments)
            response.raise_for_status()
            return {"success": True, "results": response.json()["results"]}

        elif tool_name == "nexus_register_capability":
            response = client.post("/capabilities", json=arguments)
            response.raise_for_status()
            return {"success": True, "capability": response.json()}

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}


def create_mcp_server(api_key: str, base_url: str = "http://localhost:8000/api/v1") -> NexusMCPServer:
    """Create an MCP server instance."""
    return NexusMCPServer(api_key=api_key, base_url=base_url)


# MCP Server manifest for registration
MCP_MANIFEST = {
    "name": "nexus",
    "version": "0.1.0",
    "description": "Nexus - Memory and discovery for AI agents",
    "tools": MCP_TOOLS,
}


def get_manifest() -> dict:
    """Return the MCP server manifest."""
    return MCP_MANIFEST


if __name__ == "__main__":
    # Print manifest for debugging
    print(json.dumps(MCP_MANIFEST, indent=2))
