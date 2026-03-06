import { useState, useEffect } from 'react'

// API base URL - uses proxy in dev, origin in production
const API_BASE = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '')

interface ApiResponse {
  status: number
  data: unknown
  time: number
}

interface HistoryItem {
  id: string
  method: string
  path: string
  body: string | null
  status: number
  time: number
  timestamp: number
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

const HISTORY_KEY = 'nexus_playground_history'
const MAX_HISTORY = 20

function generateCurl(method: string, path: string, body: string | null, apiKey: string): string {
  const url = `${window.location.origin}${path}`
  let cmd = `curl -X ${method} "${url}"`
  if (apiKey) {
    cmd += ` \\\n  -H "Authorization: Bearer ${apiKey}"`
  }
  if (body && method !== 'GET') {
    cmd += ` \\\n  -H "Content-Type: application/json"`
    cmd += ` \\\n  -d '${body.replace(/\n/g, '')}'`
  }
  return cmd
}

function generatePython(method: string, path: string, body: string | null, apiKey: string): string {
  const url = `${window.location.origin}${path}`
  let code = `import requests\n\n`
  code += `url = "${url}"\n`

  if (apiKey) {
    code += `headers = {"Authorization": "Bearer ${apiKey}"}\n`
  } else {
    code += `headers = {}\n`
  }

  if (body && method !== 'GET') {
    code += `data = ${body}\n\n`
    code += `response = requests.${method.toLowerCase()}(url, headers=headers, json=data)\n`
  } else {
    code += `\nresponse = requests.${method.toLowerCase()}(url, headers=headers)\n`
  }

  code += `print(response.json())`
  return code
}

function generateJavaScript(method: string, path: string, body: string | null, apiKey: string): string {
  const url = `${window.location.origin}${path}`
  let code = `const response = await fetch("${url}", {\n`
  code += `  method: "${method}",\n`
  code += `  headers: {\n`
  if (apiKey) {
    code += `    "Authorization": "Bearer ${apiKey}",\n`
  }
  if (body && method !== 'GET') {
    code += `    "Content-Type": "application/json",\n`
  }
  code += `  },\n`
  if (body && method !== 'GET') {
    code += `  body: JSON.stringify(${body.replace(/\n/g, '')}),\n`
  }
  code += `});\n\n`
  code += `const data = await response.json();\n`
  code += `console.log(data);`
  return code
}

export default function App() {
  const [apiKey, setApiKey] = useState('')
  const [method, setMethod] = useState('GET')
  const [path, setPath] = useState('/health')
  const [body, setBody] = useState('')
  const [response, setResponse] = useState<ApiResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [showSnippets, setShowSnippets] = useState(false)
  const [snippetLang, setSnippetLang] = useState<'curl' | 'python' | 'javascript'>('curl')
  const [copied, setCopied] = useState(false)

  // Load history from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(HISTORY_KEY)
    if (saved) {
      try {
        setHistory(JSON.parse(saved))
      } catch {
        // Invalid data, ignore
      }
    }
  }, [])

  // Save history to localStorage
  const saveHistory = (items: HistoryItem[]) => {
    setHistory(items)
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items))
  }

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
      const elapsed = Date.now() - start
      setResponse({ status: res.status, data, time: elapsed })

      // Add to history
      const historyItem: HistoryItem = {
        id: crypto.randomUUID(),
        method,
        path,
        body: body || null,
        status: res.status,
        time: elapsed,
        timestamp: Date.now(),
      }
      const newHistory = [historyItem, ...history].slice(0, MAX_HISTORY)
      saveHistory(newHistory)
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

  const loadFromHistory = (item: HistoryItem) => {
    setMethod(item.method)
    setPath(item.path)
    setBody(item.body || '')
    setShowHistory(false)
  }

  const clearHistory = () => {
    saveHistory([])
  }

  const getSnippet = () => {
    switch (snippetLang) {
      case 'curl': return generateCurl(method, path, body, apiKey)
      case 'python': return generatePython(method, path, body, apiKey)
      case 'javascript': return generateJavaScript(method, path, body, apiKey)
    }
  }

  const copySnippet = async () => {
    await navigator.clipboard.writeText(getSnippet())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp)
    const now = new Date()
    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
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
        {/* Sidebar */}
        <div className="space-y-6">
          {/* Tab buttons */}
          <div className="flex gap-2">
            <button
              onClick={() => setShowHistory(false)}
              className={`flex-1 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                !showHistory ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              Examples
            </button>
            <button
              onClick={() => setShowHistory(true)}
              className={`flex-1 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                showHistory ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              History
              {history.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-gray-700 rounded-full text-xs">
                  {history.length}
                </span>
              )}
            </button>
          </div>

          {/* Examples */}
          {!showHistory && (
            <div className="space-y-4">
              {EXAMPLES.map((cat) => (
                <div key={cat.category}>
                  <h3 className="text-xs text-gray-500 mb-1 uppercase tracking-wide">{cat.category}</h3>
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
          )}

          {/* History */}
          {showHistory && (
            <div className="space-y-2">
              {history.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-4">No history yet</p>
              ) : (
                <>
                  <div className="flex justify-end">
                    <button
                      onClick={clearHistory}
                      className="text-xs text-gray-500 hover:text-red-400 transition-colors"
                    >
                      Clear all
                    </button>
                  </div>
                  {history.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => loadFromHistory(item)}
                      className="w-full text-left px-2 py-2 rounded hover:bg-gray-800 border border-gray-800 transition-colors"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs font-mono ${
                          item.method === 'GET' ? 'text-green-400' :
                          item.method === 'POST' ? 'text-blue-400' :
                          item.method === 'PUT' ? 'text-yellow-400' : 'text-red-400'
                        }`}>
                          {item.method}
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          item.status < 300 ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                        }`}>
                          {item.status}
                        </span>
                        <span className="text-xs text-gray-500 ml-auto">{formatTime(item.timestamp)}</span>
                      </div>
                      <p className="text-xs text-gray-400 truncate font-mono">{item.path}</p>
                    </button>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* Main content */}
        <div className="col-span-3 space-y-4">
          {/* Request builder */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className="flex gap-2 mb-4">
              <select value={method} onChange={(e) => setMethod(e.target.value)}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded font-mono text-sm">
                <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
              </select>
              <input value={path} onChange={(e) => setPath(e.target.value)}
                className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded font-mono text-sm" />
              <button onClick={runRequest} disabled={loading}
                className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 rounded font-medium disabled:opacity-50">
                {loading ? '...' : 'Send'}
              </button>
            </div>
            {method !== 'GET' && (
              <textarea value={body} onChange={(e) => setBody(e.target.value)}
                rows={5} placeholder='{"key": "value"}'
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded font-mono text-sm" />
            )}
          </div>

          {/* Code snippets */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <button
              onClick={() => setShowSnippets(!showSnippets)}
              className="w-full px-4 py-3 flex items-center justify-between text-sm font-medium hover:bg-gray-800 transition-colors"
            >
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                </svg>
                Code Snippets
              </span>
              <svg className={`w-4 h-4 transition-transform ${showSnippets ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {showSnippets && (
              <div className="border-t border-gray-800 p-4">
                <div className="flex items-center gap-2 mb-3">
                  {(['curl', 'python', 'javascript'] as const).map((lang) => (
                    <button
                      key={lang}
                      onClick={() => setSnippetLang(lang)}
                      className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                        snippetLang === lang
                          ? 'bg-indigo-600 text-white'
                          : 'bg-gray-800 text-gray-400 hover:text-white'
                      }`}
                    >
                      {lang === 'curl' ? 'cURL' : lang === 'python' ? 'Python' : 'JavaScript'}
                    </button>
                  ))}
                  <button
                    onClick={copySnippet}
                    className="ml-auto px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-gray-400 hover:text-white transition-colors flex items-center gap-1.5"
                  >
                    {copied ? (
                      <>
                        <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        Copied!
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        Copy
                      </>
                    )}
                  </button>
                </div>
                <pre className="bg-gray-950 p-4 rounded overflow-auto max-h-60 text-sm font-mono text-gray-300">
                  {getSnippet()}
                </pre>
              </div>
            )}
          </div>

          {/* Response */}
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
