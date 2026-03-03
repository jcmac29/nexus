import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = '/api/v1';

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

// Dashboard stats
export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => fetchApi<{
      agents: number;
      memories: number;
      teams: number;
      invocations: number;
      federation_peers: number;
    }>('/admin/stats'),
    refetchInterval: 30000,
  });
}

// Agents
export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: () => fetchApi<Array<{
      id: string;
      name: string;
      slug: string;
      status: string;
      created_at: string;
    }>>('/admin/agents'),
  });
}

// Teams
export function useTeams() {
  return useQuery({
    queryKey: ['teams'],
    queryFn: () => fetchApi<Array<{
      id: string;
      name: string;
      member_count: number;
      created_at: string;
    }>>('/admin/teams'),
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
      last_seen: string;
    }>>('/federation/peers'),
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
      resource_id: string;
      agent_id: string;
      timestamp: string;
      details: Record<string, unknown>;
    }>>(`/audit/logs?limit=${limit}`),
  });
}

// Recent activity
export function useRecentActivity() {
  return useQuery({
    queryKey: ['recent-activity'],
    queryFn: () => fetchApi<Array<{
      id: string;
      type: string;
      description: string;
      timestamp: string;
    }>>('/admin/activity'),
    refetchInterval: 10000,
  });
}
