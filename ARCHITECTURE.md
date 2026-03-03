# Nexus - Technical Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Clients                                   │
├─────────────────────────────────────────────────────────────────┤
│  Python SDK  │  TypeScript SDK  │  REST API  │  MCP Interface   │
└──────┬───────┴────────┬─────────┴──────┬─────┴────────┬─────────┘
       │                │                │              │
       └────────────────┴────────────────┴──────────────┘
                                │
                    ┌───────────▼───────────┐
                    │      API Gateway       │
                    │   (Auth + Rate Limit)  │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Identity    │     │     Memory      │     │    Discovery    │
│   Service     │     │     Service     │     │    Service      │
└───────┬───────┘     └────────┬────────┘     └────────┬────────┘
        │                      │                       │
        └──────────────────────┼───────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │      Data Layer      │
                    ├──────────────────────┤
                    │  PostgreSQL + pgvec  │
                    │  Redis (cache/queue) │
                    └──────────────────────┘
```

## Technology Stack

### Core (Python)
- **Framework**: FastAPI (async, OpenAPI docs, fast)
- **Database**: PostgreSQL 15+ with pgvector extension
- **Cache/Queue**: Redis (caching, rate limiting, pub/sub)
- **ORM**: SQLAlchemy 2.0 (async)
- **Embeddings**: sentence-transformers (local) or OpenAI (optional)
- **Auth**: JWT + API keys

### SDKs
- **Python**: `nexus-sdk` (sync + async)
- **TypeScript**: `@nexus/sdk` (Node.js + browser)

### Infrastructure
- **Container**: Docker + Docker Compose
- **Cloud**: Fly.io or Railway (simple, cheap to start)
- **CI/CD**: GitHub Actions

## Data Models

### Agent (Identity)

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    public_key TEXT,
    metadata JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(10) NOT NULL,  -- for display: "nex_abc..."
    scopes TEXT[] DEFAULT ARRAY['read', 'write'],
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Memory

```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    namespace VARCHAR(255) DEFAULT 'default',
    key VARCHAR(255) NOT NULL,
    value JSONB NOT NULL,
    embedding vector(384),  -- for semantic search
    scope VARCHAR(50) DEFAULT 'agent',  -- agent, user, session, shared
    user_id VARCHAR(255),  -- optional, for user-scoped memories
    session_id VARCHAR(255),  -- optional, for session-scoped
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(agent_id, namespace, key, user_id, session_id)
);

CREATE INDEX memories_embedding_idx ON memories
    USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE memory_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    shared_with_agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    permissions TEXT[] DEFAULT ARRAY['read'],
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Discovery (Capabilities)

```sql
CREATE TABLE capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    embedding vector(384),  -- for semantic search
    metadata JSONB DEFAULT '{}',
    endpoint_url TEXT,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(agent_id, name)
);

CREATE INDEX capabilities_embedding_idx ON capabilities
    USING ivfflat (embedding vector_cosine_ops);
```

## API Design

### Base URL
- Self-hosted: `http://localhost:8000/api/v1`
- Cloud: `https://api.nexus.dev/v1`

### Authentication
All requests require API key in header:
```
Authorization: Bearer nex_xxxxxxxxxxxxx
```

### Endpoints

#### Identity
```
POST   /agents                 # Register new agent
GET    /agents/me              # Get current agent info
PATCH  /agents/me              # Update agent metadata
DELETE /agents/me              # Delete agent

POST   /agents/me/keys         # Create new API key
GET    /agents/me/keys         # List API keys
DELETE /agents/me/keys/:id     # Revoke API key
```

#### Memory
```
POST   /memory                 # Store memory
GET    /memory/:key            # Get memory by key
GET    /memory                 # List memories (with filters)
DELETE /memory/:key            # Delete memory
POST   /memory/search          # Semantic search

POST   /memory/:key/share      # Share memory with agent
DELETE /memory/:key/share/:id  # Revoke share
```

#### Discovery
```
POST   /capabilities           # Register capability
GET    /capabilities           # List own capabilities
DELETE /capabilities/:name     # Remove capability

GET    /discover               # Search all capabilities
GET    /discover/agents/:id    # Get agent's capabilities
```

### Request/Response Examples

#### Register Agent
```bash
POST /agents
{
    "name": "My Code Review Agent",
    "slug": "code-review-agent",
    "metadata": {
        "version": "1.0.0",
        "author": "developer@example.com"
    }
}

# Response
{
    "agent": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "My Code Review Agent",
        "slug": "code-review-agent",
        "status": "active"
    },
    "api_key": "nex_live_abc123..."  # Only shown once
}
```

