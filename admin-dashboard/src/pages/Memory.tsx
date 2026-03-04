import { Search, Database, User, Clock, Trash2, Eye, CheckSquare, Square } from 'lucide-react';
import { useState } from 'react';
import { useMemorySearch, useDeleteMemory, useBulkDeleteMemories } from '../hooks/useApi';
import { format } from 'date-fns';
import Pagination from '../components/Pagination';
import EmptyState from '../components/EmptyState';
import MemoryModal from '../components/modals/MemoryModal';
import { ConfirmDialog } from '../components/modals';
import { useToast } from '../components/Toast';

interface Memory {
  id: string;
  agent_id: string;
  agent_name: string;
  content: string;
  memory_type: string;
  created_at: string;
  relevance_score?: number | null;
}

export default function Memory() {
  const [search, setSearch] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [deletingMemory, setDeletingMemory] = useState<Memory | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showBulkDelete, setShowBulkDelete] = useState(false);

  const { data, isLoading, error } = useMemorySearch(searchQuery, page);
  const deleteMemory = useDeleteMemory();
  const bulkDelete = useBulkDeleteMemories();
  const { showToast } = useToast();

  const memories = data?.items ?? [];
  const totalPages = data?.pages ?? 1;
  const totalItems = data?.total ?? 0;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(search);
    setPage(1);
    setSelectedIds(new Set());
  };

  const handleDelete = async () => {
    if (!deletingMemory) return;
    try {
      await deleteMemory.mutateAsync(deletingMemory.id);
      showToast('success', 'Memory deleted successfully');
      setDeletingMemory(null);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to delete memory');
    }
  };

  const handleBulkDelete = async () => {
    try {
      const result = await bulkDelete.mutateAsync(Array.from(selectedIds));
      showToast('success', `Deleted ${result.deleted} memories`);
      setSelectedIds(new Set());
      setShowBulkDelete(false);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Failed to delete memories');
    }
  };

  const toggleSelect = (id: string) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === memories.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(memories.map((m) => m.id)));
    }
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
      </form>

      {/* Bulk actions bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-4 p-3 bg-indigo-50 rounded-lg border border-indigo-200">
          <span className="text-sm font-medium text-indigo-700">
            {selectedIds.size} selected
          </span>
          <button
            onClick={() => setShowBulkDelete(true)}
            className="flex items-center gap-1 px-3 py-1 text-sm text-red-600 hover:bg-red-50 rounded transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Delete Selected
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded transition-colors"
          >
            Clear Selection
          </button>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border">
        {!searchQuery ? (
          <EmptyState
            icon="search"
            title="Search Memories"
            description="Enter a search query to find memories across all agents."
          />
        ) : isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500 mx-auto"></div>
            <p className="text-gray-500 mt-4">Searching...</p>
          </div>
        ) : error ? (
          <div className="text-center py-12 text-red-500">
            <p>Error: {error.message}</p>
          </div>
        ) : memories.length === 0 ? (
          <EmptyState
            icon="brain"
            title="No memories found"
            description={`No memories match "${searchQuery}". Try a different search term.`}
          />
        ) : (
          <>
            <div className="px-6 py-3 border-b bg-gray-50 flex items-center justify-between">
              <p className="text-sm text-gray-600">
                Found {totalItems} memories
              </p>
              <button
                onClick={toggleSelectAll}
                className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
              >
                {selectedIds.size === memories.length ? (
                  <CheckSquare className="w-4 h-4" />
                ) : (
                  <Square className="w-4 h-4" />
                )}
                Select All
              </button>
            </div>
            <div className="divide-y">
              {memories.map((memory) => (
                <div
                  key={memory.id}
                  className={`p-6 hover:bg-gray-50 transition-colors ${
                    selectedIds.has(memory.id) ? 'bg-indigo-50' : ''
                  }`}
                >
                  <div className="flex items-start gap-4">
                    {/* Checkbox */}
                    <button
                      onClick={() => toggleSelect(memory.id)}
                      className="mt-1 text-gray-400 hover:text-indigo-600"
                    >
                      {selectedIds.has(memory.id) ? (
                        <CheckSquare className="w-5 h-5 text-indigo-600" />
                      ) : (
                        <Square className="w-5 h-5" />
                      )}
                    </button>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
                        <User className="w-4 h-4" />
                        <span>{memory.agent_name}</span>
                        <span className="text-gray-300">|</span>
                        <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                          {memory.memory_type}
                        </span>
                      </div>
                      <p className="text-gray-900 line-clamp-3">{memory.content}</p>
                      <div className="flex items-center gap-2 text-xs text-gray-400 mt-2">
                        <Clock className="w-3 h-3" />
                        {format(new Date(memory.created_at), 'PPpp')}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setSelectedMemory(memory)}
                        className="p-2 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                        title="View Details"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setDeletingMemory(memory)}
                        className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              totalItems={totalItems}
              pageSize={20}
              onPageChange={setPage}
            />
          </>
        )}
      </div>

      {/* Memory Detail Modal */}
      <MemoryModal
        isOpen={!!selectedMemory}
        onClose={() => setSelectedMemory(null)}
        memory={selectedMemory}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deletingMemory}
        onClose={() => setDeletingMemory(null)}
        onConfirm={handleDelete}
        title="Delete Memory"
        message="Are you sure you want to delete this memory? This action cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        isLoading={deleteMemory.isPending}
      />

      {/* Bulk Delete Confirmation */}
      <ConfirmDialog
        isOpen={showBulkDelete}
        onClose={() => setShowBulkDelete(false)}
        onConfirm={handleBulkDelete}
        title="Delete Selected Memories"
        message={`Are you sure you want to delete ${selectedIds.size} memories? This action cannot be undone.`}
        confirmLabel={`Delete ${selectedIds.size} Memories`}
        variant="danger"
        isLoading={bulkDelete.isPending}
      />
    </div>
  );
}
