import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'

interface Memory {
  id: string
  content: string
  memory_type: string
  agent_id?: string
  created_at: string
}

export default function Memory() {
  const api = useApi<any>()
  const [memories, setMemories] = useState<Memory[]>([])
  const [search, setSearch] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ content: '', memory_type: 'general' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadMemories()
  }, [])

  async function loadMemories() {
    try {
      const data = await api.get('/api/v1/memory?limit=50')
      setMemories(data.items || [])
    } catch {}
  }

  async function handleSearch() {
    if (!search.trim()) {
      loadMemories()
      return
    }
    try {
      const data = await api.post('/api/v1/memory/search', { query: search, limit: 20 })
      setMemories(data.results || [])
    } catch {}
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post('/api/v1/memory', form)
      setShowModal(false)
      setForm({ content: '', memory_type: 'general' })
      loadMemories()
    } catch {}
    setSaving(false)
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this memory?')) return
    try {
      await api.del(`/api/v1/memory/${id}`)
      setMemories(memories.filter(m => m.id !== id))
    } catch {}
  }

  const memoryTypes = ['general', 'preference', 'fact', 'context', 'instruction']

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Memory</h1>
          <p className="text-gray-400 mt-1">Store and search your agent's memories</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity"
        >
          + Store Memory
        </button>
      </div>

      {/* Search */}
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 mb-6">
        <div className="flex gap-3">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Search memories..."
          />
          <button
            onClick={handleSearch}
            className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Search
          </button>
        </div>
      </div>

      {/* Memory List */}
      {memories.length === 0 ? (
        <div className="bg-gray-900 rounded-xl p-12 border border-gray-800 text-center">
          <span className="text-6xl mb-4 block">🧠</span>
          <h2 className="text-xl font-bold text-white mb-2">No memories yet</h2>
          <p className="text-gray-400 mb-6">Store information your agents can remember</p>
          <button
            onClick={() => setShowModal(true)}
            className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Store Your First Memory
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {memories.map(memory => (
            <div key={memory.id} className="bg-gray-900 rounded-xl p-6 border border-gray-800">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                      memory.memory_type === 'preference' ? 'bg-purple-500/10 text-purple-400' :
                      memory.memory_type === 'fact' ? 'bg-blue-500/10 text-blue-400' :
                      memory.memory_type === 'instruction' ? 'bg-orange-500/10 text-orange-400' :
                      'bg-gray-500/10 text-gray-400'
                    }`}>
                      {memory.memory_type}
                    </span>
                    <span className="text-gray-500 text-xs">
                      {new Date(memory.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="text-white">{memory.content}</p>
                </div>
                <button
                  onClick={() => handleDelete(memory.id)}
                  className="p-2 text-gray-500 hover:text-red-400 transition-colors"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-lg border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-6">Store Memory</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Type</label>
                <select
                  value={form.memory_type}
                  onChange={e => setForm({ ...form, memory_type: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {memoryTypes.map(type => (
                    <option key={type} value={type}>{type.charAt(0).toUpperCase() + type.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Content</label>
                <textarea
                  value={form.content}
                  onChange={e => setForm({ ...form, content: e.target.value })}
                  required
                  rows={5}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="What should your agent remember?"
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
                  {saving ? 'Saving...' : 'Store Memory'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
