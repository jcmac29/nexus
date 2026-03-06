import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { useToast } from '../contexts/ToastContext'

interface TeamMember {
  id: string
  email: string
  name: string
  role: 'owner' | 'admin' | 'member' | 'viewer'
  avatar_url?: string
  joined_at: string
  last_active?: string
  status: 'active' | 'invited' | 'suspended'
}

interface Invite {
  id: string
  email: string
  role: string
  expires_at: string
  created_at: string
  accepted: boolean
}

interface Project {
  id: string
  name: string
  slug: string
  description: string
  color: string
  agent_count: number
  memory_count: number
  created_at: string
}

interface TeamAgent {
  id: string
  name: string
  slug: string
  description: string
  status: 'online' | 'offline' | 'busy'
  capabilities: string[]
  owner_name: string
  project_id?: string
  last_active?: string
}

type TabType = 'members' | 'projects' | 'agents' | 'activity' | 'settings'

export default function Team() {
  const api = useApi<any>()
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<TabType>('members')
  const [members, setMembers] = useState<TeamMember[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [agents, setAgents] = useState<TeamAgent[]>([])
  const [activities, setActivities] = useState<any[]>([])

  // Modals
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [showProjectModal, setShowProjectModal] = useState(false)
  const [showMemberModal, setShowMemberModal] = useState(false)
  const [showAgentModal, setShowAgentModal] = useState(false)
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<TeamAgent | null>(null)

  // Forms
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'member', message: '' })
  const [projectForm, setProjectForm] = useState({ name: '', description: '', color: '#6366f1' })
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Team settings
  const [teamSettings, setTeamSettings] = useState({
    name: 'My Team',
    allow_member_invites: false,
    require_2fa: false,
    default_memory_scope: 'team',
    agent_discovery: 'team',
    allow_external_agents: false
  })

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      // First get user's teams, then get members/agents for the first team
      const teamsData = await api.get('/api/v1/teams/me').catch(() => [])
      const teams = Array.isArray(teamsData) ? teamsData : []
      const teamId = teams[0]?.id

      const [membersData, invitesData, agentsData] = await Promise.all([
        teamId ? api.get(`/api/v1/teams/${teamId}/members`).catch(() => []) : Promise.resolve([]),
        api.get('/api/v1/tenants/invites').catch(() => []),
        api.get('/api/v1/agents/me').catch(() => null).then(agent => agent ? [agent] : []),
      ])
      if (Array.isArray(membersData)) setMembers(membersData.map((m: any) => ({
        id: m.id,
        email: m.email || `${m.slug}@agent`,
        name: m.name,
        role: m.role || 'member',
        joined_at: m.joined_at,
        status: 'active'
      })))
      if (Array.isArray(invitesData)) setInvites(invitesData)
      // Projects endpoint may not exist, use empty array
      setProjects([])
      if (Array.isArray(agentsData)) {
        setAgents(agentsData.map((a: any) => ({
          ...a,
          status: 'online',
          capabilities: a.capabilities || ['general'],
          owner_name: 'You'
        })))
      }
      // Activity endpoint may not exist, use empty array
      setActivities([])
    } catch {}
  }

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await api.post('/api/v1/tenants/invites', {
        email: inviteForm.email,
        role: inviteForm.role
      })
      setShowInviteModal(false)
      setInviteForm({ email: '', role: 'member', message: '' })
      loadData()
    } catch {}
    setLoading(false)
  }

  async function handleCreateProject(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await api.post('/api/v1/projects', projectForm)
      setShowProjectModal(false)
      setProjectForm({ name: '', description: '', color: '#6366f1' })
      loadData()
    } catch {}
    setLoading(false)
  }

  async function handleRevokeInvite(inviteId: string) {
    if (!confirm('Revoke this invitation?')) return
    try {
      await api.del(`/api/v1/tenants/invites/${inviteId}`)
      setInvites(invites.filter(i => i.id !== inviteId))
    } catch {}
  }

  async function handleUpdateMemberRole(memberId: string, newRole: string) {
    try {
      await api.put(`/api/v1/teams/members/${memberId}`, { role: newRole })
      setMembers(members.map(m => m.id === memberId ? { ...m, role: newRole as any } : m))
    } catch {}
  }

  async function handleRemoveMember(memberId: string) {
    if (!confirm('Remove this team member? They will lose access to all team resources.')) return
    try {
      await api.del(`/api/v1/teams/members/${memberId}`)
      setMembers(members.filter(m => m.id !== memberId))
    } catch {}
  }

  async function handleSaveSettings() {
    setLoading(true)
    try {
      await api.put('/api/v1/teams/settings', teamSettings)
      toast.success('Settings saved!')
    } catch {
      toast.error('Failed to save settings')
    }
    setLoading(false)
  }

  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case 'owner': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
      case 'admin': return 'bg-purple-500/10 text-purple-400 border-purple-500/20'
      case 'member': return 'bg-blue-500/10 text-blue-400 border-blue-500/20'
      case 'viewer': return 'bg-gray-500/10 text-gray-400 border-gray-500/20'
      default: return 'bg-gray-500/10 text-gray-400 border-gray-500/20'
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online': return 'bg-green-500'
      case 'busy': return 'bg-yellow-500'
      case 'offline': return 'bg-gray-500'
      default: return 'bg-gray-500'
    }
  }

  const filteredMembers = members.filter(m =>
    m.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    m.email.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const filteredAgents = agents.filter(a =>
    a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a.slug.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const tabs: { id: TabType; label: string; icon: string; count?: number }[] = [
    { id: 'members', label: 'Members', icon: '👥', count: members.length + invites.filter(i => !i.accepted).length },
    { id: 'projects', label: 'Projects', icon: '📁', count: projects.length },
    { id: 'agents', label: 'AI Agents', icon: '🤖', count: agents.length },
    { id: 'activity', label: 'Activity', icon: '📋' },
    { id: 'settings', label: 'Settings', icon: '⚙️' },
  ]

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Team Management</h1>
          <p className="text-gray-400 mt-1">Manage members, projects, and AI agents</p>
        </div>
        <div className="flex gap-3">
          {activeTab === 'members' && (
            <button
              onClick={() => setShowInviteModal(true)}
              className="px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity flex items-center gap-2"
            >
              <span>+</span> Invite Member
            </button>
          )}
          {activeTab === 'projects' && (
            <button
              onClick={() => setShowProjectModal(true)}
              className="px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity flex items-center gap-2"
            >
              <span>+</span> New Project
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-900 p-1 rounded-xl w-fit">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            <span>{tab.icon}</span>
            {tab.label}
            {tab.count !== undefined && (
              <span className={`px-1.5 py-0.5 text-xs rounded-full ${
                activeTab === tab.id ? 'bg-white/20' : 'bg-gray-800'
              }`}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Search Bar (for members and agents) */}
      {(activeTab === 'members' || activeTab === 'agents') && (
        <div className="mb-6">
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder={`Search ${activeTab}...`}
            className="w-full max-w-md px-4 py-3 bg-gray-900 border border-gray-800 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      )}

      {/* Members Tab */}
      {activeTab === 'members' && (
        <div className="space-y-6">
          {/* How It Works Banner */}
          <div className="bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-xl p-6 border border-indigo-500/20">
            <h3 className="text-lg font-bold text-white mb-3">How Team Collaboration Works</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="flex items-start gap-3">
                <span className="text-2xl">1️⃣</span>
                <div>
                  <p className="text-white font-medium">Invite by Email</p>
                  <p className="text-gray-400 text-sm">Send invite with chosen role</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <span className="text-2xl">2️⃣</span>
                <div>
                  <p className="text-white font-medium">They Create Account</p>
                  <p className="text-gray-400 text-sm">Own login, no shared passwords</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <span className="text-2xl">3️⃣</span>
                <div>
                  <p className="text-white font-medium">Join Team Workspace</p>
                  <p className="text-gray-400 text-sm">Access shared resources</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <span className="text-2xl">4️⃣</span>
                <div>
                  <p className="text-white font-medium">Collaborate</p>
                  <p className="text-gray-400 text-sm">Share agents & memories</p>
                </div>
              </div>
            </div>
          </div>

          {/* Pending Invitations */}
          {invites.filter(i => !i.accepted).length > 0 && (
            <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <span>✉️</span> Pending Invitations
              </h3>
              <div className="space-y-3">
                {invites.filter(i => !i.accepted).map(invite => (
                  <div key={invite.id} className="flex items-center justify-between p-4 bg-gray-800 rounded-lg">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-gray-700 rounded-full flex items-center justify-center">
                        <span className="text-gray-400">✉️</span>
                      </div>
                      <div>
                        <p className="text-white font-medium">{invite.email}</p>
                        <p className="text-gray-500 text-sm">
                          Expires {new Date(invite.expires_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-3 py-1 text-xs font-medium rounded-full border ${getRoleBadgeColor(invite.role)}`}>
                        {invite.role}
                      </span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(`${window.location.origin}/invite/${invite.id}`)
                          toast.success('Invite link copied!')
                        }}
                        className="text-indigo-400 hover:text-indigo-300 text-sm"
                      >
                        Copy Link
                      </button>
                      <button
                        onClick={() => handleRevokeInvite(invite.id)}
                        className="text-red-400 hover:text-red-300 text-sm"
                      >
                        Revoke
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Team Members */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">Team Members</h3>
            {filteredMembers.length === 0 && members.length === 0 ? (
              <div className="text-center py-12">
                <span className="text-6xl mb-4 block">👥</span>
                <h3 className="text-xl font-bold text-white mb-2">Start Building Your Team</h3>
                <p className="text-gray-400 mb-6 max-w-md mx-auto">
                  Invite team members to collaborate on AI agents, share memories, and work together on projects.
                </p>
                <button
                  onClick={() => setShowInviteModal(true)}
                  className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  Invite Your First Member
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="text-left py-3 px-4 text-gray-400 font-medium text-sm">Member</th>
                      <th className="text-left py-3 px-4 text-gray-400 font-medium text-sm">Role</th>
                      <th className="text-left py-3 px-4 text-gray-400 font-medium text-sm">Status</th>
                      <th className="text-left py-3 px-4 text-gray-400 font-medium text-sm">Joined</th>
                      <th className="text-right py-3 px-4 text-gray-400 font-medium text-sm">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMembers.map(member => (
                      <tr key={member.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                        <td className="py-4 px-4">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-white font-bold">
                              {member.name?.[0]?.toUpperCase() || member.email[0].toUpperCase()}
                            </div>
                            <div>
                              <p className="text-white font-medium">{member.name || 'Unnamed'}</p>
                              <p className="text-gray-500 text-sm">{member.email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-4 px-4">
                          <select
                            value={member.role}
                            onChange={e => handleUpdateMemberRole(member.id, e.target.value)}
                            disabled={member.role === 'owner'}
                            className={`px-3 py-1.5 text-sm font-medium rounded-lg border bg-transparent cursor-pointer disabled:cursor-not-allowed ${getRoleBadgeColor(member.role)}`}
                          >
                            <option value="viewer">Viewer</option>
                            <option value="member">Member</option>
                            <option value="admin">Admin</option>
                            {member.role === 'owner' && <option value="owner">Owner</option>}
                          </select>
                        </td>
                        <td className="py-4 px-4">
                          <span className="flex items-center gap-2">
                            <span className={`w-2 h-2 rounded-full ${member.status === 'active' ? 'bg-green-500' : 'bg-gray-500'}`}></span>
                            <span className="text-gray-400 text-sm capitalize">{member.status}</span>
                          </span>
                        </td>
                        <td className="py-4 px-4">
                          <span className="text-gray-400 text-sm">
                            {new Date(member.joined_at).toLocaleDateString()}
                          </span>
                        </td>
                        <td className="py-4 px-4 text-right">
                          {member.role !== 'owner' && (
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={() => {
                                  setSelectedMember(member)
                                  setShowMemberModal(true)
                                }}
                                className="text-gray-400 hover:text-white text-sm"
                              >
                                View
                              </button>
                              <button
                                onClick={() => handleRemoveMember(member.id)}
                                className="text-red-400 hover:text-red-300 text-sm"
                              >
                                Remove
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Role Permissions */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">Role Permissions</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-3 px-4 text-gray-400 font-medium text-sm">Permission</th>
                    <th className="text-center py-3 px-4"><span className={`px-3 py-1 text-xs font-medium rounded-full border ${getRoleBadgeColor('owner')}`}>Owner</span></th>
                    <th className="text-center py-3 px-4"><span className={`px-3 py-1 text-xs font-medium rounded-full border ${getRoleBadgeColor('admin')}`}>Admin</span></th>
                    <th className="text-center py-3 px-4"><span className={`px-3 py-1 text-xs font-medium rounded-full border ${getRoleBadgeColor('member')}`}>Member</span></th>
                    <th className="text-center py-3 px-4"><span className={`px-3 py-1 text-xs font-medium rounded-full border ${getRoleBadgeColor('viewer')}`}>Viewer</span></th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {[
                    { perm: 'View agents & memories', owner: true, admin: true, member: true, viewer: true },
                    { perm: 'Create/edit agents', owner: true, admin: true, member: true, viewer: false },
                    { perm: 'Store memories', owner: true, admin: true, member: true, viewer: false },
                    { perm: 'Manage integrations', owner: true, admin: true, member: false, viewer: false },
                    { perm: 'Invite team members', owner: true, admin: true, member: false, viewer: false },
                    { perm: 'Remove members', owner: true, admin: true, member: false, viewer: false },
                    { perm: 'Manage billing', owner: true, admin: false, member: false, viewer: false },
                    { perm: 'Delete team', owner: true, admin: false, member: false, viewer: false },
                  ].map(row => (
                    <tr key={row.perm} className="border-b border-gray-800/50">
                      <td className="py-3 px-4 text-gray-300">{row.perm}</td>
                      <td className="py-3 px-4 text-center">{row.owner ? '✅' : '❌'}</td>
                      <td className="py-3 px-4 text-center">{row.admin ? '✅' : '❌'}</td>
                      <td className="py-3 px-4 text-center">{row.member ? '✅' : '❌'}</td>
                      <td className="py-3 px-4 text-center">{row.viewer ? '✅' : '❌'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Projects Tab */}
      {activeTab === 'projects' && (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-blue-500/10 to-cyan-500/10 rounded-xl p-6 border border-blue-500/20">
            <h3 className="text-lg font-bold text-white mb-2">Organize with Projects</h3>
            <p className="text-gray-400">
              Projects help you separate different initiatives. Each project can have its own agents and memories,
              keeping work isolated while still being accessible to the team.
            </p>
          </div>

          {projects.length === 0 ? (
            <div className="bg-gray-900 rounded-xl p-12 border border-gray-800 text-center">
              <span className="text-6xl mb-4 block">📁</span>
              <h3 className="text-xl font-bold text-white mb-2">No Projects Yet</h3>
              <p className="text-gray-400 mb-6">Create projects to organize your agents and memories by initiative.</p>
              <button
                onClick={() => setShowProjectModal(true)}
                className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Create Your First Project
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {projects.map(project => (
                <div key={project.id} className="bg-gray-900 rounded-xl p-6 border border-gray-800 hover:border-gray-700 transition-colors">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold"
                        style={{ backgroundColor: project.color }}
                      >
                        {project.name[0].toUpperCase()}
                      </div>
                      <div>
                        <h4 className="text-white font-bold">{project.name}</h4>
                        <p className="text-gray-500 text-sm">@{project.slug}</p>
                      </div>
                    </div>
                  </div>
                  <p className="text-gray-400 text-sm mb-4 line-clamp-2">{project.description || 'No description'}</p>
                  <div className="flex items-center gap-4 text-sm text-gray-500">
                    <span className="flex items-center gap-1">
                      <span>🤖</span> {project.agent_count} agents
                    </span>
                    <span className="flex items-center gap-1">
                      <span>🧠</span> {project.memory_count} memories
                    </span>
                  </div>
                  <div className="mt-4 pt-4 border-t border-gray-800 flex gap-2">
                    <button className="flex-1 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 rounded-lg transition-colors">
                      Open
                    </button>
                    <button className="flex-1 py-2 text-sm text-indigo-400 hover:text-indigo-300 bg-indigo-500/10 rounded-lg transition-colors">
                      Settings
                    </button>
                  </div>
                </div>
              ))}

              {/* Add Project Card */}
              <button
                onClick={() => setShowProjectModal(true)}
                className="bg-gray-900 rounded-xl p-6 border border-dashed border-gray-700 hover:border-gray-600 transition-colors flex flex-col items-center justify-center min-h-[200px] text-gray-400 hover:text-white"
              >
                <span className="text-4xl mb-2">+</span>
                <span className="font-medium">New Project</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* AI Agents Tab */}
      {activeTab === 'agents' && (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 rounded-xl p-6 border border-green-500/20">
            <h3 className="text-lg font-bold text-white mb-2">AI Agent Discovery & Communication</h3>
            <p className="text-gray-400">
              View all AI agents in your team. Agents can discover each other, send messages, and delegate tasks.
              This is the foundation for AI-to-AI collaboration.
            </p>
          </div>

          {/* Agent Stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">Total Agents</p>
              <p className="text-2xl font-bold text-white">{agents.length}</p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">Online Now</p>
              <p className="text-2xl font-bold text-green-400">{agents.filter(a => a.status === 'online').length}</p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">Unique Capabilities</p>
              <p className="text-2xl font-bold text-purple-400">
                {new Set(agents.flatMap(a => a.capabilities)).size}
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-sm">Messages Today</p>
              <p className="text-2xl font-bold text-blue-400">0</p>
            </div>
          </div>

          {/* Agent List */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Team Agents</h3>
              <div className="flex gap-2">
                <button className="px-3 py-1.5 text-sm bg-gray-800 text-gray-400 rounded-lg hover:text-white transition-colors">
                  All
                </button>
                <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors">
                  Online
                </button>
                <button className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors">
                  Offline
                </button>
              </div>
            </div>

            {filteredAgents.length === 0 ? (
              <div className="text-center py-12">
                <span className="text-6xl mb-4 block">🤖</span>
                <h3 className="text-xl font-bold text-white mb-2">No Agents Yet</h3>
                <p className="text-gray-400 mb-6">Create your first AI agent to get started with collaboration.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredAgents.map(agent => (
                  <div key={agent.id} className="flex items-center justify-between p-4 bg-gray-800 rounded-lg hover:bg-gray-800/80 transition-colors">
                    <div className="flex items-center gap-4">
                      <div className="relative">
                        <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-2xl">
                          🤖
                        </div>
                        <span className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-gray-800 ${getStatusColor(agent.status)}`}></span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-white font-medium">{agent.name}</p>
                          <span className="text-gray-500 text-sm">@{agent.slug}</span>
                        </div>
                        <p className="text-gray-400 text-sm">{agent.description || 'No description'}</p>
                        <div className="flex gap-1 mt-1">
                          {agent.capabilities.slice(0, 3).map(cap => (
                            <span key={cap} className="px-2 py-0.5 text-xs bg-gray-700 text-gray-300 rounded">
                              {cap}
                            </span>
                          ))}
                          {agent.capabilities.length > 3 && (
                            <span className="px-2 py-0.5 text-xs bg-gray-700 text-gray-400 rounded">
                              +{agent.capabilities.length - 3}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-500 text-sm">Owner: {agent.owner_name}</span>
                      <button
                        onClick={() => {
                          setSelectedAgent(agent)
                          setShowAgentModal(true)
                        }}
                        className="px-4 py-2 text-sm text-indigo-400 hover:text-white bg-indigo-500/10 hover:bg-indigo-500 rounded-lg transition-all"
                      >
                        View Details
                      </button>
                      <button className="px-4 py-2 text-sm text-green-400 hover:text-white bg-green-500/10 hover:bg-green-500 rounded-lg transition-all">
                        Message
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Agent Communication Guide */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">How AI-to-AI Communication Works</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="p-4 bg-gray-800 rounded-lg">
                <span className="text-2xl mb-2 block">🔍</span>
                <h4 className="text-white font-medium mb-1">Discovery</h4>
                <p className="text-gray-400 text-sm">Agents can find each other by capabilities, name, or project using the Discovery API.</p>
                <code className="block mt-2 text-xs text-indigo-400 font-mono">GET /api/v1/discover</code>
              </div>
              <div className="p-4 bg-gray-800 rounded-lg">
                <span className="text-2xl mb-2 block">💬</span>
                <h4 className="text-white font-medium mb-1">Messaging</h4>
                <p className="text-gray-400 text-sm">Send direct messages between agents. Messages can include tasks, data, or queries.</p>
                <code className="block mt-2 text-xs text-indigo-400 font-mono">POST /api/v1/messages</code>
              </div>
              <div className="p-4 bg-gray-800 rounded-lg">
                <span className="text-2xl mb-2 block">📋</span>
                <h4 className="text-white font-medium mb-1">Task Delegation</h4>
                <p className="text-gray-400 text-sm">Agents can assign tasks to other agents based on their capabilities.</p>
                <code className="block mt-2 text-xs text-indigo-400 font-mono">POST /api/v1/swarm/{id}/tasks</code>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Activity Tab */}
      {activeTab === 'activity' && (
        <div className="space-y-6">
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">Recent Activity</h3>
            {activities.length === 0 ? (
              <div className="text-center py-12">
                <span className="text-6xl mb-4 block">📋</span>
                <h3 className="text-xl font-bold text-white mb-2">No Activity Yet</h3>
                <p className="text-gray-400">Activity from team members and agents will appear here.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {activities.map((activity, i) => (
                  <div key={i} className="flex items-start gap-4 p-4 bg-gray-800 rounded-lg">
                    <div className="w-10 h-10 bg-gray-700 rounded-full flex items-center justify-center">
                      {activity.type === 'agent' ? '🤖' : '👤'}
                    </div>
                    <div className="flex-1">
                      <p className="text-white">{activity.message}</p>
                      <p className="text-gray-500 text-sm">{activity.timestamp}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Placeholder Activity */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">Sample Activity Feed</h3>
            <div className="space-y-3">
              {[
                { icon: '👤', text: 'You created agent "Research Assistant"', time: 'Just now' },
                { icon: '🤖', text: 'Research Assistant stored 15 new memories', time: '2 minutes ago' },
                { icon: '👥', text: 'Sarah joined the team as Member', time: '1 hour ago' },
                { icon: '🤖', text: 'Code Reviewer sent message to Research Assistant', time: '2 hours ago' },
                { icon: '📁', text: 'New project "Q1 Analysis" created', time: '3 hours ago' },
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-4 p-3 bg-gray-800/50 rounded-lg">
                  <span className="text-xl">{item.icon}</span>
                  <div className="flex-1">
                    <p className="text-gray-300">{item.text}</p>
                  </div>
                  <span className="text-gray-500 text-sm">{item.time}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <div className="space-y-6 max-w-3xl">
          {/* Team Info */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">Team Information</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Team Name</label>
                <input
                  type="text"
                  value={teamSettings.name}
                  onChange={e => setTeamSettings({ ...teamSettings, name: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>
          </div>

          {/* Member Permissions */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">Member Permissions</h3>
            <div className="space-y-4">
              <label className="flex items-center justify-between p-4 bg-gray-800 rounded-lg cursor-pointer">
                <div>
                  <p className="text-white font-medium">Allow members to invite others</p>
                  <p className="text-gray-400 text-sm">Members can send invitations (not just admins)</p>
                </div>
                <input
                  type="checkbox"
                  checked={teamSettings.allow_member_invites}
                  onChange={e => setTeamSettings({ ...teamSettings, allow_member_invites: e.target.checked })}
                  className="w-5 h-5 rounded bg-gray-700 border-gray-600 text-indigo-600 focus:ring-indigo-500"
                />
              </label>
              <label className="flex items-center justify-between p-4 bg-gray-800 rounded-lg cursor-pointer">
                <div>
                  <p className="text-white font-medium">Require Two-Factor Authentication</p>
                  <p className="text-gray-400 text-sm">All team members must enable 2FA</p>
                </div>
                <input
                  type="checkbox"
                  checked={teamSettings.require_2fa}
                  onChange={e => setTeamSettings({ ...teamSettings, require_2fa: e.target.checked })}
                  className="w-5 h-5 rounded bg-gray-700 border-gray-600 text-indigo-600 focus:ring-indigo-500"
                />
              </label>
            </div>
          </div>

          {/* Memory & Agent Settings */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-lg font-semibold text-white mb-4">Memory & Agent Settings</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Default Memory Scope</label>
                <select
                  value={teamSettings.default_memory_scope}
                  onChange={e => setTeamSettings({ ...teamSettings, default_memory_scope: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="agent">Agent (Private to each agent)</option>
                  <option value="team">Team (Shared with all team agents)</option>
                  <option value="project">Project (Shared within project only)</option>
                </select>
                <p className="mt-2 text-gray-500 text-sm">
                  This determines how memories are shared by default. Can be overridden per-memory.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Agent Discovery</label>
                <select
                  value={teamSettings.agent_discovery}
                  onChange={e => setTeamSettings({ ...teamSettings, agent_discovery: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="team">Team Only (Agents only see team members)</option>
                  <option value="public">Public (Agents can be discovered globally)</option>
                  <option value="private">Private (Agents cannot be discovered)</option>
                </select>
              </div>

              <label className="flex items-center justify-between p-4 bg-gray-800 rounded-lg cursor-pointer">
                <div>
                  <p className="text-white font-medium">Allow External Agent Communication</p>
                  <p className="text-gray-400 text-sm">Your agents can receive messages from agents outside your team</p>
                </div>
                <input
                  type="checkbox"
                  checked={teamSettings.allow_external_agents}
                  onChange={e => setTeamSettings({ ...teamSettings, allow_external_agents: e.target.checked })}
                  className="w-5 h-5 rounded bg-gray-700 border-gray-600 text-indigo-600 focus:ring-indigo-500"
                />
              </label>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-end">
            <button
              onClick={handleSaveSettings}
              disabled={loading}
              className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {loading ? 'Saving...' : 'Save Settings'}
            </button>
          </div>

          {/* Danger Zone */}
          <div className="bg-gray-900 rounded-xl p-6 border border-red-500/20">
            <h3 className="text-lg font-semibold text-red-400 mb-4">Danger Zone</h3>
            <div className="space-y-3">
              <button className="px-4 py-2 bg-red-600/20 text-red-400 font-medium rounded-lg hover:bg-red-600/30 transition-colors">
                Transfer Ownership
              </button>
              <button className="px-4 py-2 bg-red-600/20 text-red-400 font-medium rounded-lg hover:bg-red-600/30 transition-colors ml-3">
                Delete Team
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Invite Member Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">Invite Team Member</h2>
            <p className="text-gray-400 mb-6">They'll receive an email with instructions to join.</p>
            <form onSubmit={handleInvite} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Email Address</label>
                <input
                  type="email"
                  value={inviteForm.email}
                  onChange={e => setInviteForm({ ...inviteForm, email: e.target.value })}
                  required
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="teammate@company.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Role</label>
                <select
                  value={inviteForm.role}
                  onChange={e => setInviteForm({ ...inviteForm, role: e.target.value })}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="member">Member - Create & edit agents, memories</option>
                  <option value="viewer">Viewer - Read-only access</option>
                  <option value="admin">Admin - Full access except billing</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Personal Message (optional)</label>
                <textarea
                  value={inviteForm.message}
                  onChange={e => setInviteForm({ ...inviteForm, message: e.target.value })}
                  rows={2}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Hey! Join our AI team workspace..."
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowInviteModal(false)
                    setInviteForm({ email: '', role: 'member', message: '' })
                  }}
                  className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !inviteForm.email}
                  className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {loading ? 'Sending...' : 'Send Invitation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      {showProjectModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">Create Project</h2>
            <p className="text-gray-400 mb-6">Organize your agents and memories by project.</p>
            <form onSubmit={handleCreateProject} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Project Name</label>
                <input
                  type="text"
                  value={projectForm.name}
                  onChange={e => setProjectForm({ ...projectForm, name: e.target.value })}
                  required
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Q1 Marketing Campaign"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Description</label>
                <textarea
                  value={projectForm.description}
                  onChange={e => setProjectForm({ ...projectForm, description: e.target.value })}
                  rows={3}
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="What is this project about?"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Color</label>
                <div className="flex gap-2">
                  {['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316', '#eab308', '#22c55e', '#06b6d4'].map(color => (
                    <button
                      key={color}
                      type="button"
                      onClick={() => setProjectForm({ ...projectForm, color })}
                      className={`w-8 h-8 rounded-lg transition-transform ${projectForm.color === color ? 'scale-110 ring-2 ring-white' : ''}`}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowProjectModal(false)
                    setProjectForm({ name: '', description: '', color: '#6366f1' })
                  }}
                  className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !projectForm.name}
                  className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {loading ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Member Details Modal */}
      {showMemberModal && selectedMember && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md border border-gray-800">
            <div className="flex items-center gap-4 mb-6">
              <div className="w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-white text-2xl font-bold">
                {selectedMember.name?.[0]?.toUpperCase() || selectedMember.email[0].toUpperCase()}
              </div>
              <div>
                <h2 className="text-2xl font-bold text-white">{selectedMember.name || 'Unnamed'}</h2>
                <p className="text-gray-400">{selectedMember.email}</p>
              </div>
            </div>
            <div className="space-y-4">
              <div className="p-4 bg-gray-800 rounded-lg">
                <p className="text-gray-400 text-sm">Role</p>
                <p className="text-white font-medium capitalize">{selectedMember.role}</p>
              </div>
              <div className="p-4 bg-gray-800 rounded-lg">
                <p className="text-gray-400 text-sm">Joined</p>
                <p className="text-white font-medium">{new Date(selectedMember.joined_at).toLocaleDateString()}</p>
              </div>
              <div className="p-4 bg-gray-800 rounded-lg">
                <p className="text-gray-400 text-sm">Status</p>
                <p className="text-white font-medium capitalize">{selectedMember.status}</p>
              </div>
            </div>
            <button
              onClick={() => {
                setShowMemberModal(false)
                setSelectedMember(null)
              }}
              className="w-full mt-6 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Agent Details Modal */}
      {showAgentModal && selectedAgent && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-lg border border-gray-800">
            <div className="flex items-center gap-4 mb-6">
              <div className="relative">
                <div className="w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-3xl">
                  🤖
                </div>
                <span className={`absolute -bottom-1 -right-1 w-5 h-5 rounded-full border-2 border-gray-900 ${getStatusColor(selectedAgent.status)}`}></span>
              </div>
              <div>
                <h2 className="text-2xl font-bold text-white">{selectedAgent.name}</h2>
                <p className="text-gray-400">@{selectedAgent.slug}</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="p-4 bg-gray-800 rounded-lg">
                <p className="text-gray-400 text-sm mb-1">Description</p>
                <p className="text-white">{selectedAgent.description || 'No description'}</p>
              </div>

              <div className="p-4 bg-gray-800 rounded-lg">
                <p className="text-gray-400 text-sm mb-2">Capabilities</p>
                <div className="flex flex-wrap gap-2">
                  {selectedAgent.capabilities.map(cap => (
                    <span key={cap} className="px-3 py-1 text-sm bg-gray-700 text-gray-300 rounded-full">
                      {cap}
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-gray-800 rounded-lg">
                  <p className="text-gray-400 text-sm">Owner</p>
                  <p className="text-white font-medium">{selectedAgent.owner_name}</p>
                </div>
                <div className="p-4 bg-gray-800 rounded-lg">
                  <p className="text-gray-400 text-sm">Status</p>
                  <p className="text-white font-medium capitalize">{selectedAgent.status}</p>
                </div>
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => {
                    setShowAgentModal(false)
                    setSelectedAgent(null)
                  }}
                  className="flex-1 py-3 bg-gray-800 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Close
                </button>
                <button className="flex-1 py-3 bg-gradient-to-r from-green-500 to-emerald-600 text-white font-medium rounded-lg hover:opacity-90 transition-opacity">
                  Send Message
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
