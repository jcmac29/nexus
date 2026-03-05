import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface Memory {
  id: string
  content: string
  memory_type: string
  scope: string
  agent_id?: string
  agent_name?: string
  tags?: string[]
  created_at: string
}

interface Agent {
  id: string
  name: string
  slug: string
}

type ViewMode = 'list' | 'guide'

const MEMORY_TYPES = [
  {
    value: 'preference',
    label: 'Preference',
    icon: '⚙️',
    description: 'User preferences and settings',
    example: 'User prefers dark mode and concise responses',
    color: 'purple'
  },
  {
    value: 'fact',
    label: 'Fact',
    icon: '📚',
    description: 'Factual information to remember',
    example: 'Company founded in 2020, HQ in San Francisco',
    color: 'blue'
  },
  {
    value: 'instruction',
    label: 'Instruction',
    icon: '📋',
    description: 'Rules and guidelines to follow',
    example: 'Always greet users by name, never discuss competitors',
    color: 'orange'
  },
  {
    value: 'context',
    label: 'Context',
    icon: '🎯',
    description: 'Background context for conversations',
    example: 'Currently working on Q1 marketing campaign',
    color: 'green'
  },
  {
    value: 'conversation',
    label: 'Conversation',
    icon: '💬',
    description: 'Key points from past conversations',
    example: 'Discussed pricing on March 1st, interested in Pro plan',
    color: 'cyan'
  },
  {
    value: 'general',
    label: 'General',
    icon: '📝',
    description: 'Any other information',
    example: 'Meeting notes, random thoughts, temporary data',
    color: 'gray'
  },
]

const MEMORY_SCOPES = [
  {
    value: 'agent',
    label: 'Agent Only',
    icon: '🤖',
    description: 'Only this specific agent can access',
    useCase: 'Personal assistant memories, user-specific preferences'
  },
  {
    value: 'team',
    label: 'Team Shared',
    icon: '👥',
    description: 'All agents in your team can access',
    useCase: 'Company knowledge, shared context, team guidelines'
  },
  {
    value: 'project',
    label: 'Project',
    icon: '📁',
    description: 'Agents in the same project can access',
    useCase: 'Project-specific information, scoped collaboration'
  },
]

