# Nexus Integrations

Connect your development tools to Nexus for AI-powered development with shared team context.

## Available Integrations

| Integration | Status | Description |
|------------|--------|-------------|
| **Xcode** | ✅ Ready | Swift package + CLI for iOS/macOS development |
| **VS Code** | ✅ Ready | Full extension with auto-sync, search, AI assist |
| **JetBrains** | ✅ Ready | Plugin for IntelliJ, PyCharm, WebStorm, etc. |
| **Git Hooks** | ✅ Ready | Auto-capture commits and pushes |
| **GitHub Actions** | ✅ Ready | Sync PRs, issues, and pushes |
| **Terminal/Shell** | ✅ Ready | Bash/Zsh functions for CLI workflow |
| **Slack Bot** | ✅ Ready | Team AI assistant in Slack |
| **Obsidian** | ✅ Ready | Note-taking with shared AI context |

## Quick Start

### 1. Get Your API Key

```bash
curl -X POST http://localhost:8000/api/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "My Workspace", "slug": "my-workspace", "description": "My dev environment"}'
```

Save the `api_key` from the response.

### 2. Set Environment Variables

```bash
export NEXUS_URL=http://localhost:8000
export NEXUS_API_KEY=nex_your_key_here
```

### 3. Install Your Integration

See individual integration docs below.

---

## Xcode Integration

Swift package for iOS/macOS development.

```bash
cd integrations/xcode/NexusXcode
swift build
export PATH=$PATH:$(pwd)/.build/debug

# Store current file
nexus-xcode store --file MyFile.swift --project MyApp

# Search context
nexus-xcode search "authentication logic"

# Sync entire project
nexus-xcode sync --directory /path/to/project --project MyApp
```

---

## VS Code Extension

Full-featured extension with auto-sync.

```bash
cd integrations/vscode
npm install
npm run compile
# Then "Install from VSIX" in VS Code, or link for development
```

**Features:**
- Auto-sync files on save
- `Cmd+Shift+N` - Ask AI
- `Cmd+Shift+F` - Search knowledge base
- Right-click → "Explain Selected Code"
- Team activity panel

**Settings:**
- `nexus.serverUrl` - Server URL
- `nexus.apiKey` - Your API key
- `nexus.autoSync` - Enable auto-sync on save

---

## JetBrains Plugin

Works with IntelliJ IDEA, PyCharm, WebStorm, GoLand, etc.

```bash
cd integrations/jetbrains
./gradlew buildPlugin
# Install from build/distributions/
```

**Features:**
- Tools → Nexus menu
- `Ctrl+Shift+N` - Ask AI
- Auto-sync on save
- Search knowledge base

---

## Git Hooks

Auto-capture commits and pushes.

```bash
cd your-repo
/path/to/integrations/git-hooks/install.sh
```

Every commit and push is automatically stored in Nexus with:
- Commit message
- Author
- Files changed
- Branch info

---

## GitHub Actions

Add to `.github/workflows/nexus-sync.yml`:

```yaml
name: Nexus Sync
on:
  pull_request:
  issues:
  push:
    branches: [main]

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Sync to Nexus
        run: |
          # See integrations/github-actions/nexus-sync.yml for full workflow
```

Add secrets:
- `NEXUS_URL`
- `NEXUS_API_KEY`

---

## Terminal/Shell

Add to your `.bashrc` or `.zshrc`:

```bash
source /path/to/integrations/terminal/nexus.sh
```

**Commands:**
```bash
nx-remember "key" "something to remember"
nx-search "authentication logic"
nx-ask "How do I implement OAuth?"
nx-pending                    # Check pending work
nx-team                       # List team members
nx-status                     # Check connection
nx-capture "npm test"         # Run and store output
```

---

## Slack Bot

AI-powered team assistant.

```bash
cd integrations/slack-bot
pip install -r requirements.txt

export SLACK_BOT_TOKEN=xoxb-your-token
export SLACK_APP_TOKEN=xapp-your-token
export NEXUS_URL=http://localhost:8000
export NEXUS_API_KEY=your-key

python bot.py
```

**Slack Commands:**
- `/nexus-search <query>` - Search knowledge base
- `/nexus-ask <question>` - Ask AI
- `/nexus-remember <note>` - Store a note
- `/nexus-activity` - Recent team activity
- `@nexus <question>` - Mention the bot

---

## Obsidian Plugin

Sync your notes to shared AI context.

```bash
cd integrations/obsidian
npm install
npm run build
# Copy to .obsidian/plugins/nexus/
```

**Features:**
- Store notes in Nexus
- Search across all knowledge
- Ask AI about your notes
- Sync entire vault
- Auto-sync on note change

---

## How It All Works Together

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Xcode     │     │   VS Code   │     │  Terminal   │
│  (Alice)    │     │   (Bob)     │     │  (Charlie)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   NEXUS     │
                    │  ─────────  │
                    │  • Memory   │
                    │  • Agents   │
                    │  • AI       │
                    └──────┬──────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Git Hooks   │     │   Slack     │     │  Obsidian   │
│ (context)   │     │  (team)     │     │  (notes)    │
└─────────────┘     └─────────────┘     └─────────────┘
```

**Alice** codes in Xcode, context syncs to Nexus.
**Bob** searches in VS Code, finds Alice's work.
**Charlie** asks AI in terminal, gets context from both.
**Slack** notifies team of activity.
**Git** captures all commits automatically.
**Obsidian** links documentation to code.

All connected. All shared. All AI-aware.
