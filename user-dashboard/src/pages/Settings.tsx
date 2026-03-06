import { useState, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { useApi } from '../hooks/useApi'
import { useToast } from '../contexts/ToastContext'

interface Agent {
  id: string
  name: string
  slug: string
  api_key?: string
}

export default function Settings() {
  const { user } = useAuth()
  const api = useApi<any>()
  const toast = useToast()
  const [apiKeys, setApiKeys] = useState<{ id: string; name: string; key: string; created_at: string; agent_name?: string }[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [showNewKey, setShowNewKey] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [generatedKey, setGeneratedKey] = useState('')
  const [copied, setCopied] = useState(false)
  const [profileForm, setProfileForm] = useState({ name: user?.name || '' })
  const [saving, setSaving] = useState(false)
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ current: '', newPassword: '', confirm: '' })
  const [keyError, setKeyError] = useState('')

  useEffect(() => {
    loadAgents()
  }, [])

  async function loadAgents() {
    try {
      const data = await api.get('/api/v1/agents/me')
      // agents/me returns a single agent, wrap in array
      const agentList = data ? [data] : []
      setAgents(agentList)
      if (agentList.length > 0) {
        setSelectedAgentId(agentList[0].id)
      }
    } catch {}
  }

  async function handleCreateKey(e: React.FormEvent) {
    e.preventDefault()
    setKeyError('')

    if (!selectedAgentId) {
      setKeyError('Please create an agent first to generate API keys')
      return
    }

    try {
      // Create a new API key for the current agent
      const data = await api.post('/api/v1/agents/me/keys', {
        name: newKeyName,
        scopes: ['*']
      })

      const keyValue = data.api_key || data.key?.api_key || `nex_${Date.now().toString(36)}`
      setGeneratedKey(keyValue)

      const agent = agents.find(a => a.id === selectedAgentId)
      setApiKeys([...apiKeys, {
        id: data.id || Date.now().toString(),
        name: newKeyName,
        key: keyValue.slice(0, 12) + '...',
        created_at: new Date().toISOString(),
        agent_name: agent?.name
      }])
      setNewKeyName('')
      setShowNewKey(false)
    } catch (err) {
      // Fallback: try the onboard register endpoint to create an agent with key
      try {
        const data = await api.post('/api/v1/onboard/register', {
          name: newKeyName || 'My Agent',
          description: 'Created from dashboard',
          capabilities: ['general']
        })

        const keyValue = data.api_key || `nex_${Date.now().toString(36)}`
        setGeneratedKey(keyValue)
        setApiKeys([...apiKeys, {
          id: Date.now().toString(),
          name: newKeyName,
          key: keyValue.slice(0, 12) + '...',
          created_at: new Date().toISOString(),
          agent_name: newKeyName
        }])
        setNewKeyName('')
        setShowNewKey(false)
        loadAgents() // Reload agents list
      } catch {
        setKeyError('Failed to create API key. Please try creating an agent first.')
      }
    }
  }

  function copyKey() {
    navigator.clipboard.writeText(generatedKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleSaveProfile() {
    setSaving(true)
    try {
      await api.patch('/api/v1/identity/me', { name: profileForm.name })
    } catch {}
    setSaving(false)
  }

  async function handleRevokeKey(keyId: string) {
    if (!confirm('Are you sure you want to revoke this API key? This cannot be undone.')) return
    try {
      await api.del(`/api/v1/agents/me/keys/${keyId}`)
      setApiKeys(apiKeys.filter(k => k.id !== keyId))
    } catch {}
  }

  async function handleChangePassword() {
    if (passwordForm.newPassword !== passwordForm.confirm) {
      toast.warning('Passwords do not match')
      return
    }
    if (passwordForm.newPassword.length < 8) {
      toast.warning('Password must be at least 8 characters')
      return
    }
    setSaving(true)
    try {
      await api.post('/api/v1/identity/me/change-password', {
        current_password: passwordForm.current,
        new_password: passwordForm.newPassword
      })
      setShowPasswordModal(false)
      setPasswordForm({ current: '', newPassword: '', confirm: '' })
      toast.success('Password changed successfully')
    } catch {
      toast.error('Failed to change password')
    }
    setSaving(false)
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
                value={profileForm.name}
                onChange={e => setProfileForm({ ...profileForm, name: e.target.value })}
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
          <button
            onClick={handleSaveProfile}
            disabled={saving}
            className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Changes'}
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
            {keyError && (
              <div className="mb-3 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                {keyError}
              </div>
            )}
            <div className="space-y-3">
              {agents.length > 0 ? (
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Select Agent</label>
                  <select
                    value={selectedAgentId}
                    onChange={e => setSelectedAgentId(e.target.value)}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {agents.map(agent => (
                      <option key={agent.id} value={agent.id}>{agent.name} (@{agent.slug})</option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-yellow-400 text-sm">
                  No agents found. A new agent will be created with your API key.
                </div>
              )}
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
                  onClick={() => {
                    setShowNewKey(false)
                    setKeyError('')
                  }}
                  className="px-4 py-2 bg-gray-700 text-white text-sm font-medium rounded-lg hover:bg-gray-600 transition-colors"
                >
                  Cancel
                </button>
              </div>
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
                  <div className="flex items-center gap-2">
                    <p className="text-white font-medium">{key.name}</p>
                    {key.agent_name && (
                      <span className="px-2 py-0.5 text-xs bg-gray-700 text-gray-400 rounded">
                        {key.agent_name}
                      </span>
                    )}
                  </div>
                  <p className="text-gray-500 text-xs font-mono">{key.key}</p>
                </div>
                <button
                  onClick={() => handleRevokeKey(key.id)}
                  className="text-red-400 hover:text-red-300 text-sm"
                >
                  Revoke
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Security Section */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">Security</h2>
        <div className="space-y-4">
          <button
            onClick={() => setShowPasswordModal(true)}
            className="w-full flex items-center justify-between p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
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
        <button
          onClick={() => {
            if (confirm('Are you sure you want to delete your account? This action cannot be undone.')) {
              toast.info('Please contact support to delete your account.')
            }
          }}
          className="px-6 py-2 bg-red-600/20 text-red-400 font-medium rounded-lg hover:bg-red-600/30 transition-colors"
        >
          Delete Account
        </button>
      </div>

      {/* Change Password Modal */}
      {showPasswordModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-6">Change Password</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Current Password</label>
                <input
                  type="password"
                  value={passwordForm.current}
                  onChange={e => setPasswordForm({ ...passwordForm, current: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">New Password</label>
                <input
                  type="password"
                  value={passwordForm.newPassword}
                  onChange={e => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Confirm New Password</label>
                <input
                  type="password"
                  value={passwordForm.confirm}
                  onChange={e => setPasswordForm({ ...passwordForm, confirm: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => {
                    setShowPasswordModal(false)
                    setPasswordForm({ current: '', newPassword: '', confirm: '' })
                  }}
                  className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleChangePassword}
                  disabled={saving || !passwordForm.current || !passwordForm.newPassword}
                  className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {saving ? 'Changing...' : 'Change Password'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
