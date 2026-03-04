import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import Modal from './Modal';
import { useAgents } from '../../hooks/useApi';

interface Team {
  id?: string;
  name: string;
  slug: string;
  description?: string;
  owner_agent_id?: string;
}

interface TeamModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { name: string; slug: string; description?: string; owner_agent_id?: string }) => Promise<void>;
  team?: Team | null;
  isLoading?: boolean;
}

export default function TeamModal({
  isOpen,
  onClose,
  onSubmit,
  team,
  isLoading = false,
}: TeamModalProps) {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [ownerAgentId, setOwnerAgentId] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  const { data: agentsData } = useAgents(1, 100);
  const agents = agentsData?.items ?? [];

  const isEditing = !!team;

  useEffect(() => {
    if (team) {
      setName(team.name);
      setSlug(team.slug);
      setDescription(team.description || '');
      setOwnerAgentId(team.owner_agent_id || '');
    } else {
      setName('');
      setSlug('');
      setDescription('');
      setOwnerAgentId(agents[0]?.id || '');
    }
    setErrors({});
  }, [team, isOpen, agents]);

  // Auto-generate slug from name
  const handleNameChange = (value: string) => {
    setName(value);
    if (!isEditing && !slug) {
      setSlug(value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''));
    }
  };

  const validate = () => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (!slug.trim()) {
      newErrors.slug = 'Slug is required';
    } else if (!/^[a-z0-9-]+$/.test(slug)) {
      newErrors.slug = 'Slug must contain only lowercase letters, numbers, and hyphens';
    }

    if (!isEditing && !ownerAgentId) {
      newErrors.owner = 'Owner agent is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    const data: { name: string; slug: string; description?: string; owner_agent_id?: string } = {
      name: name.trim(),
      slug: slug.trim(),
      description: description.trim() || undefined,
    };

    if (!isEditing) {
      data.owner_agent_id = ownerAgentId;
    }

    await onSubmit(data);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Team' : 'Create Team'}
      size="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Name */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
            Team Name
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 ${
              errors.name ? 'border-red-500' : 'border-gray-300'
            }`}
            placeholder="Engineering Team"
          />
          {errors.name && <p className="mt-1 text-sm text-red-500">{errors.name}</p>}
        </div>

        {/* Slug */}
        <div>
          <label htmlFor="slug" className="block text-sm font-medium text-gray-700 mb-1">
            Slug
          </label>
          <input
            id="slug"
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase())}
            disabled={isEditing}
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 ${
              errors.slug ? 'border-red-500' : 'border-gray-300'
            } ${isEditing ? 'bg-gray-100 cursor-not-allowed' : ''}`}
            placeholder="engineering-team"
          />
          {errors.slug && <p className="mt-1 text-sm text-red-500">{errors.slug}</p>}
        </div>

        {/* Owner Agent (only for create) */}
        {!isEditing && (
          <div>
            <label htmlFor="owner" className="block text-sm font-medium text-gray-700 mb-1">
              Owner Agent
            </label>
            <select
              id="owner"
              value={ownerAgentId}
              onChange={(e) => setOwnerAgentId(e.target.value)}
              className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 ${
                errors.owner ? 'border-red-500' : 'border-gray-300'
              }`}
            >
              <option value="">Select an agent...</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name} ({agent.slug})
                </option>
              ))}
            </select>
            {errors.owner && <p className="mt-1 text-sm text-red-500">{errors.owner}</p>}
            <p className="mt-1 text-xs text-gray-500">
              The agent that will own and manage this team.
            </p>
          </div>
        )}

        {/* Description */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
            Description <span className="text-gray-400">(optional)</span>
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            placeholder="Describe the team's purpose..."
          />
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isLoading}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            {isEditing ? 'Save Changes' : 'Create Team'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
