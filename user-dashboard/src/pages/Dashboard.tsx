import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../contexts/AuthContext'

interface Stats {
  agents: number
  memories: number
  integrations: number
  apiCalls: number
}

export default function Dashboard() {
  const { user } = useAuth()
  const api = useApi<any>()
  const navigate = useNavigate()
  const [stats, setStats] = useState<Stats>({ agents: 0, memories: 0, integrations: 0, apiCalls: 0 })

  useEffect(() => {
    loadStats()
  }, [])

  async function loadStats() {
    try {
      const [agents, memories] = await Promise.all([
        api.get('/api/v1/agents').catch(() => ({ items: [] })),
        api.get('/api/v1/memory?limit=1').catch(() => ({ total: 0 }))
      ])
      setStats({
        agents: agents.items?.length || 0,
        memories: memories.total || 0,
        integrations: 0,
        apiCalls: 0
      })
    } catch {}
  }

  const statCards = [
    { label: 'Active Agents', value: stats.agents, icon: '🤖', color: 'from-indigo-500 to-purple-600' },
    { label: 'Stored Memories', value: stats.memories, icon: '🧠', color: 'from-green-500 to-emerald-600' },
    { label: 'Integrations', value: stats.integrations, icon: '🔗', color: 'from-blue-500 to-cyan-600' },
    { label: 'API Calls Today', value: stats.apiCalls, icon: '📡', color: 'from-orange-500 to-amber-600' },
  ]

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Welcome back, {user?.name?.split(' ')[0]}</h1>
        <p className="text-gray-400 mt-1">Here's what's happening with your AI agents</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {statCards.map(stat => (
          <div key={stat.label} className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center justify-between mb-4">
              <span className="text-3xl">{stat.icon}</span>
              <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${stat.color} opacity-20`}></div>
            </div>
            <p className="text-3xl font-bold text-white">{stat.value}</p>
            <p className="text-gray-400 text-sm mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button
            onClick={() => navigate('/agents')}
            className="flex items-center gap-4 p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
            <span className="text-2xl">🤖</span>
            <div className="text-left">
              <p className="text-white font-medium">Create Agent</p>
              <p className="text-gray-400 text-sm">Deploy a new AI agent</p>
            </div>
          </button>
          <button
            onClick={() => navigate('/integrations')}
            className="flex items-center gap-4 p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
            <span className="text-2xl">🔗</span>
            <div className="text-left">
              <p className="text-white font-medium">Add Integration</p>
              <p className="text-gray-400 text-sm">Connect an API</p>
            </div>
          </button>
          <button
            onClick={() => navigate('/api-access')}
            className="flex items-center gap-4 p-4 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          >
            <span className="text-2xl">📚</span>
            <div className="text-left">
              <p className="text-white font-medium">View Docs</p>
              <p className="text-gray-400 text-sm">API reference</p>
            </div>
          </button>
        </div>
      </div>

      {/* Getting Started */}
      <div className="bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-xl p-6 border border-indigo-500/20">
        <h2 className="text-xl font-bold text-white mb-2">Getting Started</h2>
        <p className="text-gray-400 mb-4">Complete these steps to get the most out of Nexus</p>
        <div className="space-y-3">
          {[
            { done: true, label: 'Create your account' },
            { done: stats.agents > 0, label: 'Deploy your first agent' },
            { done: stats.integrations > 0, label: 'Connect an integration' },
            { done: stats.memories > 0, label: 'Store your first memory' },
          ].map(step => (
            <div key={step.label} className="flex items-center gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center ${
                step.done ? 'bg-green-500' : 'bg-gray-700'
              }`}>
                {step.done ? '✓' : ''}
              </div>
              <span className={step.done ? 'text-gray-400 line-through' : 'text-white'}>
                {step.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
