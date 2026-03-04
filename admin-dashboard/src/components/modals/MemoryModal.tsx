import { User, Clock, Tag, Hash } from 'lucide-react';
import Modal from './Modal';
import { format } from 'date-fns';

interface Memory {
  id: string;
  agent_id: string;
  agent_name: string;
  content: string;
  memory_type: string;
  created_at: string;
  relevance_score?: number | null;
}

interface MemoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  memory: Memory | null;
}

export default function MemoryModal({ isOpen, onClose, memory }: MemoryModalProps) {
  if (!memory) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Memory Details" size="lg">
      <div className="space-y-4">
        {/* Metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2 text-sm">
            <User className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500">Agent:</span>
            <span className="font-medium">{memory.agent_name}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Tag className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500">Type:</span>
            <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded text-xs font-medium">
              {memory.memory_type}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Clock className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500">Created:</span>
            <span>{format(new Date(memory.created_at), 'PPpp')}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Hash className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500">ID:</span>
            <span className="font-mono text-xs">{memory.id.slice(0, 8)}...</span>
          </div>
        </div>

        {/* Content */}
        <div className="border-t pt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">Content</h4>
          <div className="bg-gray-50 rounded-lg p-4 text-gray-800 whitespace-pre-wrap max-h-96 overflow-y-auto">
            {memory.content}
          </div>
        </div>

        {/* Relevance score if present */}
        {memory.relevance_score !== null && memory.relevance_score !== undefined && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>Relevance Score:</span>
            <div className="flex-1 bg-gray-200 rounded-full h-2 max-w-xs">
              <div
                className="bg-indigo-600 h-2 rounded-full"
                style={{ width: `${Math.min(100, memory.relevance_score * 100)}%` }}
              />
            </div>
            <span className="font-medium">{(memory.relevance_score * 100).toFixed(1)}%</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end pt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}
