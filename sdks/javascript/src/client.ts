/**
 * Nexus JavaScript SDK Client
 */

import {
  Agent,
  Memory,
  Capability,
  Invocation,
  Message,
  SearchResult,
  StoreMemoryOptions,
  SearchMemoryOptions,
  InvokeOptions,
  SendMessageOptions,
} from './types.js';

export interface NexusClientOptions {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
}

export class NexusClient {
  private baseUrl: string;
  private apiKey: string;
  private timeout: number;

  constructor(options: NexusClientOptions) {
    this.baseUrl = (options.baseUrl ?? 'http://localhost:8000').replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.timeout = options.timeout ?? 30000;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: Record<string, unknown>
  ): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Nexus API error: ${response.status} - ${error}`);
      }

      return response.json();
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // --- Identity ---

  async whoami(): Promise<Agent> {
    const data = await this.request<Record<string, unknown>>('GET', '/api/v1/agents/me');
    return {
      id: data.id as string,
      name: data.name as string,
      slug: data.slug as string,
      description: data.description as string | undefined,
    };
  }

  // --- Memory ---

  async storeMemory(options: StoreMemoryOptions): Promise<Memory> {
    const data = await this.request<Record<string, unknown>>('POST', '/api/v1/memory', {
      key: options.key,
      value: options.value,
      text_content: options.textContent ?? JSON.stringify(options.value),
      tags: options.tags ?? [],
      scope: options.scope ?? 'agent',
    });

    return {
      id: data.id as string,
      key: data.key as string,
      value: data.value as Record<string, unknown>,
      tags: (data.tags as string[]) ?? [],
    };
  }

  async searchMemory(options: SearchMemoryOptions): Promise<SearchResult[]> {
    const data = await this.request<{ results: Array<{ memory: Record<string, unknown>; score: number }> }>(
      'POST',
      '/api/v1/memory/search',
      {
        query: options.query,
        limit: options.limit ?? 10,
        include_shared: options.includeShared ?? true,
      }
    );

    return (data.results ?? []).map(r => ({
      memory: {
        id: r.memory.id as string,
        key: r.memory.key as string,
        value: r.memory.value as Record<string, unknown>,
        tags: (r.memory.tags as string[]) ?? [],
      },
      score: r.score,
    }));
  }

  async getMemory(memoryId: string): Promise<Memory> {
    const data = await this.request<Record<string, unknown>>('GET', `/api/v1/memory/${memoryId}`);
    return {
      id: data.id as string,
      key: data.key as string,
      value: data.value as Record<string, unknown>,
      tags: (data.tags as string[]) ?? [],
    };
  }

  // --- Capabilities ---

  async registerCapability(
    name: string,
    description: string,
    inputSchema?: Record<string, unknown>
  ): Promise<Capability> {
    const data = await this.request<Record<string, unknown>>('POST', '/api/v1/capabilities', {
      name,
      description,
      input_schema: inputSchema ?? {},
    });

    return {
      name: data.name as string,
      description: data.description as string | undefined,
      inputSchema: data.input_schema as Record<string, unknown> | undefined,
    };
  }

  async discoverAgents(capability: string): Promise<Agent[]> {
    const data = await this.request<{ agents: Array<Record<string, unknown>> }>(
      'GET',
      `/api/v1/discover/capabilities/${capability}`
    );

    return (data.agents ?? []).map(a => ({
      id: a.id as string,
      name: a.name as string,
      slug: a.slug as string,
      description: a.description as string | undefined,
    }));
  }

  // --- Invocations ---

  async invoke(options: InvokeOptions): Promise<Invocation> {
    const data = await this.request<Record<string, unknown>>(
      'POST',
      `/api/v1/invoke/${options.agentId}/${options.capability}`,
      { input: options.input }
    );

    let invocation: Invocation = {
      id: (data.invocation_id ?? data.id) as string,
      status: data.status as Invocation['status'],
      output: data.output as Record<string, unknown> | undefined,
    };

    if (options.wait && invocation.status === 'pending') {
      // Poll for completion
      for (let i = 0; i < 60; i++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const status = await this.getInvocation(invocation.id);
        if (status.status === 'completed' || status.status === 'failed') {
          return status;
        }
      }
    }

    return invocation;
  }

  async getInvocation(invocationId: string): Promise<Invocation> {
    const data = await this.request<Record<string, unknown>>('GET', `/api/v1/invocations/${invocationId}`);
    return {
      id: data.id as string,
      status: data.status as Invocation['status'],
      output: data.output as Record<string, unknown> | undefined,
    };
  }

  async getPendingWork(): Promise<Invocation[]> {
    const data = await this.request<Array<Record<string, unknown>>>('GET', '/api/v1/agents/me/pending');
    return data.map(i => ({
      id: i.id as string,
      status: 'pending' as const,
      output: undefined,
    }));
  }

  async completeInvocation(
    invocationId: string,
    output: Record<string, unknown>,
    success: boolean = true
  ): Promise<void> {
    await this.request('POST', `/api/v1/invocations/${invocationId}/complete`, {
      output,
      success,
    });
  }

  // --- Messaging ---

  async sendMessage(options: SendMessageOptions): Promise<Message> {
    const data = await this.request<Record<string, unknown>>('POST', '/api/v1/messages', {
      to_agent_id: options.toAgentId,
      subject: options.subject,
      body: options.body,
    });

    return {
      id: data.id as string,
      fromAgentId: data.from_agent_id as string,
      subject: data.subject as string,
      body: data.body as string,
    };
  }

  async getInbox(unreadOnly: boolean = false): Promise<Message[]> {
    const params = unreadOnly ? '?unread=true' : '';
    const data = await this.request<Array<Record<string, unknown>>>('GET', `/api/v1/messages/inbox${params}`);

    return data.map(m => ({
      id: m.id as string,
      fromAgentId: m.from_agent_id as string,
      subject: m.subject as string,
      body: m.body as string,
    }));
  }

  // --- Health ---

  async heartbeat(status: string = 'healthy'): Promise<void> {
    await this.request('POST', '/api/v1/health/heartbeat', { status });
  }
}
