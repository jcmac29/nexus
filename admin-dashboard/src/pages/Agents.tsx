import { Plus, Search } from 'lucide-react';
import { useState } from 'react';
import DataTable from '../components/DataTable';
import { useAgents } from '../hooks/useApi';

export default function Agents() {
  const [search, setSearch] = useState('');
  const { data, isLoading } = useAgents();

  const agents = data?.items ?? [];
  const filteredAgents = agents.filter(
    (agent) =>
      agent.name.toLowerCase().includes(search.toLowerCase()) ||
      agent.slug.toLowerCase().includes(search.toLowerCase())
  );

  const columns = [
    { key: 'name', header: 'Name' },
    { key: 'slug', header: 'Slug' },
    {
      key: 'status',
      header: 'Status',
      render: (agent: (typeof filteredAgents)[0]) => (
        <span
          className={`px-2 py-1 rounded-full text-xs font-medium ${
            agent.status === 'active'
              ? 'bg-green-100 text-green-800'
              : 'bg-gray-100 text-gray-800'
          }`}
        >
          {agent.status}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (agent: (typeof filteredAgents)[0]) =>
        new Date(agent.created_at).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: () => (
        <button className="text-indigo-600 hover:text-indigo-800 text-sm font-medium">
          View
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          <p className="text-gray-600 mt-1">Manage your AI agents</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" />
          Add Agent
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search agents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
      </div>

      <DataTable columns={columns} data={filteredAgents} loading={isLoading} />
    </div>
  );
}
