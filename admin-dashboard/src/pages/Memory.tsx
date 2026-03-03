import { Search, Filter } from 'lucide-react';
import { useState } from 'react';

export default function Memory() {
  const [search, setSearch] = useState('');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Memory</h1>
        <p className="text-gray-600 mt-1">Browse and search stored memories</p>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search memories..."
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

      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="text-center py-12 text-gray-500">
          <p>Enter a search query to find memories</p>
          <p className="text-sm mt-2">Semantic search across all agent memories</p>
        </div>
      </div>
    </div>
  );
}
