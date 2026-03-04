import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = '/api/v1';

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem('admin_token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...options?.headers,
    },
  });

  // Handle 401 - redirect to login
  if (response.status === 401) {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_refresh_token');
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }

  return response.json();
}

// Dashboard stats
export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => fetchApi<{
      total_agents: number;
      active_agents: number;
      total_memories: number;
      total_teams: number;
      total_capabilities: number;
      api_calls_today: number;
      api_calls_this_month: number;
    }>('/admin/stats'),
    refetchInterval: 30000,
  });
}

// Agents with pagination
export function useAgents(page = 1, pageSize = 20, search?: string) {
  return useQuery({
    queryKey: ['agents', page, pageSize, search],
    queryFn: () => fetchApi<{
      items: Array<{
        id: string;
        name: string;
        slug: string;
        status: string;
        capabilities_count: number;
        memories_count: number;
        created_at: string;
        last_seen: string | null;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(`/admin/agents?page=${page}&page_size=${pageSize}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  });
}

// Teams with pagination
export function useTeams(page = 1, pageSize = 20) {
  return useQuery({
    queryKey: ['teams', page, pageSize],
    queryFn: () => fetchApi<{
      items: Array<{
        id: string;
        name: string;
        slug: string;
        member_count: number;
        created_at: string;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(`/admin/teams?page=${page}&page_size=${pageSize}`),
  });
}

// Memory search
export function useMemorySearch(query: string, page = 1, pageSize = 20) {
  return useQuery({
    queryKey: ['memories', query, page, pageSize],
    queryFn: () => fetchApi<{
      items: Array<{
        id: string;
        agent_id: string;
        agent_name: string;
        content: string;
        memory_type: string;
        created_at: string;
        relevance_score: number | null;
      }>;
      total: number;
      page: number;
      page_size: number;
      pages: number;
    }>(`/admin/memories?q=${encodeURIComponent(query)}&page=${page}&page_size=${pageSize}`),
    enabled: query.length > 0,
  });
}

// Federation peers
export function useFederationPeers() {
  return useQuery({
    queryKey: ['federation-peers'],
    queryFn: () => fetchApi<Array<{
      id: string;
      name: string;
      url: string;
      trust_level: string;
      status: string;
      last_seen: string | null;
    }>>('/admin/federation/peers'),
  });
}

// Audit logs
export function useAuditLogs(limit = 50) {
  return useQuery({
    queryKey: ['audit-logs', limit],
    queryFn: () => fetchApi<Array<{
      id: string;
      action: string;
      resource_type: string;
      resource_id: string | null;
      agent_id: string | null;
      timestamp: string;
      details: Record<string, unknown>;
    }>>(`/admin/audit/logs?limit=${limit}`),
  });
}

// Recent activity
export function useRecentActivity(limit = 50) {
  return useQuery({
    queryKey: ['recent-activity', limit],
    queryFn: () => fetchApi<Array<{
      id: string;
      type: string;
      description: string;
      agent_id: string | null;
      agent_name: string | null;
      timestamp: string;
    }>>(`/admin/activity?limit=${limit}`),
    refetchInterval: 10000,
  });
}

// Instance settings
export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => fetchApi<{
      instance_name: string;
      allow_registration: boolean;
      require_email_verification: boolean;
      default_rate_limit: number;
      features: Record<string, boolean>;
    }>('/admin/settings'),
  });
}

// Update settings mutation
export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (updates: Partial<{
      instance_name: string;
      allow_registration: boolean;
      require_email_verification: boolean;
      default_rate_limit: number;
      features: Record<string, boolean>;
    }>) => fetchApi('/admin/settings', {
      method: 'PATCH',
      body: JSON.stringify(updates),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });
}

// ============================================================================
// Agent Mutations
// ============================================================================

export function useCreateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: {
      name: string;
      slug: string;
      description?: string;
      status?: string;
    }) => fetchApi('/admin/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}

export function useUpdateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, ...data }: {
      id: string;
      name?: string;
      description?: string;
      status?: string;
    }) => fetchApi(`/admin/agents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => fetchApi(`/admin/agents/${id}`, {
      method: 'DELETE',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}

// ============================================================================
// Team Mutations
// ============================================================================

export function useCreateTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: {
      name: string;
      slug: string;
      owner_agent_id: string;
      description?: string;
    }) => fetchApi('/admin/teams', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}

export function useUpdateTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, ...data }: {
      id: string;
      name?: string;
      description?: string;
    }) => fetchApi(`/admin/teams/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
}

export function useDeleteTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => fetchApi(`/admin/teams/${id}`, {
      method: 'DELETE',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}

export function useAddTeamMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ teamId, agentId, role = 'member' }: {
      teamId: string;
      agentId: string;
      role?: string;
    }) => fetchApi(`/admin/teams/${teamId}/members`, {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, role }),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
}

export function useRemoveTeamMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ teamId, agentId }: {
      teamId: string;
      agentId: string;
    }) => fetchApi(`/admin/teams/${teamId}/members/${agentId}`, {
      method: 'DELETE',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
}

// ============================================================================
// Memory Mutations
// ============================================================================

export function useDeleteMemory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => fetchApi(`/admin/memories/${id}`, {
      method: 'DELETE',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}

export function useBulkDeleteMemories() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ids: string[]) => fetchApi<{ deleted: number }>('/admin/memories/bulk-delete', {
      method: 'POST',
      body: JSON.stringify(ids),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}
