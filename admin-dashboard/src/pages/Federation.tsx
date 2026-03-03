import { Plus, Globe, Shield, RefreshCw } from 'lucide-react';
import DataTable from '../components/DataTable';
import { useFederationPeers } from '../hooks/useApi';

export default function Federation() {
  const { data: peers, isLoading, refetch } = useFederationPeers();

  const columns = [
    {
      key: 'name',
      header: 'Peer Name',
      render: (peer: NonNullable<typeof peers>[0]) => (
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-indigo-600" />
          <span className="font-medium">{peer.name}</span>
        </div>
      ),
    },
    { key: 'url', header: 'URL' },
    {
      key: 'trust_level',
      header: 'Trust Level',
      render: (peer: NonNullable<typeof peers>[0]) => (
        <span
          className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
            peer.trust_level === 'full'
              ? 'bg-green-100 text-green-800'
              : peer.trust_level === 'verified'
              ? 'bg-blue-100 text-blue-800'
              : 'bg-gray-100 text-gray-800'
          }`}
        >
          <Shield className="w-3 h-3" />
          {peer.trust_level}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (peer: NonNullable<typeof peers>[0]) => (
        <span
          className={`px-2 py-1 rounded-full text-xs font-medium ${
            peer.status === 'active'
              ? 'bg-green-100 text-green-800'
              : 'bg-red-100 text-red-800'
          }`}
        >
          {peer.status}
        </span>
      ),
    },
    {
      key: 'last_seen',
      header: 'Last Seen',
      render: (peer: NonNullable<typeof peers>[0]) =>
        peer.last_seen ? new Date(peer.last_seen).toLocaleString() : 'Never',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Federation</h1>
          <p className="text-gray-600 mt-1">Connected Nexus instances</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
            <Plus className="w-4 h-4" />
            Add Peer
          </button>
        </div>
      </div>

      <DataTable columns={columns} data={peers ?? []} loading={isLoading} />

      {!isLoading && (!peers || peers.length === 0) && (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <Globe className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900">No Federation Peers</h3>
          <p className="text-gray-500 mt-2">
            Connect to other Nexus instances to enable cross-instance agent collaboration.
          </p>
        </div>
      )}
    </div>
  );
}
