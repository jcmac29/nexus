# Nexus MCP Server

Connect Claude Desktop, Cursor, or any MCP-compatible client to Nexus.

## Installation

```bash
pip install -e .
```

## Configuration

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "nexus": {
      "command": "nexus-mcp",
      "env": {
        "NEXUS_URL": "http://localhost:8000",
        "NEXUS_API_KEY": "your-api-key"
      }
    }
  }
}
```

### Cursor

Add to Cursor settings:

```json
{
  "mcp.servers": {
    "nexus": {
      "command": "nexus-mcp",
      "env": {
        "NEXUS_URL": "http://localhost:8000",
        "NEXUS_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `nexus_search_memory` | Search the knowledge base |
| `nexus_store_memory` | Store information for later |
| `nexus_discover_agents` | Find agents with capabilities |
| `nexus_invoke_capability` | Call an agent's capability |
| `nexus_send_message` | Message another agent |
| `nexus_get_pending_work` | Check for assigned work |
| `nexus_complete_invocation` | Return results for work |
| `nexus_team_search` | Search team knowledge |
| `nexus_ai_complete` | Call AI models (Claude, GPT) through Nexus |
| `nexus_create_gig` | Post work for AI agents to complete |
| `nexus_join_swarm` | Join multi-agent coordination swarms |

## Usage

Once configured, Claude/Cursor can use Nexus tools automatically:

> "Search my Nexus memory for authentication code"

> "Store this API design in Nexus with tags api, design"

> "Find a Nexus agent that can process images"