export default function Memory() {
  const api = useApi<any>()
  const [memories, setMemories] = useState<Memory[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [showModal, setShowModal] = useState(false)
  const [showDetailModal, setShowDetailModal] = useState(false)
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null)
  const [form, setForm] = useState({
    content: '',
    memory_type: 'general',
    scope: 'agent',
    agent_id: '',
    tags: ''
  })
  const [saving, setSaving] = useState(false)
  const [filterType, setFilterType] = useState<string>('all')
  const [filterScope, setFilterScope] = useState<string>('all')

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [memoriesData, agentData] = await Promise.all([
        api.get('/api/v1/memory?limit=100').catch(() => ({ items: [] })),
        api.get('/api/v1/agents/me').catch(() => null)
      ])
      setMemories(memoriesData.items || [])
      // agents/me returns a single agent, wrap in array
      const agentList = agentData ? [agentData] : []
      setAgents(agentList)
      if (agentList.length > 0 && !form.agent_id) {
        setForm(f => ({ ...f, agent_id: agentList[0].id }))
      }
    } catch {}
  }

  async function handleSearch() {
    if (!search.trim()) {
      loadData()
      return
    }
    try {
      const data = await api.post('/api/v1/memory/search', { query: search, limit: 50 })
      setMemories(data.results || [])
    } catch {}
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload: any = {
        content: form.content,
        memory_type: form.memory_type,
        scope: form.scope,
      }
      if (form.agent_id) payload.agent_id = form.agent_id
      if (form.tags) payload.tags = form.tags.split(',').map(t => t.trim()).filter(Boolean)

      await api.post('/api/v1/memory', payload)
      setShowModal(false)
      setForm({ content: '', memory_type: 'general', scope: 'agent', agent_id: agents[0]?.id || '', tags: '' })
      loadData()
    } catch {}
    setSaving(false)
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this memory? This cannot be undone.')) return
    try {
      await api.del(`/api/v1/memory/${id}`)
      setMemories(memories.filter(m => m.id !== id))
      if (selectedMemory?.id === id) {
        setShowDetailModal(false)
        setSelectedMemory(null)
      }
    } catch {}
  }

  const getTypeConfig = (type: string) => {
    return MEMORY_TYPES.find(t => t.value === type) || MEMORY_TYPES[5]
  }

  const getScopeConfig = (scope: string) => {
    return MEMORY_SCOPES.find(s => s.value === scope) || MEMORY_SCOPES[0]
  }

  const getTypeColor = (type: string) => {
    const config = getTypeConfig(type)
    switch (config.color) {
      case 'purple': return 'bg-purple-500/10 text-purple-400 border-purple-500/20'
      case 'blue': return 'bg-blue-500/10 text-blue-400 border-blue-500/20'
      case 'orange': return 'bg-orange-500/10 text-orange-400 border-orange-500/20'
      case 'green': return 'bg-green-500/10 text-green-400 border-green-500/20'
      case 'cyan': return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
      default: return 'bg-gray-500/10 text-gray-400 border-gray-500/20'
    }
  }

  const filteredMemories = memories.filter(m => {
    if (filterType !== 'all' && m.memory_type !== filterType) return false
    if (filterScope !== 'all' && m.scope !== filterScope) return false
    return true
  })

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white">Memory</h1>
          <p className="text-gray-400 mt-1">Give your AI agents persistent memory</p>
        </div>
        <div className="flex gap-3">
          <div className="flex bg-gray-900 rounded-lg p-1">
            <button
              onClick={() => setViewMode('list')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                viewMode === 'list' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              Memories
            </button>
            <button
              onClick={() => setViewMode('guide')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                viewMode === 'guide' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              How It Works
            </button>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="px-6 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity"
          >
            + Store Memory
          </button>
        </div>
      </div>

      {/* Guide View */}
      {viewMode === 'guide' && (
        <div className="space-y-8">
          {/* What is Memory */}
          <div className="bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-2xl p-8 border border-indigo-500/20">
            <h2 className="text-2xl font-bold text-white mb-4">What is AI Memory?</h2>
            <p className="text-gray-300 text-lg mb-6">
              Memory allows your AI agents to <span className="text-indigo-400 font-semibold">remember information across conversations</span>.
              Unlike regular chat history that disappears, memories persist forever and can be shared between agents.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-gray-900/50 rounded-xl p-6">
                <span className="text-4xl mb-4 block">🧠</span>
                <h3 className="text-white font-bold mb-2">Persistent</h3>
                <p className="text-gray-400">Memories survive across sessions, restarts, and even different devices.</p>
              </div>
              <div className="bg-gray-900/50 rounded-xl p-6">
                <span className="text-4xl mb-4 block">🔍</span>
                <h3 className="text-white font-bold mb-2">Searchable</h3>
                <p className="text-gray-400">AI can search memories by meaning, not just keywords. Ask "what does the user prefer?" and find relevant memories.</p>
              </div>
              <div className="bg-gray-900/50 rounded-xl p-6">
                <span className="text-4xl mb-4 block">🔗</span>
                <h3 className="text-white font-bold mb-2">Shareable</h3>
                <p className="text-gray-400">Share memories between agents so your whole team stays in sync.</p>
              </div>
            </div>
          </div>

          {/* Memory Types */}
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">Memory Types</h2>
            <p className="text-gray-400 mb-6">Organize memories by type to help your AI understand context better.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {MEMORY_TYPES.map(type => (
                <div key={type.value} className="bg-gray-800 rounded-xl p-5 hover:bg-gray-800/80 transition-colors">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-2xl">{type.icon}</span>
                    <span className={`px-3 py-1 text-sm font-medium rounded-full border ${getTypeColor(type.value)}`}>
                      {type.label}
                    </span>
                  </div>
                  <p className="text-gray-300 text-sm mb-3">{type.description}</p>
                  <div className="p-3 bg-gray-900 rounded-lg">
                    <p className="text-gray-500 text-xs mb-1">Example:</p>
                    <p className="text-gray-400 text-sm italic">"{type.example}"</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Memory Scopes */}
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">Memory Scopes</h2>
            <p className="text-gray-400 mb-6">Control who can access each memory.</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {MEMORY_SCOPES.map(scope => (
                <div key={scope.value} className="bg-gray-800 rounded-xl p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <span className="text-3xl">{scope.icon}</span>
                    <div>
                      <h3 className="text-white font-bold">{scope.label}</h3>
                    </div>
                  </div>
                  <p className="text-gray-300 mb-4">{scope.description}</p>
                  <div className="p-3 bg-gray-900 rounded-lg">
                    <p className="text-gray-500 text-xs mb-1">Best for:</p>
                    <p className="text-gray-400 text-sm">{scope.useCase}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Visual Diagram */}
            <div className="mt-8 p-6 bg-gray-800 rounded-xl">
              <h3 className="text-white font-bold mb-4">How Scope Works</h3>
              <div className="flex flex-col md:flex-row items-center justify-center gap-8">
                <div className="text-center">
                  <div className="w-24 h-24 bg-purple-500/20 rounded-full flex items-center justify-center mx-auto mb-2">
                    <span className="text-4xl">🤖</span>
                  </div>
                  <p className="text-purple-400 font-medium">Agent Scope</p>
                  <p className="text-gray-500 text-sm">Private</p>
                </div>
                <div className="text-gray-500 text-2xl">⊂</div>
                <div className="text-center">
                  <div className="w-32 h-32 bg-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-2">
                    <span className="text-4xl">📁</span>
                  </div>
                  <p className="text-blue-400 font-medium">Project Scope</p>
                  <p className="text-gray-500 text-sm">Project Team</p>
                </div>
                <div className="text-gray-500 text-2xl">⊂</div>
                <div className="text-center">
                  <div className="w-40 h-40 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-2">
                    <span className="text-4xl">👥</span>
                  </div>
                  <p className="text-green-400 font-medium">Team Scope</p>
                  <p className="text-gray-500 text-sm">Everyone</p>
                </div>
              </div>
            </div>
          </div>

          {/* API Usage */}
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">Using Memory via API</h2>
            <p className="text-gray-400 mb-6">Your AI agents can store and retrieve memories programmatically.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-white font-medium mb-3 flex items-center gap-2">
                  <span className="text-green-400">POST</span> Store a Memory
                </h3>
                <pre className="p-4 bg-gray-800 rounded-lg overflow-x-auto text-sm">
                  <code className="text-gray-300">{`POST /api/v1/memory
{
  "content": "User prefers dark mode",
  "memory_type": "preference",
  "scope": "agent"
}`}</code>
                </pre>
              </div>
              <div>
                <h3 className="text-white font-medium mb-3 flex items-center gap-2">
                  <span className="text-blue-400">POST</span> Search Memories
                </h3>
                <pre className="p-4 bg-gray-800 rounded-lg overflow-x-auto text-sm">
                  <code className="text-gray-300">{`POST /api/v1/memory/search
{
  "query": "what are user preferences?",
  "limit": 10
}`}</code>
                </pre>
              </div>
            </div>
            <div className="mt-6 p-4 bg-indigo-500/10 border border-indigo-500/20 rounded-lg">
              <p className="text-indigo-300">
                <span className="font-bold">Pro Tip:</span> Use semantic search! Ask questions like "what does the user like?"
                instead of searching for exact keywords. Our AI understands meaning.
              </p>
            </div>
          </div>

          {/* Best Practices */}
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-6">Best Practices</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="flex gap-4">
                <span className="text-2xl">✅</span>
                <div>
                  <h3 className="text-white font-medium mb-1">Be Specific</h3>
                  <p className="text-gray-400 text-sm">"John prefers email over phone calls for non-urgent matters" instead of "John's preferences"</p>
                </div>
              </div>
              <div className="flex gap-4">
                <span className="text-2xl">✅</span>
                <div>
                  <h3 className="text-white font-medium mb-1">Use the Right Type</h3>
                  <p className="text-gray-400 text-sm">Categorize memories correctly so AI can prioritize them appropriately</p>
                </div>
              </div>
              <div className="flex gap-4">
                <span className="text-2xl">✅</span>
                <div>
                  <h3 className="text-white font-medium mb-1">Add Tags</h3>
                  <p className="text-gray-400 text-sm">Use tags like "customer:acme" or "project:q1" for easy filtering</p>
                </div>
              </div>
              <div className="flex gap-4">
                <span className="text-2xl">✅</span>
                <div>
                  <h3 className="text-white font-medium mb-1">Clean Up</h3>
                  <p className="text-gray-400 text-sm">Delete outdated memories to keep your AI's knowledge current</p>
                </div>
              </div>
              <div className="flex gap-4">
                <span className="text-2xl">❌</span>
                <div>
                  <h3 className="text-white font-medium mb-1">Don't Store Secrets</h3>
                  <p className="text-gray-400 text-sm">Never store passwords, API keys, or sensitive credentials in memories</p>
                </div>
              </div>
              <div className="flex gap-4">
                <span className="text-2xl">❌</span>
                <div>
                  <h3 className="text-white font-medium mb-1">Avoid Duplicates</h3>
                  <p className="text-gray-400 text-sm">Search before storing to avoid redundant memories</p>
                </div>
              </div>
            </div>
          </div>

          {/* CTA */}
          <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl p-8 text-center">
            <h2 className="text-2xl font-bold text-white mb-4">Ready to Get Started?</h2>
            <p className="text-indigo-100 mb-6">Store your first memory and see the magic happen.</p>
            <button
              onClick={() => {
                setViewMode('list')
                setShowModal(true)
              }}
              className="px-8 py-3 bg-white text-indigo-600 font-medium rounded-lg hover:bg-gray-100 transition-colors"
            >
              Store Your First Memory
            </button>
          </div>
        </div>
      )}

      {/* List View */}
      {viewMode === 'list' && (
        <>
          {/* Search & Filters */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 mb-6">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1 flex gap-3">
                <input
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Search memories... (try asking a question!)"
                />
                <button
                  onClick={handleSearch}
                  className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  Search
                </button>
              </div>
              <div className="flex gap-3">
                <select
                  value={filterType}
                  onChange={e => setFilterType(e.target.value)}
                  className="px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="all">All Types</option>
                  {MEMORY_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.icon} {t.label}</option>
                  ))}
                </select>
                <select
                  value={filterScope}
                  onChange={e => setFilterScope(e.target.value)}
                  className="px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="all">All Scopes</option>
                  {MEMORY_SCOPES.map(s => (
                    <option key={s.value} value={s.value}>{s.icon} {s.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Memory Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">Total Memories</p>
              <p className="text-2xl font-bold text-white">{memories.length}</p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">Agent Memories</p>
              <p className="text-2xl font-bold text-purple-400">{memories.filter(m => m.scope === 'agent').length}</p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">Team Memories</p>
              <p className="text-2xl font-bold text-green-400">{memories.filter(m => m.scope === 'team').length}</p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">This Week</p>
              <p className="text-2xl font-bold text-blue-400">
                {memories.filter(m => new Date(m.created_at) > new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)).length}
              </p>
            </div>
          </div>

          {/* Memory List */}
          {filteredMemories.length === 0 ? (
            <div className="bg-gray-900 rounded-xl p-12 border border-gray-800 text-center">
              <span className="text-6xl mb-4 block">🧠</span>
              <h2 className="text-xl font-bold text-white mb-2">
                {memories.length === 0 ? 'No memories yet' : 'No matching memories'}
              </h2>
              <p className="text-gray-400 mb-6">
                {memories.length === 0
                  ? 'Store information your AI agents can remember across conversations'
                  : 'Try adjusting your search or filters'
                }
              </p>
              {memories.length === 0 && (
                <div className="flex justify-center gap-4">
                  <button
                    onClick={() => setShowModal(true)}
                    className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                  >
                    Store Your First Memory
                  </button>
                  <button
                    onClick={() => setViewMode('guide')}
                    className="px-6 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
                  >
                    Learn How It Works
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredMemories.map(memory => {
                const typeConfig = getTypeConfig(memory.memory_type)
                const scopeConfig = getScopeConfig(memory.scope)
                return (
                  <div
                    key={memory.id}
                    className="bg-gray-900 rounded-xl p-5 border border-gray-800 hover:border-gray-700 transition-colors cursor-pointer"
                    onClick={() => {
                      setSelectedMemory(memory)
                      setShowDetailModal(true)
                    }}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <span className={`px-2.5 py-1 text-xs font-medium rounded-full border flex items-center gap-1 ${getTypeColor(memory.memory_type)}`}>
                            <span>{typeConfig.icon}</span>
                            {typeConfig.label}
                          </span>
                          <span className="px-2.5 py-1 text-xs font-medium rounded-full bg-gray-800 text-gray-400 flex items-center gap-1">
                            <span>{scopeConfig.icon}</span>
                            {scopeConfig.label}
                          </span>
                          {memory.agent_name && (
                            <span className="px-2.5 py-1 text-xs font-medium rounded-full bg-gray-800 text-gray-500">
                              🤖 {memory.agent_name}
                            </span>
                          )}
                          <span className="text-gray-500 text-xs ml-auto">
                            {new Date(memory.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="text-white line-clamp-2">{memory.content}</p>
                        {memory.tags && memory.tags.length > 0 && (
                          <div className="flex gap-1 mt-2">
                            {memory.tags.map(tag => (
                              <span key={tag} className="px-2 py-0.5 text-xs bg-gray-800 text-gray-400 rounded">
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDelete(memory.id)
                        }}
                        className="p-2 text-gray-500 hover:text-red-400 transition-colors"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* Create Memory Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-2xl border border-gray-800 max-h-[90vh] overflow-y-auto">
            <h2 className="text-2xl font-bold text-white mb-2">Store Memory</h2>
            <p className="text-gray-400 mb-6">Add information for your AI to remember.</p>

            <form onSubmit={handleCreate} className="space-y-6">
              {/* Memory Type Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">Memory Type</label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {MEMORY_TYPES.map(type => (
                    <button
                      key={type.value}
                      type="button"
                      onClick={() => setForm({ ...form, memory_type: type.value })}
                      className={`p-3 rounded-lg border text-left transition-colors ${
                        form.memory_type === type.value
                          ? 'border-indigo-500 bg-indigo-500/10'
                          : 'border-gray-700 bg-gray-800 hover:border-gray-600'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span>{type.icon}</span>
                        <span className="text-white font-medium text-sm">{type.label}</span>
                      </div>
                      <p className="text-gray-500 text-xs">{type.description}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Content */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Content</label>
                <textarea
                  value={form.content}
                  onChange={e => setForm({ ...form, content: e.target.value })}
                  required
                  rows={4}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder={getTypeConfig(form.memory_type).example}
                />
              </div>

              {/* Scope Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">Who can access this memory?</label>
                <div className="grid grid-cols-3 gap-3">
                  {MEMORY_SCOPES.map(scope => (
                    <button
                      key={scope.value}
                      type="button"
                      onClick={() => setForm({ ...form, scope: scope.value })}
                      className={`p-4 rounded-lg border text-center transition-colors ${
                        form.scope === scope.value
                          ? 'border-indigo-500 bg-indigo-500/10'
                          : 'border-gray-700 bg-gray-800 hover:border-gray-600'
                      }`}
                    >
                      <span className="text-2xl mb-2 block">{scope.icon}</span>
                      <span className="text-white font-medium text-sm">{scope.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Agent Selection (for agent scope) */}
              {form.scope === 'agent' && agents.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">Assign to Agent</label>
                  <select
                    value={form.agent_id}
                    onChange={e => setForm({ ...form, agent_id: e.target.value })}
                    className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {agents.map(agent => (
                      <option key={agent.id} value={agent.id}>🤖 {agent.name} (@{agent.slug})</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Tags */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Tags (optional)</label>
                <input
                  type="text"
                  value={form.tags}
                  onChange={e => setForm({ ...form, tags: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="customer:acme, project:q1, important"
                />
                <p className="text-gray-500 text-xs mt-1">Separate tags with commas</p>
              </div>

              {/* Actions */}
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !form.content}
                  className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Store Memory'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Memory Detail Modal */}
      {showDetailModal && selectedMemory && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-lg border border-gray-800">
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-3">
                <span className="text-3xl">{getTypeConfig(selectedMemory.memory_type).icon}</span>
                <div>
                  <h2 className="text-xl font-bold text-white">{getTypeConfig(selectedMemory.memory_type).label}</h2>
                  <p className="text-gray-400 text-sm">{getScopeConfig(selectedMemory.scope).label}</p>
                </div>
              </div>
              <button
                onClick={() => {
                  setShowDetailModal(false)
                  setSelectedMemory(null)
                }}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div className="p-4 bg-gray-800 rounded-lg">
                <p className="text-white whitespace-pre-wrap">{selectedMemory.content}</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-gray-800 rounded-lg">
                  <p className="text-gray-500 text-xs mb-1">Created</p>
                  <p className="text-white text-sm">{new Date(selectedMemory.created_at).toLocaleString()}</p>
                </div>
                <div className="p-3 bg-gray-800 rounded-lg">
                  <p className="text-gray-500 text-xs mb-1">Scope</p>
                  <p className="text-white text-sm flex items-center gap-1">
                    <span>{getScopeConfig(selectedMemory.scope).icon}</span>
                    {getScopeConfig(selectedMemory.scope).label}
                  </p>
                </div>
              </div>

              {selectedMemory.tags && selectedMemory.tags.length > 0 && (
                <div className="p-3 bg-gray-800 rounded-lg">
                  <p className="text-gray-500 text-xs mb-2">Tags</p>
                  <div className="flex flex-wrap gap-2">
                    {selectedMemory.tags.map(tag => (
                      <span key={tag} className="px-2 py-1 text-sm bg-gray-700 text-gray-300 rounded">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <button
                onClick={() => handleDelete(selectedMemory.id)}
                className="w-full py-3 bg-red-600/20 text-red-400 font-medium rounded-lg hover:bg-red-600/30 transition-colors"
              >
                Delete Memory
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
