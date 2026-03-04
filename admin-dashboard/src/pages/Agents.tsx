import { Plus, Search, Edit2, Trash2 } from 'lucide-react';
import { useState } from 'react';
import DataTable from '../components/DataTable';
import Pagination from '../components/Pagination';
import EmptyState from '../components/EmptyState';
import AgentModal from '../components/modals/AgentModal';
import { ConfirmDialog } from '../components/modals';
import { useToast } from '../components/Toast';
import { useAgents, useCreateAgent, useUpdateAgent, useDeleteAgent } from '../hooks/useApi';

interface Agent {
  id: string;
  name: string;
  slug: string;
  status: string;
  description?: string;
  capabilities_count: number;
  memories_count: number;
  created_at: string;
  last_seen: string | null;
}

export default function Agents() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [deletingAgent, setDeletingAgent] = useState<Agent | null>(null);

  const { data, isLoading } = useAgents(page, 20, search || undefined);
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const deleteAgent = useDeleteAgent();
  const { showToast } = useToast();

  const agents = data?.items ?? [];
  const totalPages = data?.pages ?? 1;
  const totalItems = data?.total ?? 0;

  const handleCreate = async (agentData: { name: string; slug: string; description?: string; status: string }) => {
    try {
      await createAgent.mutateAsync(agentData);
      showToast('success', 'Agent created successfully');
      setIsModalOpen(false);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to create agent');
    }
  };

  const handleUpdate = async (agentData: { name: string; slug: string; description?: string; status: string }) => {
    if (!editingAgent) return;
    try {
      await updateAgent.mutateAsync({ id: editingAgent.id, ...agentData });
      showToast('success', 'Agent updated successfully');
      setEditingAgent(null);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to update agent');
    }
  };

  const handleDelete = async () => {
    if (!deletingAgent) return;
    try {
      await deleteAgent.mutateAsync(deletingAgent.id);
      showToast('success', 'Agent deleted successfully');
      setDeletingAgent(null);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to delete agent');
    }
  };

  const columns = [
    { key: 'name', header: 'Name' },
    { key: 'slug', header: 'Slug' },
    {
      key: 'status',
      header: 'Status',
      render: (agent: Agent) => (
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
      key: 'stats',
      header: 'Stats',
      render: (agent: Agent) => (
        <div className="text-sm text-gray-500">
          <span title="Capabilities">{agent.capabilities_count} caps</span>
          <span className="mx-1">/</span>
          <span title="Memories">{agent.memories_count} mems</span>
        </div>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (agent: Agent) =>
        new Date(agent.created_at).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (agent: Agent) => (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setEditingAgent(agent)}
            className="p-1 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded transition-colors"
            title="Edit"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setDeletingAgent(agent)}
            className="p-1 text-red-600 hover:text-red-800 hover:bg-red-50 rounded transition-colors"
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
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
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Agent
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search agents..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
      </div>

      {agents.length === 0 && !isLoading ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          <EmptyState
            icon="bot"
            title="No agents yet"
            description="Create your first AI agent to get started with Nexus."
            action={
              <button
                onClick={() => setIsModalOpen(true)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Create Agent
              </button>
            }
          />
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <DataTable columns={columns} data={agents} loading={isLoading} />
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            totalItems={totalItems}
            pageSize={20}
            onPageChange={setPage}
          />
        </div>
      )}

      {/* Create/Edit Modal */}
      <AgentModal
        isOpen={isModalOpen || !!editingAgent}
        onClose={() => {
          setIsModalOpen(false);
          setEditingAgent(null);
        }}
        onSubmit={editingAgent ? handleUpdate : handleCreate}
        agent={editingAgent}
        isLoading={createAgent.isPending || updateAgent.isPending}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deletingAgent}
        onClose={() => setDeletingAgent(null)}
        onConfirm={handleDelete}
        title="Delete Agent"
        message={`Are you sure you want to delete "${deletingAgent?.name}"? This will also delete all associated memories and capabilities.`}
        confirmLabel="Delete"
        variant="danger"
        isLoading={deleteAgent.isPending}
      />
    </div>
  );
}
