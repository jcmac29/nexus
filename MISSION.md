# Nexus - Project Mission

## One-Line Description
Open-source identity, memory, and discovery infrastructure for AI agents to authenticate, remember, and find each other.

---

## The Problem

AI agents today operate in isolation:
- No standard way to identify and authenticate agents
- Memory is siloed within individual applications
- No way to discover other agents' capabilities
- No cross-platform context sharing

Existing solutions (Mem0, Zep) focus on single-app memory. MCP Registry handles discovery but not memory or identity. **Nobody owns the unified layer.**

---

## Our Solution

Nexus provides three core primitives in one platform:

### 1. Identity
Every agent gets a verifiable identity with API keys and scoped permissions.

### 2. Memory
Persistent, semantic memory that agents can store, search, and share across sessions.

### 3. Discovery
Find agents by capability. Register what you do, discover what others offer.

---

## Why Us (Differentiation)

| Nexus | Mem0 | MCP Registry |
|-------|------|--------------|
| Open-source core | Partially open | Open |
| Identity-first | No identity | No identity |
| Memory + Discovery | Memory only | Discovery only |
| MCP-native | MCP support | MCP-native |
| Self-hostable | Limited | N/A |

---

## Target Users

1. **MCP Server Developers** - Need persistent memory across sessions
2. **AI Agent Builders** (LangChain, CrewAI, AutoGen) - Need cross-session memory and agent collaboration
3. **AI Application Developers** - Need simple user memory persistence

---

## Business Model

**Open-source core + Hosted cloud:**

| Tier | Price | Included |
|------|-------|----------|
| Free | $0 | 10K ops/month, 1K memories |
| Starter | $19/mo | 100K ops/month, 50K memories |
| Pro | $99/mo | 1M ops/month, 500K memories |
| Enterprise | Custom | Unlimited, SLA, support |

---

## What We've Built

### Core API (Python/FastAPI)
- Agent registration and authentication
- Memory storage with semantic search (pgvector)
- Capability registration and discovery
- MCP server integration

### SDKs
- Python SDK (sync + async)
- TypeScript SDK

### Infrastructure
- Docker Compose setup (PostgreSQL + Redis + API)
- Self-hosting ready

### Documentation
- Product spec
- Technical architecture
- Landing page

---

## Current Status

| Component | Status |
|-----------|--------|
| Core API | Working |
| Identity System | Working |
| Memory System | Working |
| Discovery System | Working |
| Python SDK | Working |
| TypeScript SDK | Working |
| MCP Integration | Working |
| Landing Page | Done |
| Hosted Cloud | Not started |

---

## Next Steps

1. **Deploy** - Fly.io or Railway for hosted version
2. **Domain** - Pick name (Axon, Engram, or Helix) and buy domain
3. **Documentation Site** - Full docs with examples
4. **Launch** - Share with MCP server developers, AI agent builders
5. **Iterate** - Add features based on user feedback

---

## Name Candidates

- **Axon** - Part of neuron that transmits signals (perfect metaphor)
- **Engram** - Neuroscience term for memory trace
- **Helix** - Intertwined structure, suggests connection

---

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy
- **Database**: PostgreSQL with pgvector
- **Cache**: Redis
- **Embeddings**: sentence-transformers (local)
- **SDKs**: Python (httpx), TypeScript (axios)
- **Infrastructure**: Docker, Docker Compose

---

## Project Structure

```
nexus/
├── MISSION.md           # This document
├── PRODUCT_SPEC.md      # Detailed product spec
├── ARCHITECTURE.md      # Technical architecture
├── README.md            # Documentation
├── core/                # Python API server
├── sdk-python/          # Python SDK
├── sdk-typescript/      # TypeScript SDK
├── landing/             # Landing page
├── docker-compose.yml   # One-command setup
└── Makefile             # Dev commands
```

---

## Running Locally

```bash
# Start everything
docker-compose up -d

# API at http://localhost:8000
# Docs at http://localhost:8000/docs
```

---

*Created: March 2026*
