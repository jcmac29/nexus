import { Plus, Users, Edit2, Trash2, ChevronDown, ChevronRight, UserPlus, UserMinus } from 'lucide-react';
import { useState } from 'react';
import DataTable from '../components/DataTable';
import Pagination from '../components/Pagination';
import EmptyState from '../components/EmptyState';
import TeamModal from '../components/modals/TeamModal';
import { ConfirmDialog } from '../components/modals';
import { useToast } from '../components/Toast';
import {
  useTeams,
  useAgents,
  useCreateTeam,
  useUpdateTeam,
  useDeleteTeam,
  useAddTeamMember,
  useRemoveTeamMember,
} from '../hooks/useApi';

interface Team {
  id: string;
  name: string;
  slug: string;
  description?: string;
  member_count: number;
  owner_agent_id?: string;
  members?: Array<{
    agent_id: string;
    agent_name: string;
    agent_slug: string;
    role: string;
    joined_at: string;
  }>;
  created_at: string;
}

export default function Teams() {
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTeam, setEditingTeam] = useState<Team | null>(null);
  const [deletingTeam, setDeletingTeam] = useState<Team | null>(null);
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);
  const [addingMemberTo, setAddingMemberTo] = useState<string | null>(null);
  const [removingMember, setRemovingMember] = useState<{ teamId: string; agentId: string; agentName: string } | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState('');

  const { data, isLoading, refetch } = useTeams(page, 20);
  const { data: agentsData } = useAgents(1, 100);
  const createTeam = useCreateTeam();
  const updateTeam = useUpdateTeam();
  const deleteTeam = useDeleteTeam();
  const addMember = useAddTeamMember();
  const removeMember = useRemoveTeamMember();
  const { showToast } = useToast();

  const teams = data?.items ?? [];
  const totalPages = data?.pages ?? 1;
  const totalItems = data?.total ?? 0;
  const agents = agentsData?.items ?? [];

  const handleCreate = async (teamData: { name: string; slug: string; description?: string; owner_agent_id?: string }) => {
    try {
      await createTeam.mutateAsync(teamData as { name: string; slug: string; owner_agent_id: string; description?: string });
      showToast('success', 'Team created successfully');
      setIsModalOpen(false);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to create team');
    }
  };

  const handleUpdate = async (teamData: { name: string; slug: string; description?: string }) => {
    if (!editingTeam) return;
    try {
      await updateTeam.mutateAsync({ id: editingTeam.id, ...teamData });
      showToast('success', 'Team updated successfully');
      setEditingTeam(null);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to update team');
    }
  };

  const handleDelete = async () => {
    if (!deletingTeam) return;
    try {
      await deleteTeam.mutateAsync(deletingTeam.id);
      showToast('success', 'Team deleted successfully');
      setDeletingTeam(null);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to delete team');
    }
  };

  const handleAddMember = async () => {
    if (!addingMemberTo || !selectedAgentId) return;
    try {
      await addMember.mutateAsync({ teamId: addingMemberTo, agentId: selectedAgentId });
      showToast('success', 'Member added successfully');
      setAddingMemberTo(null);
      setSelectedAgentId('');
      refetch();
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to add member');
    }
  };

  const handleRemoveMember = async () => {
    if (!removingMember) return;
    try {
      await removeMember.mutateAsync({ teamId: removingMember.teamId, agentId: removingMember.agentId });
      showToast('success', 'Member removed successfully');
      setRemovingMember(null);
      refetch();
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to remove member');
    }
  };

  const columns = [
    {
      key: 'expand',
      header: '',
      render: (team: Team) => (
        <button
          onClick={() => setExpandedTeam(expandedTeam === team.id ? null : team.id)}
          className="p-1 text-gray-400 hover:text-gray-600 rounded"
        >
          {expandedTeam === team.id ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>
      ),
    },
    { key: 'name', header: 'Team Name' },
    {
      key: 'member_count',
      header: 'Members',
      render: (team: Team) => (
        <span className="flex items-center gap-1">
          <Users className="w-4 h-4 text-gray-400" />
          {team.member_count}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (team: Team) =>
        new Date(team.created_at).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (team: Team) => (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAddingMemberTo(team.id)}
            className="p-1 text-green-600 hover:text-green-800 hover:bg-green-50 rounded transition-colors"
            title="Add Member"
          >
            <UserPlus className="w-4 h-4" />
          </button>
          <button
            onClick={() => setEditingTeam(team)}
            className="p-1 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded transition-colors"
            title="Edit"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setDeletingTeam(team)}
            className="p-1 text-red-600 hover:text-red-800 hover:bg-red-50 rounded transition-colors"
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  // Custom row render to support expansion
  const renderRow = (team: Team, index: number, defaultRender: () => React.ReactNode) => (
    <>
      {defaultRender()}
      {expandedTeam === team.id && team.members && (
        <tr className="bg-gray-50">
          <td colSpan={columns.length} className="px-6 py-3">
            <div className="text-sm">
              <h4 className="font-medium text-gray-700 mb-2">Team Members</h4>
              {team.members.length === 0 ? (
                <p className="text-gray-500">No members yet</p>
              ) : (
                <ul className="space-y-2">
                  {team.members.map((member) => (
                    <li
                      key={member.agent_id}
                      className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-gray-200"
                    >
                      <div>
                        <span className="font-medium">{member.agent_name}</span>
                        <span className="text-gray-500 ml-2">@{member.agent_slug}</span>
                        <span className={`ml-2 px-2 py-0.5 text-xs rounded-full ${
                          member.role === 'owner'
                            ? 'bg-purple-100 text-purple-700'
                            : member.role === 'admin'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}>
                          {member.role}
                        </span>
                      </div>
                      {member.role !== 'owner' && (
                        <button
                          onClick={() => setRemovingMember({
                            teamId: team.id,
                            agentId: member.agent_id,
                            agentName: member.agent_name,
                          })}
                          className="p-1 text-red-600 hover:text-red-800 hover:bg-red-50 rounded transition-colors"
                          title="Remove Member"
                        >
                          <UserMinus className="w-4 h-4" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Teams</h1>
          <p className="text-gray-600 mt-1">Manage team collaborations</p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Team
        </button>
      </div>

      {teams.length === 0 && !isLoading ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          <EmptyState
            icon="users"
            title="No teams yet"
            description="Create a team to enable agent collaboration."
            action={
              <button
                onClick={() => setIsModalOpen(true)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Create Team
              </button>
            }
          />
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <DataTable columns={columns} data={teams} loading={isLoading} />
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
      <TeamModal
        isOpen={isModalOpen || !!editingTeam}
        onClose={() => {
          setIsModalOpen(false);
          setEditingTeam(null);
        }}
        onSubmit={editingTeam ? handleUpdate : handleCreate}
        team={editingTeam}
        isLoading={createTeam.isPending || updateTeam.isPending}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deletingTeam}
        onClose={() => setDeletingTeam(null)}
        onConfirm={handleDelete}
        title="Delete Team"
        message={`Are you sure you want to delete "${deletingTeam?.name}"? All team members will be removed.`}
        confirmLabel="Delete"
        variant="danger"
        isLoading={deleteTeam.isPending}
      />

      {/* Add Member Modal */}
      {addingMemberTo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Add Team Member</h3>
            <select
              value={selectedAgentId}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 mb-4"
            >
              <option value="">Select an agent...</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name} ({agent.slug})
                </option>
              ))}
            </select>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setAddingMemberTo(null);
                  setSelectedAgentId('');
                }}
                className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAddMember}
                disabled={!selectedAgentId || addMember.isPending}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50"
              >
                Add Member
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Remove Member Confirmation */}
      <ConfirmDialog
        isOpen={!!removingMember}
        onClose={() => setRemovingMember(null)}
        onConfirm={handleRemoveMember}
        title="Remove Team Member"
        message={`Are you sure you want to remove "${removingMember?.agentName}" from this team?`}
        confirmLabel="Remove"
        variant="warning"
        isLoading={removeMember.isPending}
      />
    </div>
  );
}
