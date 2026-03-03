/**
 * Discovery operations for Nexus SDK
 */

import { AxiosInstance } from 'axios';
import { Capability, DiscoverResult, DiscoverResponse } from './types';

export interface CapabilityOptions {
  name: string;
  description?: string;
  category?: string;
  tags?: string[];
  endpointUrl?: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface CapabilityUpdateOptions {
  description?: string;
  category?: string;
  tags?: string[];
  endpointUrl?: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  status?: 'active' | 'inactive' | 'deprecated';
}

export interface DiscoverOptions {
  query?: string;
  name?: string;
  category?: string;
  tags?: string[];
  limit?: number;
}

export interface AgentCapabilities {
  agent_id: string;
  agent_name: string;
  agent_slug: string;
  capabilities: Capability[];
}

/**
 * Discovery operations for registering and finding capabilities.
 */
export class Discovery {
  constructor(private client: AxiosInstance) {}

  /**
   * Register a capability for your agent.
   */
  async register(options: CapabilityOptions): Promise<Capability> {
    const response = await this.client.post<Capability>('/capabilities', {
      name: options.name,
      description: options.description,
      category: options.category,
      tags: options.tags || [],
      endpoint_url: options.endpointUrl,
      input_schema: options.inputSchema,
      output_schema: options.outputSchema,
      metadata: options.metadata || {},
    });

    return response.data;
  }

  /**
   * List your agent's capabilities.
   */
  async list(): Promise<Capability[]> {
    const response = await this.client.get<Capability[]>('/capabilities');
    return response.data;
  }

  /**
   * Update a capability.
   */
  async update(name: string, options: CapabilityUpdateOptions): Promise<Capability> {
    const response = await this.client.patch<Capability>(`/capabilities/${name}`, {
      description: options.description,
      category: options.category,
      tags: options.tags,
      endpoint_url: options.endpointUrl,
      input_schema: options.inputSchema,
      output_schema: options.outputSchema,
      metadata: options.metadata,
      status: options.status,
    });

    return response.data;
  }

  /**
   * Delete a capability.
   */
  async delete(name: string): Promise<boolean> {
    try {
      await this.client.delete(`/capabilities/${name}`);
      return true;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return false;
      }
      throw error;
    }
  }

  /**
   * Discover capabilities across all agents.
   */
  async discover(options?: DiscoverOptions): Promise<DiscoverResult[]> {
    const response = await this.client.get<DiscoverResponse>('/discover', {
      params: {
        query: options?.query,
        name: options?.name,
        category: options?.category,
        tags: options?.tags,
        limit: options?.limit || 20,
      },
    });

    return response.data.results;
  }

  /**
   * Get an agent's capabilities.
   */
  async getAgent(agentId: string): Promise<AgentCapabilities> {
    const response = await this.client.get<AgentCapabilities>(
      `/discover/agents/${agentId}`
    );
    return response.data;
  }
}
