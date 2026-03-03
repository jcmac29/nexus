# Nexus

**The connective layer for AI agents.** Identity, Memory, and Discovery in one platform.

```
┌─────────────────────────────────────────────────────────────┐
│                         Nexus                                │
├─────────────────────────────────────────────────────────────┤
│  Identity          │  Memory            │  Discovery        │
│  - Agent registration  │  - Store/retrieve   │  - Find agents    │
│  - API keys        │  - Semantic search │  - Capabilities   │
│  - Permissions     │  - Cross-agent share│  - Network        │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start Nexus

```bash
# Clone and start with Docker
git clone <repo>
cd nexus
docker-compose up -d
```

### 2. Register Your Agent

**Python:**
```python
from nexus_sdk import Nexus

# Register a new agent (one-time)
nexus = Nexus.register(
    slug="my-agent",
    name="My AI Agent",
    description="An agent that does cool things"
)
# Save the API key! It's only shown once.

# Or connect with existing key
nexus = Nexus(api_key="nex_xxx...")
```

**TypeScript:**
```typescript
import { Nexus } from '@nexus/sdk';

const nexus = await Nexus.register({
  slug: 'my-agent',
  name: 'My AI Agent'
});
```

### 3. Use Memory

```python
# Store a memory
nexus.memory.store("user_prefs", {
    "theme": "dark",
    "language": "en"
})

# Retrieve it
prefs = nexus.memory.get("user_prefs")

# Semantic search
results = nexus.memory.search("what are the user's preferences?")
```

### 4. Register Capabilities

```python
# Make your agent discoverable
nexus.capabilities.register(
    name="code-review",
    description="Reviews code for bugs and best practices",
    category="code",
    tags=["python", "javascript", "review"]
)
```

### 5. Discover Other Agents

```python
# Find agents that can translate
translators = nexus.discover(query="translate text between languages")

for result in translators:
    print(f"{result['agent_name']}: {result['capability']['description']}")
```

## Features

### Identity
- **Agent Registration**: Every agent gets a unique identity
- **API Keys**: Secure authentication with scoped permissions
- **Verification**: Verify agent identities cryptographically

### Memory
- **Persistent Storage**: Key-value + semantic search
- **Scopes**: Agent-level, user-level, session-level memories
- **Sharing**: Share memories with other agents (with permissions)
- **Auto-indexing**: Memories are automatically indexed for semantic search

### Discovery
- **Capability Registry**: Agents register what they can do
- **Semantic Search**: Find agents by capability description
- **Categories & Tags**: Filter by type of capability

### MCP Integration
Nexus works as an MCP server, so Claude and other MCP clients can use it directly:

```json
{
  "mcpServers": {
    "nexus": {
      "command": "python",
      "args": ["-m", "nexus.mcp.server"],
      "env": {
        "NEXUS_API_KEY": "nex_xxx..."
      }
    }
  }
}
```

### Graph Memory
Track relationships between memories, agents, and capabilities:

```python
# Create a relationship between memories
nexus.graph.create_relationship(
    source_type="memory",
    source_id=memory_a_id,
    target_type="memory",
    target_id=memory_b_id,
    relationship_type="references"
)

# Find related memories
related = nexus.graph.get_related_memories(memory_id)

# Traverse the graph
nodes = nexus.graph.traverse(
    start_type="memory",
    start_id=memory_id,
    max_depth=2
)
```

### Webhooks
Receive real-time notifications when events occur:

```python
# Register a webhook endpoint
webhook = nexus.webhooks.create(
    name="My Webhook",
    url="https://example.com/webhook",
    event_types=["memory.*", "agent.connected"]
)

# Webhook payloads are signed with HMAC-SHA256
# Verify with: X-Nexus-Signature header
```

### Usage Analytics
Track API usage, storage, and performance:

```python
# Get dashboard summary
dashboard = nexus.analytics.dashboard(days=7)

# Get detailed usage metrics
usage = nexus.analytics.usage(
    metric_types=["api_request", "memory_store"],
    granularity="day"
)

# Export data
nexus.analytics.export(format="csv", start_date="2024-01-01")
```

### Multi-Tenant (Hosted Cloud)
For SaaS deployments with tenant isolation:

```python
# Configure tenant settings
settings = nexus.tenants.create_settings(
    subdomain="acme",  # acme.nexus-cloud.com
    features={"graph_memory": True, "webhooks": True}
)

# Invite team members
nexus.tenants.invite(email="user@acme.com", role="member")

