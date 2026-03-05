import { useState } from 'react'

// API base URL - uses proxy in dev, origin in production
const API_BASE = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '')

interface ApiResponse {
  status: number
  data: unknown
  time: number
}

const EXAMPLES = [
  {
    category: 'Getting Started',
    items: [
      { name: 'Health Check', method: 'GET', path: '/health', body: null, description: 'Check if the API is running' },
      { name: 'API Info', method: 'GET', path: '/', body: null, description: 'Get API version and info' },
    ]
  },
  {
    category: 'Agents',
    items: [
      { name: 'Create Agent', method: 'POST', path: '/api/v1/agents', body: { name: 'My Agent', slug: 'my-agent', description: 'A helpful AI agent' }, description: 'Register a new AI agent' },
    ]
  },
  {
    category: 'Memory',
    items: [
      { name: 'Store Memory', method: 'POST', path: '/api/v1/memory', body: { content: 'User prefers dark mode', memory_type: 'preference' }, description: 'Store a memory' },
      { name: 'Search', method: 'POST', path: '/api/v1/memory/search', body: { query: 'preferences', limit: 5 }, description: 'Search memories' },
    ]
  },
  {
    category: 'Teams',
    items: [
      { name: 'Create Team', method: 'POST', path: '/api/v1/teams', body: { name: 'My Team', slug: 'my-team' }, description: 'Create a team' },
      { name: 'List Teams', method: 'GET', path: '/api/v1/teams', body: null, description: 'List your teams' },
    ]
  },
]

export default function App() {
  const [apiKey, setApiKey] = useState('')
  const [method, setMethod] = useState('GET')
  const [path, setPath] = useState('/health')
  const [body, setBody] = useState('')
  const [response, setResponse] = useState<ApiResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const runRequest = async () => {
    setLoading(true)
    const start = Date.now()
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`
      const options: RequestInit = { method, headers }
      if (body && method !== 'GET') options.body = body
      const res = await fetch(API_BASE + path, options)
      const data = await res.json().catch(() => null)
      setResponse({ status: res.status, data, time: Date.now() - start })
    } catch (err) {
      setResponse({ status: 0, data: { error: String(err) }, time: Date.now() - start })
    }
    setLoading(false)
  }

  const loadExample = (ex: typeof EXAMPLES[0]['items'][0]) => {
    setMethod(ex.method)
    setPath(ex.path)
    setBody(ex.body ? JSON.stringify(ex.body, null, 2) : '')
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <span className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg"></span>
            Nexus Playground
          </h1>
          <input
            type="password"
            placeholder="API Key (optional)"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="px-3 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm w-64"
          />
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-6 grid grid-cols-4 gap-6">
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase">Examples</h2>
          {EXAMPLES.map((cat) => (
            <div key={cat.category}>
              <h3 className="text-xs text-gray-500 mb-1">{cat.category}</h3>
              {cat.items.map((item) => (
                <button
                  key={item.path + item.method}
                  onClick={() => loadExample(item)}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-800 text-sm"
                >
                  <span className={`text-xs font-mono mr-2 ${item.method === 'GET' ? 'text-green-400' : 'text-blue-400'}`}>
                    {item.method}
                  </span>
                  {item.name}
                </button>
              ))}
            </div>
          ))}
        </div>

        <div className="col-span-3 space-y-4">
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className="flex gap-2 mb-4">
              <select value={method} onChange={(e) => setMethod(e.target.value)}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded font-mono text-sm">
                <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
              </select>
              <input value={path} onChange={(e) => setPath(e.target.value)}
                className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded font-mono text-sm" />
              <button onClick={runRequest} disabled={loading}
                className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 rounded font-medium">
                {loading ? '...' : 'Send'}
              </button>
            </div>
            {method !== 'GET' && (
              <textarea value={body} onChange={(e) => setBody(e.target.value)}
                rows={5} placeholder='{"key": "value"}'
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded font-mono text-sm" />
            )}
          </div>

          {response && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <div className="flex items-center gap-3 mb-3">
                <span className={`px-2 py-1 rounded text-sm font-mono ${
                  response.status < 300 ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                }`}>{response.status}</span>
                <span className="text-gray-400 text-sm">{response.time}ms</span>
              </div>
              <pre className="bg-gray-950 p-4 rounded overflow-auto max-h-80 text-sm font-mono">
                {JSON.stringify(response.data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
