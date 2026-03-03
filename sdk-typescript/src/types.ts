/**
 * Shared types for Nexus SDK
 */

export interface Agent {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  metadata: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AgentCreateResponse {
  agent: Agent;
  api_key: string;
}

export interface MemoryData {
  id: string;
  key: string;
  value: Record<string, unknown>;
  namespace: string;
  scope: string;
  user_id: string | null;
  session_id: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export interface MemorySearchResult {
  memory: MemoryData;
  score: number;
  owner_agent_id: string | null;
}

export interface MemorySearchResponse {
  results: MemorySearchResult[];
  total: number;
}

export interface Capability {
  id: string;
  agent_id: string;
  name: string;
  description: string | null;
  category: string | null;
  tags: string[];
  endpoint_url: string | null;
  input_schema: Record<string, unknown> | null;
  output_schema: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface DiscoverResult {
  agent_id: string;
  agent_name: string;
  agent_slug: string;
  capability: Capability;
  score: number | null;
}

export interface DiscoverResponse {
  results: DiscoverResult[];
  total: number;
}

export interface MemoryShare {
  id: string;
  memory_id: string;
  shared_with_agent_id: string;
  permissions: string[];
  created_at: string;
}
