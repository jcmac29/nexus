"""
Nexus MCP Server - Connect Claude Desktop/Cursor to Nexus.

This implements the Model Context Protocol (MCP) to expose Nexus
capabilities as tools that Claude can use directly.
"""

import asyncio
import json
import os
import sys
from typing import Any

import httpx

# MCP Protocol constants
JSONRPC_VERSION = "2.0"


class NexusMCPServer:
    """MCP Server that exposes Nexus capabilities to Claude."""

    def __init__(self):
        self.nexus_url = os.environ.get("NEXUS_URL", "http://localhost:8000")
        self.api_key = os.environ.get("NEXUS_API_KEY", "")
        self.client = httpx.AsyncClient(
            base_url=self.nexus_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )

    async def handle_request(self, request: dict) -> dict:
        """Handle incoming MCP request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                result = await self.handle_initialize(params)
            elif method == "tools/list":
                result = await self.handle_tools_list()
            elif method == "tools/call":
                result = await self.handle_tool_call(params)
            elif method == "resources/list":
                result = await self.handle_resources_list()
            elif method == "resources/read":
                result = await self.handle_resource_read(params)
            elif method == "prompts/list":
                result = await self.handle_prompts_list()
            elif method == "prompts/get":
                result = await self.handle_prompt_get(params)
            else:
                return self._error_response(request_id, -32601, f"Unknown method: {method}")

            return self._success_response(request_id, result)

        except Exception as e:
            return self._error_response(request_id, -32603, str(e))

    async def handle_initialize(self, params: dict) -> dict:
        """Handle MCP initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": "nexus-mcp",
                "version": "0.1.0",
            },
        }

    async def handle_tools_list(self) -> dict:
        """List available Nexus tools."""
        tools = [
            {
                "name": "nexus_search_memory",
                "description": "Search the Nexus knowledge base for relevant context and memories",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "nexus_store_memory",
                "description": "Store information in Nexus memory for later retrieval",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Unique key for this memory"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to store"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for organization"
                        }
                    },
                    "required": ["key", "content"]
                }
            },
            {
                "name": "nexus_discover_agents",
                "description": "Find AI agents with specific capabilities",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "capability": {
                            "type": "string",
                            "description": "Capability to search for"
                        }
                    },
                    "required": ["capability"]
                }
            },
            {
                "name": "nexus_invoke_capability",
                "description": "Invoke a capability on a Nexus agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Target agent ID"
                        },
                        "capability": {
                            "type": "string",
                            "description": "Capability name"
                        },
                        "input": {
                            "type": "object",
                            "description": "Input data for the capability"
                        }
                    },
                    "required": ["agent_id", "capability", "input"]
                }
            },
            {
                "name": "nexus_send_message",
                "description": "Send a message to another Nexus agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to_agent_id": {
                            "type": "string",
                            "description": "Recipient agent ID"
                        },
                        "subject": {
                            "type": "string",
                            "description": "Message subject"
                        },
                        "body": {
                            "type": "string",
                            "description": "Message body"
                        }
                    },
                    "required": ["to_agent_id", "subject", "body"]
                }
            },
            {
                "name": "nexus_get_pending_work",
                "description": "Check for pending invocations assigned to this agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "nexus_complete_invocation",
                "description": "Complete a pending invocation with results",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "invocation_id": {
                            "type": "string",
                            "description": "Invocation ID to complete"
                        },
                        "output": {
                            "type": "object",
                            "description": "Result data"
                        },
                        "success": {
                            "type": "boolean",
                            "description": "Whether it succeeded",
                            "default": True
                        }
                    },
                    "required": ["invocation_id", "output"]
                }
            },
            {
                "name": "nexus_team_search",
                "description": "Search shared team knowledge",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "nexus_ai_complete",
                "description": "Call an AI model (Claude, GPT, etc.) through Nexus",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message to send to the AI"
                        },
                        "provider": {
                            "type": "string",
                            "description": "AI provider (anthropic, openai)",
                            "enum": ["anthropic", "openai"],
                            "default": "anthropic"
                        },
                        "system_prompt": {
                            "type": "string",
                            "description": "System prompt for context"
                        }
                    },
                    "required": ["message"]
                }
            },
            {
                "name": "nexus_create_gig",
                "description": "Create a gig for AI workers to complete",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Gig title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description"
                        },
                        "required_capabilities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Capabilities needed"
                        },
                        "budget_credits": {
                            "type": "number",
                            "description": "Budget in credits"
                        }
                    },
                    "required": ["title", "description"]
                }
            },
            {
                "name": "nexus_join_swarm",
                "description": "Join a swarm for multi-agent coordination",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "join_code": {
                            "type": "string",
                            "description": "Swarm join code"
                        },
                        "capabilities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Your capabilities"
                        }
                    },
                    "required": ["join_code"]
                }
            },
        ]
        return {"tools": tools}

    async def handle_tool_call(self, params: dict) -> dict:
        """Execute a tool call."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handlers = {
            "nexus_search_memory": self._search_memory,
            "nexus_store_memory": self._store_memory,
            "nexus_discover_agents": self._discover_agents,
            "nexus_invoke_capability": self._invoke_capability,
            "nexus_send_message": self._send_message,
            "nexus_get_pending_work": self._get_pending_work,
            "nexus_complete_invocation": self._complete_invocation,
            "nexus_team_search": self._team_search,
            "nexus_ai_complete": self._ai_complete,
            "nexus_create_gig": self._create_gig,
            "nexus_join_swarm": self._join_swarm,
        }

        handler = handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")

        result = await handler(arguments)
        return {
            "content": [
                {"type": "text", "text": json.dumps(result, indent=2)}
            ]
        }

    async def handle_resources_list(self) -> dict:
        """List available resources (memories, files, etc.)."""
        # Get recent memories as resources
        try:
            response = await self.client.post(
                "/api/v1/memory/search",
                json={"query": "*", "limit": 20, "include_shared": True}
            )
            memories = response.json().get("results", [])

            resources = [
                {
                    "uri": f"nexus://memory/{m['memory']['id']}",
                    "name": m["memory"]["key"],
                    "mimeType": "application/json",
                    "description": f"Memory: {m['memory']['key']} (tags: {', '.join(m['memory'].get('tags', []))})"
                }
                for m in memories
            ]
        except:
            resources = []

        return {"resources": resources}

    async def handle_resource_read(self, params: dict) -> dict:
        """Read a specific resource."""
        uri = params.get("uri", "")

        if uri.startswith("nexus://memory/"):
            memory_id = uri.replace("nexus://memory/", "")
            response = await self.client.get(f"/api/v1/memory/{memory_id}")
            content = response.json()
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(content, indent=2)
                    }
                ]
            }

        raise ValueError(f"Unknown resource: {uri}")

    async def handle_prompts_list(self) -> dict:
        """List available prompts."""
        try:
            response = await self.client.get("/api/v1/profile/prompts")
            prompts_data = response.json()

            prompts = [
                {
                    "name": p["name"],
                    "description": p.get("description", ""),
                    "arguments": [
                        {"name": v, "required": True}
                        for v in p.get("variables", [])
                    ]
                }
                for p in prompts_data
            ]
        except:
            prompts = []

        return {"prompts": prompts}

    async def handle_prompt_get(self, params: dict) -> dict:
        """Get a specific prompt."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Find prompt by name
        response = await self.client.get("/api/v1/profile/prompts")
        prompts = response.json()

        prompt = next((p for p in prompts if p["name"] == name), None)
        if not prompt:
            raise ValueError(f"Prompt not found: {name}")

        # Render with variables
        render_response = await self.client.post(
            f"/api/v1/profile/prompts/{prompt['id']}/render",
            json={"variables": arguments}
        )
        rendered = render_response.json().get("rendered", "")

        return {
            "messages": [
                {"role": "user", "content": {"type": "text", "text": rendered}}
            ]
        }

    # --- Tool Implementations ---

    async def _search_memory(self, args: dict) -> dict:
        response = await self.client.post(
            "/api/v1/memory/search",
            json={
                "query": args["query"],
                "limit": args.get("limit", 5),
                "include_shared": True
            }
        )
        return response.json()

    async def _store_memory(self, args: dict) -> dict:
        response = await self.client.post(
            "/api/v1/memory",
            json={
                "key": args["key"],
                "value": {"content": args["content"]},
                "text_content": args["content"],
                "tags": args.get("tags", []),
                "scope": "shared"
            }
        )
        return response.json()

    async def _discover_agents(self, args: dict) -> dict:
        response = await self.client.get(
            f"/api/v1/discover/capabilities/{args['capability']}"
        )
        return response.json()

    async def _invoke_capability(self, args: dict) -> dict:
        response = await self.client.post(
            f"/api/v1/invoke/{args['agent_id']}/{args['capability']}",
            json={"input": args["input"]}
        )
        return response.json()

    async def _send_message(self, args: dict) -> dict:
        response = await self.client.post(
            "/api/v1/messages",
            json={
                "to_agent_id": args["to_agent_id"],
                "subject": args["subject"],
                "body": args["body"]
            }
        )
        return response.json()

    async def _get_pending_work(self, args: dict) -> dict:
        response = await self.client.get("/api/v1/agents/me/pending")
        return response.json()

    async def _complete_invocation(self, args: dict) -> dict:
        response = await self.client.post(
            f"/api/v1/invocations/{args['invocation_id']}/complete",
            json={
                "output": args["output"],
                "success": args.get("success", True)
            }
        )
        return response.json()

    async def _team_search(self, args: dict) -> dict:
        response = await self.client.post(
            "/api/v1/memory/search",
            json={
                "query": args["query"],
                "limit": 10,
                "include_shared": True,
                "scope": "shared"
            }
        )
        return response.json()

    async def _ai_complete(self, args: dict) -> dict:
        """Call an AI model through Nexus LLM router."""
        response = await self.client.post(
            "/api/v1/llm/chat",
            json={
                "message": args["message"],
                "provider": args.get("provider", "anthropic"),
                "system_prompt": args.get("system_prompt"),
            }
        )
        return response.json()

    async def _create_gig(self, args: dict) -> dict:
        """Create a gig for AI workers."""
        response = await self.client.post(
            "/api/v1/gigs",
            json={
                "title": args["title"],
                "description": args["description"],
                "required_capabilities": args.get("required_capabilities", []),
                "budget_credits": args.get("budget_credits", 0),
            }
        )
        return response.json()

    async def _join_swarm(self, args: dict) -> dict:
        """Join a swarm for multi-agent coordination."""
        response = await self.client.post(
            "/api/v1/swarm/join",
            json={
                "join_code": args["join_code"],
                "capabilities": args.get("capabilities", []),
            }
        )
        return response.json()

    # --- Helpers ---

    def _success_response(self, request_id: Any, result: dict) -> dict:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "result": result,
        }

    def _error_response(self, request_id: Any, code: int, message: str) -> dict:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }


async def main():
    """Run the MCP server."""
    server = NexusMCPServer()

    # Read from stdin, write to stdout (MCP protocol)
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line)
            response = await server.handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_response = {
                "jsonrpc": JSONRPC_VERSION,
                "id": None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


def run():
    """Entry point for the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
