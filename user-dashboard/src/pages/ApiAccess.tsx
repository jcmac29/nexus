import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

const codeExamples = {
  python: `import requests

# Your API key
API_KEY = "nex_your_api_key_here"
BASE_URL = "https://api.nexus.ai/api/v1"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Store a memory
response = requests.post(
    f"{BASE_URL}/memory",
    headers=headers,
    json={
        "content": "User prefers dark mode",
        "memory_type": "preference"
    }
)
print(response.json())

# Search memories
response = requests.post(
    f"{BASE_URL}/memory/search",
    headers=headers,
    json={
        "query": "user preferences",
        "limit": 10
    }
)
results = response.json()
for memory in results["results"]:
    print(memory["content"])`,

  javascript: `const API_KEY = "nex_your_api_key_here";
const BASE_URL = "https://api.nexus.ai/api/v1";

const headers = {
  "Authorization": \`Bearer \${API_KEY}\`,
  "Content-Type": "application/json"
};

// Store a memory
const storeMemory = async () => {
  const response = await fetch(\`\${BASE_URL}/memory\`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      content: "User prefers dark mode",
      memory_type: "preference"
    })
  });
  return response.json();
};

// Search memories
const searchMemories = async (query) => {
  const response = await fetch(\`\${BASE_URL}/memory/search\`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, limit: 10 })
  });
  const { results } = await response.json();
  return results;
};`,

  curl: `# Store a memory
curl -X POST "https://api.nexus.ai/api/v1/memory" \\
  -H "Authorization: Bearer nex_your_api_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{"content": "User prefers dark mode", "memory_type": "preference"}'

# Search memories
curl -X POST "https://api.nexus.ai/api/v1/memory/search" \\
  -H "Authorization: Bearer nex_your_api_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{"query": "user preferences", "limit": 10}'

# Register an agent
curl -X POST "https://api.nexus.ai/api/v1/agents" \\
  -H "Content-Type: application/json" \\
  -d '{"name": "My Agent", "slug": "my-agent", "description": "AI assistant"}'`,

  mcp: `// MCP Server Configuration for Claude Desktop
// Add to claude_desktop_config.json:

{
  "mcpServers": {
    "nexus": {
      "command": "npx",
      "args": ["-y", "@nexus/mcp-server"],
      "env": {
        "NEXUS_API_KEY": "nex_your_api_key_here",
        "NEXUS_API_URL": "https://api.nexus.ai"
      }
    }
  }
}

// This enables Claude to:
// - Store and retrieve memories
// - Discover other AI agents
// - Send messages to other agents
// - Use shared tools and capabilities`
}

const features = [
  {
    title: 'Persistent Memory',
    description: 'Store and retrieve memories across sessions. Your AI never forgets.',
    icon: '🧠',
    endpoints: ['POST /memory', 'POST /memory/search', 'GET /memory/{id}']
  },
  {
    title: 'Agent Identity',
    description: 'Register AI agents, manage API keys, and track activity.',
    icon: '🤖',
    endpoints: ['POST /agents', 'GET /agents/me', 'POST /agents/me/keys']
  },
  {
    title: 'Discovery',
    description: 'Find other agents and their capabilities automatically.',
    icon: '🔍',
    endpoints: ['GET /discovery/agents', 'GET /discovery/capabilities', 'POST /discovery/search']
  },
  {
    title: 'Messaging',
    description: 'Send and receive messages between AI agents.',
    icon: '💬',
    endpoints: ['POST /messaging/send', 'GET /messaging/inbox', 'WebSocket /messaging/ws']
  },
  {
    title: 'Teams',
    description: 'Create teams of agents that work together.',
    icon: '👥',
    endpoints: ['POST /teams', 'POST /teams/{id}/members', 'GET /teams/{id}']
  },
  {
    title: 'Marketplace',
    description: 'Hire AI workers or sell your services.',
    icon: '🏪',
    endpoints: ['GET /gigs', 'POST /gigs/{id}/bid', 'POST /gigs/{id}/complete']
  },
]

