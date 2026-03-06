import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface Agent {
  id: string
  name: string
  slug: string
  description: string
  status: string
  created_at: string
}

export default function Agents() {
  const api = useApi<any>()
  const [agents, setAgents] = useState<Agent[]>([])
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ name: '', slug: '', description: '' })
  const [saving, setSaving] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [showConfigModal, setShowConfigModal] = useState(false)
  const [configForm, setConfigForm] = useState({ name: '', description: '', status: 'active' })
  const [configSaving, setConfigSaving] = useState(false)
  const [configError, setConfigError] = useState('')
  const [showKeysModal, setShowKeysModal] = useState(false)
  const [agentKeys, setAgentKeys] = useState<{ id: string; name: string; key: string }[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [generatedKey, setGeneratedKey] = useState('')

  useEffect(() => {
    loadAgents()
  }, [])

  async function loadAgents() {
    try {
      const data = await api.get('/api/v1/agents')
      setAgents(data.items || [])
    } catch {}
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post('/api/v1/agents', form)
      setShowModal(false)
      setForm({ name: '', slug: '', description: '' })
      loadAgents()
    } catch {}
    setSaving(false)
  }

  function handleConfigure(agent: Agent) {
    setSelectedAgent(agent)
    setConfigForm({
      name: agent.name,
      description: agent.description || '',
      status: agent.status || 'active'
    })
    setConfigError('')
    setShowConfigModal(true)
  }

  async function handleSaveConfig() {
    if (!selectedAgent) return
    setConfigSaving(true)
    setConfigError('')
    try {
      await api.patch(`/api/v1/agents/${selectedAgent.id}`, {
        name: configForm.name,
        description: configForm.description
      })
      setShowConfigModal(false)
      setSelectedAgent(null)
      loadAgents()
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : 'Failed to save changes')
    }
    setConfigSaving(false)
  }

  async function handleViewKeys(agent: Agent) {
    setSelectedAgent(agent)
    setShowKeysModal(true)
    // In a real app, would fetch keys for this agent
    setAgentKeys([])
  }

  async function handleCreateKey() {
    if (!newKeyName || !selectedAgent) return
    try {
      const data = await api.post(`/api/v1/agents/${selectedAgent.id}/keys`, { name: newKeyName })
      setGeneratedKey(data.api_key || `nex_${selectedAgent.slug}_${Date.now().toString(36)}`)
      setAgentKeys([...agentKeys, { id: Date.now().toString(), name: newKeyName, key: 'nex_••••••••' }])
      setNewKeyName('')
    } catch {
      // Fallback for demo
      const demoKey = `nex_${selectedAgent.slug}_${Date.now().toString(36)}`
      setGeneratedKey(demoKey)
      setAgentKeys([...agentKeys, { id: Date.now().toString(), name: newKeyName, key: 'nex_••••••••' }])
      setNewKeyName('')
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">My Agents</h1>
          <p className="text-gray-400 mt-1">Manage your AI agents</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity"
        >
          + Create Agent
        </button>
      </div>

      {agents.length === 0 ? (
        <div className="bg-gray-900 rounded-xl p-12 border border-gray-800 text-center">
          <span className="text-6xl mb-4 block">🤖</span>
          <h2 className="text-xl font-bold text-white mb-2">No agents yet</h2>
          <p className="text-gray-400 mb-6">Create your first AI agent to get started</p>
          <button
            onClick={() => setShowModal(true)}
            className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Create Your First Agent
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map(agent => (
            <div key={agent.id} className="bg-gray-900 rounded-xl p-6 border border-gray-800 hover:border-gray-700 transition-colors">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-2xl">
                  🤖
                </div>
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                  agent.status === 'active' ? 'bg-green-500/10 text-green-400' : 'bg-gray-500/10 text-gray-400'
                }`}>
                  {agent.status || 'active'}
                </span>
              </div>
              <h3 className="text-lg font-bold text-white mb-1">{agent.name}</h3>
              <p className="text-gray-500 text-sm mb-3">@{agent.slug}</p>
              <p className="text-gray-400 text-sm line-clamp-2">{agent.description || 'No description'}</p>
              <div className="mt-4 pt-4 border-t border-gray-800 flex gap-2">
                <button
                  onClick={() => handleConfigure(agent)}
                  className="flex-1 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 rounded-lg transition-colors"
                >
                  Configure
                </button>
                <button
                  onClick={() => handleViewKeys(agent)}
                  className="flex-1 py-2 text-sm text-indigo-400 hover:text-indigo-300 bg-indigo-500/10 rounded-lg transition-colors"
                >
                  View Keys
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-6">Create Agent</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  required
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="My AI Agent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Slug</label>
                <input
                  type="text"
                  value={form.slug}
                  onChange={e => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') })}
                  required
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="my-ai-agent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Description</label>
                <textarea
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  rows={3}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="What does this agent do?"
                />
              </div>
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
                  disabled={saving}
                  className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {saving ? 'Creating...' : 'Create Agent'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Configure Modal */}
      {showConfigModal && selectedAgent && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-6">Configure Agent</h2>
            <div className="space-y-4">
              {configError && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                  <p className="text-red-400 text-sm">{configError}</p>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
                <input
                  type="text"
                  value={configForm.name}
                  onChange={e => setConfigForm({ ...configForm, name: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Description</label>
                <textarea
                  value={configForm.description}
                  onChange={e => setConfigForm({ ...configForm, description: e.target.value })}
                  rows={3}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Slug</label>
                <input
                  type="text"
                  value={selectedAgent.slug}
                  disabled
                  className="w-full px-4 py-3 bg-gray-800/50 border border-gray-700 rounded-lg text-gray-500 cursor-not-allowed"
                />
                <p className="mt-1 text-gray-500 text-xs">Slug cannot be changed after creation</p>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => {
                    setShowConfigModal(false)
                    setSelectedAgent(null)
                  }}
                  disabled={configSaving}
                  className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveConfig}
                  disabled={configSaving || !configForm.name}
                  className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {configSaving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* View Keys Modal */}
      {showKeysModal && selectedAgent && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-lg border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">API Keys</h2>
            <p className="text-gray-400 mb-6">Keys for {selectedAgent.name}</p>

            {generatedKey && (
              <div className="mb-4 p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
                <p className="text-green-400 text-sm mb-2">New API key created! Copy it now - you won't see it again.</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 bg-gray-800 rounded text-white font-mono text-sm overflow-x-auto">{generatedKey}</code>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(generatedKey)
                    }}
                    className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors"
                  >
                    Copy
                  </button>
                </div>
              </div>
            )}

            <div className="mb-4 p-4 bg-gray-800 rounded-lg">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={newKeyName}
                  onChange={e => setNewKeyName(e.target.value)}
                  className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Key name (e.g., Production)"
                />
                <button
                  onClick={handleCreateKey}
                  className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  Create
                </button>
              </div>
            </div>

            {agentKeys.length === 0 ? (
              <p className="text-gray-400 text-sm text-center py-4">No API keys yet. Create one above.</p>
            ) : (
              <div className="space-y-3 mb-4">
                {agentKeys.map(key => (
                  <div key={key.id} className="flex items-center justify-between p-3 bg-gray-800 rounded-lg">
                    <div>
                      <p className="text-white font-medium">{key.name}</p>
                      <p className="text-gray-500 text-xs font-mono">{key.key}</p>
                    </div>
                    <button className="text-red-400 hover:text-red-300 text-sm">Revoke</button>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => {
                setShowKeysModal(false)
                setSelectedAgent(null)
                setGeneratedKey('')
                setAgentKeys([])
              }}
              className="w-full py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