#### Store Memory
```bash
POST /memory
Authorization: Bearer nex_live_abc123...
{
    "key": "user_preferences",
    "value": {
        "theme": "dark",
        "language": "en"
    },
    "namespace": "settings",
    "scope": "user",
    "user_id": "user_123"
}

# Response
{
    "id": "memory-uuid",
    "key": "user_preferences",
    "created_at": "2026-03-02T..."
}
```

#### Semantic Search
```bash
POST /memory/search
{
    "query": "what are the user's color preferences?",
    "limit": 5,
    "namespace": "settings"
}

# Response
{
    "results": [
        {
            "key": "user_preferences",
            "value": {"theme": "dark", ...},
            "score": 0.89
        }
    ]
}
```

#### Discover Capabilities
```bash
GET /discover?q=translation&limit=10

# Response
{
    "results": [
        {
            "agent_id": "...",
            "agent_name": "Translation Service",
            "capability": "text-translation",
            "description": "Translate text between 50+ languages",
            "endpoint_url": "https://...",
            "score": 0.95
        }
    ]
}
```

## MCP Integration

Nexus exposes itself as an MCP server with these tools:

```json
{
    "tools": [
        {
            "name": "nexus_store_memory",
            "description": "Store a memory for later retrieval",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "object"},
                    "namespace": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        },
        {
            "name": "nexus_get_memory",
            "description": "Retrieve a stored memory",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "namespace": {"type": "string"}
                },
                "required": ["key"]
            }
        },
        {
            "name": "nexus_search_memory",
            "description": "Search memories semantically",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "nexus_discover",
            "description": "Find agents with specific capabilities",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string"},
                    "query": {"type": "string"}
                }
            }
        }
    ]
}
```

## Directory Structure

```
nexus/
├── PRODUCT_SPEC.md
├── ARCHITECTURE.md
├── README.md
├── LICENSE
├── docker-compose.yml
├── Makefile
│
├── core/                    # Python core service
│   ├── pyproject.toml
│   ├── nexus/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI app
│   │   ├── config.py        # Settings
│   │   ├── database.py      # DB connection
│   │   │
│   │   ├── identity/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   └── service.py
│   │   │
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── service.py
│   │   │   └── embeddings.py
│   │   │
│   │   ├── discovery/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   └── service.py
│   │   │
│   │   └── mcp/
│   │       ├── __init__.py
│   │       └── server.py
│   │
│   └── tests/
│
├── sdk-python/              # Python SDK
│   ├── pyproject.toml
│   ├── nexus_sdk/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── memory.py
│   │   ├── identity.py
│   │   └── discovery.py
│   └── tests/
│
├── sdk-typescript/          # TypeScript SDK
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts
│   │   ├── client.ts
│   │   ├── memory.ts
│   │   ├── identity.ts
│   │   └── discovery.ts
│   └── tests/
│
└── docs/                    # Documentation
    ├── getting-started.md
    ├── api-reference.md
    ├── self-hosting.md
    └── mcp-integration.md
```

## Security Considerations

### API Key Security
- Keys hashed with bcrypt before storage
- Only prefix stored for display (`nex_abc...`)
- Full key shown only once at creation
- Keys can have expiration dates
- Scoped permissions (read, write, share, admin)

### Memory Security
- All memories encrypted at rest (PostgreSQL TDE)
- Sharing requires explicit grants
- Audit log for access (enterprise)
- Memory isolation by agent_id enforced at query level

### Rate Limiting
- Per-agent rate limits via Redis
- Configurable by tier
- Burst allowance for spikes

## Scaling Strategy

### Phase 1 (MVP): Single Instance
- Single PostgreSQL instance
- Single API server
- Good for ~1000 agents, ~1M memories

### Phase 2: Horizontal Scale
- Read replicas for PostgreSQL
- Multiple API servers behind load balancer
- Redis cluster for caching

### Phase 3: Full Scale
- Sharded PostgreSQL (by agent_id)
- Dedicated vector search (Qdrant/Milvus)
- Global CDN for API edge caching

## Deployment

### Local Development
```bash
docker-compose up -d
cd core && python -m uvicorn nexus.main:app --reload
```

### Self-Hosted Production
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Cloud (Fly.io)
```bash
fly launch
fly deploy
```

## Dependencies

### Core Service
```
fastapi>=0.109.0
uvicorn>=0.27.0
sqlalchemy>=2.0.0
asyncpg>=0.29.0
pgvector>=0.2.0
redis>=5.0.0
pyjwt>=2.8.0
bcrypt>=4.1.0
sentence-transformers>=2.3.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
```

### Python SDK
```
httpx>=0.26.0
pydantic>=2.5.0
```

### TypeScript SDK
```
axios
zod
```

---

*Last updated: 2026-03-02*
