/**
 * Nexus SDK Types
 */

export interface Agent {
  id: string;
  name: string;
  slug: string;
  description?: string;
}

export interface Memory {
  id: string;
  key: string;
  value: Record<string, unknown>;
  tags: string[];
}

export interface Capability {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

export interface Invocation {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  output?: Record<string, unknown>;
}

export interface Message {
  id: string;
  fromAgentId: string;
  subject: string;
  body: string;
}

export interface SearchResult {
  memory: Memory;
  score: number;
}

export interface StoreMemoryOptions {
  key: string;
  value: Record<string, unknown>;
  textContent?: string;
  tags?: string[];
  scope?: 'agent' | 'team' | 'shared';
}

export interface SearchMemoryOptions {
  query: string;
  limit?: number;
  includeShared?: boolean;
}

export interface InvokeOptions {
  agentId: string;
  capability: string;
  input: Record<string, unknown>;
  wait?: boolean;
}

export interface SendMessageOptions {
  toAgentId: string;
  subject: string;
  body: string;
}
