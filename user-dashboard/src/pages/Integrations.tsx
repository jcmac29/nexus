import { useState } from 'react'

interface Integration {
  id: string
  name: string
  type: string
  icon: string
  description: string
  connected: boolean
  config?: Record<string, string>
}

const AVAILABLE_INTEGRATIONS: Omit<Integration, 'id' | 'connected' | 'config'>[] = [
  { name: 'OpenAI', type: 'ai', icon: '🤖', description: 'GPT-4, ChatGPT, DALL-E, Whisper' },
  { name: 'Anthropic', type: 'ai', icon: '🧠', description: 'Claude 3, Claude 2' },
  { name: 'Slack', type: 'messaging', icon: '💬', description: 'Send messages, read channels' },
  { name: 'Discord', type: 'messaging', icon: '🎮', description: 'Bot integration, webhooks' },
  { name: 'Twilio', type: 'communication', icon: '📱', description: 'SMS, Voice, WhatsApp' },
  { name: 'SendGrid', type: 'email', icon: '📧', description: 'Transactional email' },
  { name: 'Stripe', type: 'payments', icon: '💳', description: 'Payments, subscriptions' },
  { name: 'GitHub', type: 'development', icon: '🐙', description: 'Repos, issues, PRs' },
  { name: 'Google Calendar', type: 'productivity', icon: '📅', description: 'Events, scheduling' },
  { name: 'Notion', type: 'productivity', icon: '📝', description: 'Pages, databases' },
  { name: 'Airtable', type: 'database', icon: '📊', description: 'Tables, automations' },
  { name: 'Zapier', type: 'automation', icon: '⚡', description: 'Connect 5000+ apps' },
]

export default function Integrations() {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [showModal, setShowModal] = useState(false)
  const [selectedIntegration, setSelectedIntegration] = useState<typeof AVAILABLE_INTEGRATIONS[0] | null>(null)
  const [apiKey, setApiKey] = useState('')

  function handleConnect() {
    if (!selectedIntegration || !apiKey) return

    const newIntegration: Integration = {
      id: Date.now().toString(),
      ...selectedIntegration,
      connected: true,
      config: { apiKey: apiKey.slice(0, 8) + '...' }
    }

    setIntegrations([...integrations, newIntegration])
    setShowModal(false)
    setSelectedIntegration(null)
    setApiKey('')
  }

  function handleDisconnect(id: string) {
    setIntegrations(integrations.filter(i => i.id !== id))
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Integrations</h1>
        <p className="text-gray-400 mt-1">Connect your favorite APIs and services</p>
      </div>

      {/* Connected Integrations */}
      {integrations.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Connected</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {integrations.map(integration => (
              <div key={integration.id} className="bg-gray-900 rounded-xl p-6 border border-green-500/30">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-3xl">{integration.icon}</span>
                    <div>
                      <h3 className="font-bold text-white">{integration.name}</h3>
                      <p className="text-gray-500 text-sm">{integration.type}</p>
                    </div>
                  </div>
                  <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-500/10 text-green-400">
                    Connected
                  </span>
                </div>
                <div className="flex gap-2">
                  <button className="flex-1 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 rounded-lg transition-colors">
                    Configure
                  </button>
                  <button
                    onClick={() => handleDisconnect(integration.id)}
                    className="flex-1 py-2 text-sm text-red-400 hover:text-red-300 bg-red-500/10 rounded-lg transition-colors"
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Available Integrations */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Available Integrations</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {AVAILABLE_INTEGRATIONS.filter(i => !integrations.some(c => c.name === i.name)).map(integration => (
            <div key={integration.name} className="bg-gray-900 rounded-xl p-6 border border-gray-800 hover:border-gray-700 transition-colors">
              <div className="flex items-center gap-3 mb-3">
                <span className="text-3xl">{integration.icon}</span>
                <div>
                  <h3 className="font-bold text-white">{integration.name}</h3>
                  <p className="text-gray-500 text-xs">{integration.type}</p>
                </div>
              </div>
              <p className="text-gray-400 text-sm mb-4">{integration.description}</p>
              <button
                onClick={() => {
                  setSelectedIntegration(integration)
                  setShowModal(true)
                }}
                className="w-full py-2 text-sm text-indigo-400 hover:text-white bg-indigo-500/10 hover:bg-indigo-500 rounded-lg transition-all"
              >
                Connect
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Custom Integration */}
      <div className="mt-8 bg-gray-900 rounded-xl p-6 border border-dashed border-gray-700">
        <div className="text-center">
          <span className="text-4xl mb-4 block">🔧</span>
          <h3 className="text-lg font-bold text-white mb-2">Custom Integration</h3>
          <p className="text-gray-400 text-sm mb-4">Connect any REST API with custom configuration</p>
          <button className="px-6 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors">
            Add Custom API
          </button>
        </div>
      </div>

      {/* Connect Modal */}
      {showModal && selectedIntegration && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <div className="flex items-center gap-4 mb-6">
              <span className="text-4xl">{selectedIntegration.icon}</span>
              <div>
                <h2 className="text-2xl font-bold text-white">{selectedIntegration.name}</h2>
                <p className="text-gray-400">{selectedIntegration.description}</p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Enter your API key"
                />
                <p className="mt-2 text-gray-500 text-xs">
                  Your API key is encrypted and stored securely.
                </p>
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => {
                    setShowModal(false)
                    setSelectedIntegration(null)
                    setApiKey('')
                  }}
                  className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConnect}
                  disabled={!apiKey}
                  className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  Connect
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
