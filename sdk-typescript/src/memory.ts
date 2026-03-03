/**
 * Memory operations for Nexus SDK
 */

import { AxiosInstance } from 'axios';
import { MemoryData, MemorySearchResult, MemorySearchResponse, MemoryShare } from './types';

export interface MemoryStoreOptions {
  key: string;
  value: Record<string, unknown>;
  namespace?: string;
  scope?: 'agent' | 'user' | 'session' | 'shared';
  userId?: string;
  sessionId?: string;
  tags?: string[];
  textContent?: string;
  expiresInSeconds?: number;
}

export interface MemoryGetOptions {
  namespace?: string;
  userId?: string;
  sessionId?: string;
}

export interface MemorySearchOptions {
  query: string;
  namespace?: string;
  userId?: string;
  sessionId?: string;
  tags?: string[];
  limit?: number;
  includeShared?: boolean;
}

export interface MemoryListOptions {
  namespace?: string;
  userId?: string;
  sessionId?: string;
  tags?: string[];
  limit?: number;
  offset?: number;
}

/**
 * Memory operations for storing and retrieving agent memories.
 */
export class Memory {
  constructor(private client: AxiosInstance) {}

  /**
   * Store a memory.
   */
  async store(options: MemoryStoreOptions): Promise<MemoryData>;
  async store(key: string, value: Record<string, unknown>): Promise<MemoryData>;
  async store(
    keyOrOptions: string | MemoryStoreOptions,
    value?: Record<string, unknown>
  ): Promise<MemoryData> {
    const options: MemoryStoreOptions =
      typeof keyOrOptions === 'string'
        ? { key: keyOrOptions, value: value! }
        : keyOrOptions;

    const response = await this.client.post<MemoryData>('/memory', {
      key: options.key,
      value: options.value,
      namespace: options.namespace || 'default',
      scope: options.scope || 'agent',
      user_id: options.userId,
      session_id: options.sessionId,
      tags: options.tags || [],
      text_content: options.textContent,
      expires_in_seconds: options.expiresInSeconds,
    });

    return response.data;
  }

  /**
   * Get a memory by key.
   */
  async get(key: string, options?: MemoryGetOptions): Promise<MemoryData | null> {
    try {
      const response = await this.client.get<MemoryData>(`/memory/${key}`, {
        params: {
          namespace: options?.namespace || 'default',
          user_id: options?.userId,
          session_id: options?.sessionId,
        },
      });
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  /**
   * Search memories semantically.
   */
  async search(options: MemorySearchOptions): Promise<MemorySearchResult[]> {
    const response = await this.client.post<MemorySearchResponse>('/memory/search', {
      query: options.query,
      namespace: options.namespace,
      user_id: options.userId,
      session_id: options.sessionId,
      tags: options.tags,
      limit: options.limit || 10,
      include_shared: options.includeShared ?? true,
    });

    return response.data.results;
  }

  /**
   * List memories with filters.
   */
  async list(options?: MemoryListOptions): Promise<MemoryData[]> {
    const response = await this.client.get<MemoryData[]>('/memory', {
      params: {
        namespace: options?.namespace,
        user_id: options?.userId,
        session_id: options?.sessionId,
        tags: options?.tags,
        limit: options?.limit || 50,
        offset: options?.offset || 0,
      },
    });

    return response.data;
  }

  /**
   * Delete a memory by key.
   */
  async delete(key: string, namespace?: string): Promise<boolean> {
    try {
      await this.client.delete(`/memory/${key}`, {
        params: { namespace: namespace || 'default' },
      });
      return true;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return false;
      }
      throw error;
    }
  }

  /**
   * Share a memory with another agent.
   */
  async share(
    memoryId: string,
    agentId: string,
    permissions?: string[]
  ): Promise<MemoryShare> {
    const response = await this.client.post<MemoryShare>(
      `/memory/${memoryId}/share`,
      {
        agent_id: agentId,
        permissions: permissions || ['read'],
      }
    );

    return response.data;
  }
}
