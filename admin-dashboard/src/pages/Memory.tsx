import { Search, Filter, Database, User, Clock } from 'lucide-react';
import { useState } from 'react';
import { useMemorySearch } from '../hooks/useApi';
import { format } from 'date-fns';

export default function Memory() {
  const [search, setSearch] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useMemorySearch(searchQuery, page);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(search);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Memory</h1>
        <p className="text-gray-600 mt-1">Browse and search stored memories</p>
      </div>

      <form onSubmit={handleSearch} className="flex items-center gap-4">
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
        <button
          type="submit"
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          Search
        </button>
        <button
          type="button"
          className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-gray-50"
        >
          <Filter className="w-4 h-4" />
          Filters
        </button>
      </form>

      <div className="bg-white rounded-xl shadow-sm border">
        {!searchQuery ? (
          <div className="text-center py-12 text-gray-500">
            <Database className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p>Enter a search query to find memories</p>
            <p className="text-sm mt-2">Search across all agent memories</p>
          </div>
        ) : isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500 mx-auto"></div>
            <p className="text-gray-500 mt-4">Searching...</p>
          </div>
        ) : error ? (
          <div className="text-center py-12 text-red-500">
            <p>Error: {error.message}</p>
          </div>
        ) : data?.items.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No memories found for "{searchQuery}"</p>
          </div>
        ) : (
          <>
            <div className="px-6 py-3 border-b bg-gray-50">
              <p className="text-sm text-gray-600">
                Found {data?.total} memories
              </p>
            </div>
            <div className="divide-y">
              {data?.items.map((memory) => (
                <div key={memory.id} className="p-6 hover:bg-gray-50">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
                        <User className="w-4 h-4" />
                        <span>{memory.agent_name}</span>
                        <span className="text-gray-300">|</span>
                        <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                          {memory.memory_type}
                        </span>
                      </div>
                      <p className="text-gray-900">{memory.content}</p>
                      <div className="flex items-center gap-2 text-xs text-gray-400 mt-2">
                        <Clock className="w-3 h-3" />
                        {format(new Date(memory.created_at), 'PPpp')}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {data && data.pages > 1 && (
              <div className="px-6 py-4 border-t flex items-center justify-between">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="text-sm text-gray-600">
                  Page {page} of {data.pages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(data.pages, p + 1))}
                  disabled={page === data.pages}
                  className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
