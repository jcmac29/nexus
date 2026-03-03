import { Download, Filter, Search } from 'lucide-react';
import { useState } from 'react';
import DataTable from '../components/DataTable';
import { useAuditLogs } from '../hooks/useApi';

export default function AuditLogs() {
  const [search, setSearch] = useState('');
  const { data: logs, isLoading } = useAuditLogs(100);

  const filteredLogs = (logs ?? []).filter(
    (log) =>
      log.action.toLowerCase().includes(search.toLowerCase()) ||
      log.resource_type.toLowerCase().includes(search.toLowerCase())
  );

  const columns = [
    {
      key: 'timestamp',
      header: 'Time',
      render: (log: NonNullable<typeof logs>[0]) =>
        new Date(log.timestamp).toLocaleString(),
    },
    {
      key: 'action',
      header: 'Action',
      render: (log: NonNullable<typeof logs>[0]) => (
        <span className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">
          {log.action}
        </span>
      ),
    },
    { key: 'resource_type', header: 'Resource' },
    {
      key: 'resource_id',
      header: 'Resource ID',
      render: (log: NonNullable<typeof logs>[0]) => (
        <span className="font-mono text-xs text-gray-600">
          {log.resource_id?.slice(0, 8)}...
        </span>
      ),
    },
    {
      key: 'agent_id',
      header: 'Agent',
      render: (log: NonNullable<typeof logs>[0]) => (
        <span className="font-mono text-xs text-gray-600">
          {log.agent_id?.slice(0, 8)}...
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
          <p className="text-gray-600 mt-1">Track all system activity</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-gray-50">
          <Download className="w-4 h-4" />
          Export
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search logs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <button className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-gray-50">
          <Filter className="w-4 h-4" />
          Filters
        </button>
      </div>

      <DataTable columns={columns} data={filteredLogs} loading={isLoading} />
    </div>
  );
}
