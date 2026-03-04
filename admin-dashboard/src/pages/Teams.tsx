import { Plus, Users } from 'lucide-react';
import DataTable from '../components/DataTable';
import { useTeams } from '../hooks/useApi';

export default function Teams() {
  const { data, isLoading } = useTeams();
  const teams = data?.items ?? [];

  const columns = [
    { key: 'name', header: 'Team Name' },
    {
      key: 'member_count',
      header: 'Members',
      render: (team: NonNullable<typeof teams>[0]) => (
        <span className="flex items-center gap-1">
          <Users className="w-4 h-4 text-gray-400" />
          {team.member_count}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (team: NonNullable<typeof teams>[0]) =>
        new Date(team.created_at).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: () => (
        <div className="flex items-center gap-2">
          <button className="text-indigo-600 hover:text-indigo-800 text-sm font-medium">
            View
          </button>
          <button className="text-gray-600 hover:text-gray-800 text-sm font-medium">
            Edit
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Teams</h1>
          <p className="text-gray-600 mt-1">Manage team collaborations</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" />
          Create Team
        </button>
      </div>

      <DataTable columns={columns} data={teams} loading={isLoading} />
    </div>
  );
}