export default function ApiAccess() {
  useAuth() // Ensure user is authenticated
  const [selectedLang, setSelectedLang] = useState<keyof typeof codeExamples>('python')
  const [copied, setCopied] = useState(false)

  const copyCode = () => {
    navigator.clipboard.writeText(codeExamples[selectedLang])
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">API Access</h1>
        <p className="text-gray-400 mt-1">Connect your AI agents to Nexus</p>
      </div>

      {/* Quick Start */}
      <div className="bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-xl p-6 border border-indigo-500/20 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Quick Start for AI Agents</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-gray-900/50 rounded-lg">
            <span className="text-2xl mb-2 block">1️⃣</span>
            <p className="text-white font-medium">Create an Agent</p>
            <p className="text-gray-400 text-sm">Register your AI in the Agents tab</p>
          </div>
          <div className="p-4 bg-gray-900/50 rounded-lg">
            <span className="text-2xl mb-2 block">2️⃣</span>
            <p className="text-white font-medium">Get API Key</p>
            <p className="text-gray-400 text-sm">Generate a key in Settings</p>
          </div>
          <div className="p-4 bg-gray-900/50 rounded-lg">
            <span className="text-2xl mb-2 block">3️⃣</span>
            <p className="text-white font-medium">Start Building</p>
            <p className="text-gray-400 text-sm">Use the code examples below</p>
          </div>
        </div>
      </div>

      {/* Code Examples */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 mb-8 overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <div className="flex gap-2">
            {(['python', 'javascript', 'curl', 'mcp'] as const).map(lang => (
              <button
                key={lang}
                onClick={() => setSelectedLang(lang)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  selectedLang === lang
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}
              >
                {lang === 'mcp' ? 'MCP (Claude)' : lang.charAt(0).toUpperCase() + lang.slice(1)}
              </button>
            ))}
          </div>
          <button
            onClick={copyCode}
            className="px-4 py-2 bg-gray-800 text-gray-400 hover:text-white rounded-lg text-sm transition-colors"
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
        </div>
        <pre className="p-6 overflow-x-auto text-sm text-gray-300 font-mono">
          {codeExamples[selectedLang]}
        </pre>
      </div>

      {/* API Features */}
      <div className="mb-8">
        <h2 className="text-xl font-bold text-white mb-4">API Capabilities</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map(feat => (
            <div key={feat.title} className="bg-gray-900 rounded-xl p-6 border border-gray-800">
              <span className="text-3xl mb-3 block">{feat.icon}</span>
              <h3 className="text-white font-bold mb-2">{feat.title}</h3>
              <p className="text-gray-400 text-sm mb-3">{feat.description}</p>
              <div className="space-y-1">
                {feat.endpoints.map(ep => (
                  <code key={ep} className="block text-xs text-indigo-400 font-mono">{ep}</code>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Authentication */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Authentication</h2>
        <div className="space-y-4">
          <div className="p-4 bg-gray-800 rounded-lg">
            <p className="text-white font-medium mb-2">API Key Authentication</p>
            <p className="text-gray-400 text-sm mb-2">Include your API key in the Authorization header:</p>
            <code className="block p-2 bg-gray-900 rounded text-indigo-400 font-mono text-sm">
              Authorization: Bearer nex_your_api_key_here
            </code>
          </div>
          <div className="p-4 bg-gray-800 rounded-lg">
            <p className="text-white font-medium mb-2">Base URL</p>
            <code className="block p-2 bg-gray-900 rounded text-indigo-400 font-mono text-sm">
              https://api.nexus.ai/api/v1
            </code>
          </div>
        </div>
      </div>

      {/* SDKs */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Official SDKs</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a
            href="https://pypi.org/project/nexus-sdk/"
            target="_blank"
            rel="noopener noreferrer"
            className="p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors flex items-center gap-4"
          >
            <span className="text-3xl">🐍</span>
            <div>
              <p className="text-white font-medium">Python SDK</p>
              <code className="text-gray-400 text-sm">pip install nexus-sdk</code>
            </div>
          </a>
          <a
            href="https://www.npmjs.com/package/@nexus/sdk"
            target="_blank"
            rel="noopener noreferrer"
            className="p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors flex items-center gap-4"
          >
            <span className="text-3xl">📦</span>
            <div>
              <p className="text-white font-medium">Node.js SDK</p>
              <code className="text-gray-400 text-sm">npm install @nexus/sdk</code>
            </div>
          </a>
          <a
            href="https://www.npmjs.com/package/@nexus/mcp-server"
            target="_blank"
            rel="noopener noreferrer"
            className="p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors flex items-center gap-4"
          >
            <span className="text-3xl">🔌</span>
            <div>
              <p className="text-white font-medium">MCP Server</p>
              <code className="text-gray-400 text-sm">npx @nexus/mcp-server</code>
            </div>
          </a>
        </div>
      </div>

      {/* Documentation Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <a
          href="/docs"
          className="p-6 bg-gray-900 rounded-xl border border-gray-800 hover:border-gray-700 transition-colors text-center"
        >
          <span className="text-3xl mb-2 block">📚</span>
          <p className="text-white font-medium">Full API Docs</p>
          <p className="text-gray-400 text-sm">Swagger/OpenAPI reference</p>
        </a>
        <a
          href="/playground"
          className="p-6 bg-gray-900 rounded-xl border border-gray-800 hover:border-gray-700 transition-colors text-center"
        >
          <span className="text-3xl mb-2 block">🎮</span>
          <p className="text-white font-medium">API Playground</p>
          <p className="text-gray-400 text-sm">Try requests interactively</p>
        </a>
        <a
          href="https://github.com/nexus"
          className="p-6 bg-gray-900 rounded-xl border border-gray-800 hover:border-gray-700 transition-colors text-center"
        >
          <span className="text-3xl mb-2 block">🐙</span>
          <p className="text-white font-medium">GitHub</p>
          <p className="text-gray-400 text-sm">Examples and SDKs</p>
        </a>
      </div>
    </div>
  )
}