# Check resource limits
limits = nexus.tenants.get_limits()
```

## API Reference

### Identity

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agents` | POST | Register new agent |
| `/api/v1/agents/me` | GET | Get current agent |
| `/api/v1/agents/me` | PATCH | Update agent |
| `/api/v1/agents/me/keys` | POST | Create API key |
| `/api/v1/agents/me/keys` | GET | List API keys |

### Memory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/memory` | POST | Store memory |
| `/api/v1/memory/{key}` | GET | Get memory |
| `/api/v1/memory` | GET | List memories |
| `/api/v1/memory/{key}` | DELETE | Delete memory |
| `/api/v1/memory/search` | POST | Semantic search |
| `/api/v1/memory/{id}/share` | POST | Share memory |

### Discovery

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/capabilities` | POST | Register capability |
| `/api/v1/capabilities` | GET | List own capabilities |
| `/api/v1/capabilities/{name}` | DELETE | Remove capability |
| `/api/v1/discover` | GET | Search all capabilities |
| `/api/v1/discover/agents/{id}` | GET | Get agent capabilities |

### Graph

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/graph/relationships` | POST | Create relationship |
| `/api/v1/graph/relationships/{id}` | DELETE | Delete relationship |
| `/api/v1/graph/nodes/{type}/{id}/edges` | GET | Get node edges |
| `/api/v1/graph/traverse` | POST | Traverse graph |
| `/api/v1/graph/path` | POST | Find shortest path |
| `/api/v1/graph/memories/{id}/related` | GET | Get related memories |

### Webhooks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/webhooks` | POST | Create webhook |
| `/api/v1/webhooks` | GET | List webhooks |
| `/api/v1/webhooks/{id}` | GET | Get webhook |
| `/api/v1/webhooks/{id}` | PATCH | Update webhook |
| `/api/v1/webhooks/{id}` | DELETE | Delete webhook |
| `/api/v1/webhooks/{id}/test` | POST | Test webhook |
| `/api/v1/webhooks/{id}/deliveries` | GET | List delivery logs |

### Analytics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/analytics/dashboard` | GET | Dashboard summary |
| `/api/v1/analytics/usage` | GET | Usage metrics |
| `/api/v1/analytics/endpoints` | GET | Endpoint metrics |
| `/api/v1/analytics/storage` | GET | Storage usage |
| `/api/v1/analytics/export` | GET | Export data |

### Tenants

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/tenants/settings` | GET | Get tenant settings |
| `/api/v1/tenants/settings` | POST | Create tenant settings |
| `/api/v1/tenants/settings` | PATCH | Update tenant settings |
| `/api/v1/tenants/limits` | GET | Get resource limits |
| `/api/v1/tenants/invites` | POST | Create invite |
| `/api/v1/tenants/invites` | GET | List invites |

## Self-Hosting

### Docker Compose (Recommended)

```bash
docker-compose up -d
```

This starts:
- PostgreSQL with pgvector
- Redis
- Nexus API

### Manual Setup

```bash
# Install dependencies
cd core
pip install -e .

# Set environment variables
export DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/nexus
export REDIS_URL=redis://localhost:6379/0
export SECRET_KEY=your-secret-key

# Run migrations
python -c "from nexus.database import init_db; import asyncio; asyncio.run(init_db())"

# Start server
uvicorn nexus.main:app --host 0.0.0.0 --port 8000
```

## SDKs

### Python

```bash
pip install nexus-sdk
```

### TypeScript/JavaScript

```bash
npm install @nexus/sdk
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://nexus:nexus@localhost:5432/nexus` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `SECRET_KEY` | (required) | Secret for JWT signing |
| `DEBUG` | `false` | Enable debug mode |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |

## Architecture

```
nexus/
├── core/                    # Python API server
│   ├── nexus/
│   │   ├── identity/        # Agent registration, auth
│   │   ├── memory/          # Memory storage, search
│   │   ├── discovery/       # Capability registry
│   │   └── mcp/             # MCP server integration
│   └── tests/
├── sdk-python/              # Python SDK
├── sdk-typescript/          # TypeScript SDK
└── docs/                    # Documentation
```

## Roadmap

- [x] Identity system (agent registration, API keys)
- [x] Memory system (store, retrieve, search)
- [x] Discovery system (capabilities, search)
- [x] Python SDK
- [x] TypeScript SDK
- [x] MCP integration
- [x] Graph memory (relationships)
- [x] Webhooks
- [x] Usage analytics
- [x] Hosted cloud version

## License

MIT

---

Built for the AI agent ecosystem.
