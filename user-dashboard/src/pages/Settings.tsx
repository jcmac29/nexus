import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { useApi } from '../hooks/useApi'

export default function Settings() {
  const { user } = useAuth()
  const api = useApi<any>()
  const [apiKeys, setApiKeys] = useState<{ id: string; name: string; key: string; created_at: string }[]>([])
  const [showNewKey, setShowNewKey] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [generatedKey, setGeneratedKey] = useState('')
  const [copied, setCopied] = useState(false)

  async function handleCreateKey(e: React.FormEvent) {
    e.preventDefault()
    try {
      const data = await api.post('/api/v1/identity/api-keys', { name: newKeyName })
      setGeneratedKey(data.api_key)
      setApiKeys([...apiKeys, { id: data.id, name: newKeyName, key: data.api_key.slice(0, 12) + '...', created_at: new Date().toISOString() }])
      setNewKeyName('')
    } catch {}
  }

  function copyKey() {
    navigator.clipboard.writeText(generatedKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Settings</h1>
        <p className="text-gray-400 mt-1">Manage your account and API keys</p>
      </div>

      {/* Profile Section */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">Profile</h2>
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-2xl font-bold text-white">
              {user?.name?.[0]?.toUpperCase() || 'U'}
            </div>
            <div>
              <p className="text-white font-medium">{user?.name}</p>
              <p className="text-gray-400 text-sm">{user?.email}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 pt-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
              <input
                type="text"
                defaultValue={user?.name}
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Email</label>
              <input
                type="email"
                defaultValue={user?.email}
                disabled
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-gray-400"
              />
            </div>
          </div>
          <button className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors">
            Save Changes
          </button>
        </div>
      </div>

      {/* API Keys Section */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">API Keys</h2>
          <button
            onClick={() => setShowNewKey(true)}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
          >
            + Create Key
          </button>
        </div>

        {generatedKey && (
          <div className="mb-4 p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
            <p className="text-green-400 text-sm mb-2">New API key created! Copy it now - you won't see it again.</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 py-2 bg-gray-800 rounded text-white font-mono text-sm">{generatedKey}</code>
              <button
                onClick={copyKey}
                className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        {showNewKey && !generatedKey && (
          <form onSubmit={handleCreateKey} className="mb-4 p-4 bg-gray-800 rounded-lg">
            <div className="flex gap-3">
              <input
                type="text"
                value={newKeyName}
                onChange={e => setNewKeyName(e.target.value)}
                required
                className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Key name (e.g., Production, Development)"
              />
              <button
                type="submit"
                className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Create
              </button>
              <button
                type="button"
                onClick={() => setShowNewKey(false)}
                className="px-4 py-2 bg-gray-700 text-white text-sm font-medium rounded-lg hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {apiKeys.length === 0 ? (
          <p className="text-gray-400 text-sm">No API keys yet. Create one to get started.</p>
        ) : (
          <div className="space-y-3">
            {apiKeys.map(key => (
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
      </div>

      {/* Security Section */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">Security</h2>
        <div className="space-y-4">
          <button className="w-full flex items-center justify-between p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors">
            <div>
              <p className="text-white font-medium">Change Password</p>
              <p className="text-gray-400 text-sm">Update your password</p>
            </div>
            <span className="text-gray-400">→</span>
          </button>
          <button className="w-full flex items-center justify-between p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors">
            <div>
              <p className="text-white font-medium">Two-Factor Authentication</p>
              <p className="text-gray-400 text-sm">Add an extra layer of security</p>
            </div>
            <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-700 text-gray-400">Coming Soon</span>
          </button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="bg-gray-900 rounded-xl p-6 border border-red-500/20">
        <h2 className="text-lg font-semibold text-red-400 mb-4">Danger Zone</h2>
        <button className="px-6 py-2 bg-red-600/20 text-red-400 font-medium rounded-lg hover:bg-red-600/30 transition-colors">
          Delete Account
        </button>
      </div>
    </div>
  )
}
