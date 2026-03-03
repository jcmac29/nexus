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
- [ ] Graph memory (relationships)
- [ ] Webhooks
- [ ] Usage analytics
- [ ] Hosted cloud version

## License

MIT

---

Built for the AI agent ecosystem.
