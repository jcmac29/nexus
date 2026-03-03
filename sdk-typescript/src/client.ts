/**
 * Main Nexus client
 */

import axios, { AxiosInstance } from 'axios';
import { Memory } from './memory';
import { Discovery } from './discovery';
import {
  MessagingClient,
  InvocationClient,
  WebhookClient,
  Invocation,
  PendingWork,
} from './messaging';
import { Agent, AgentCreateResponse, DiscoverResult } from './types';

export interface NexusConfig {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
}

export interface RegisterOptions {
  slug: string;
  name?: string;
  description?: string;
  metadata?: Record<string, unknown>;
  baseUrl?: string;
}

/**
 * Internal client wrapper for consistent API access.
 */
export class NexusClient {
  constructor(private axiosClient: AxiosInstance) {}

  async get<T>(path: string): Promise<T> {
    const response = await this.axiosClient.get<T>(path);
    return response.data;
  }

  async post<T>(path: string, data: Record<string, unknown>): Promise<T> {
    const response = await this.axiosClient.post<T>(path, data);
    return response.data;
  }

  async delete(path: string): Promise<void> {
    await this.axiosClient.delete(path);
  }
}

/**
 * Nexus client for connecting AI agents.
 *
 * @example
 * ```typescript
 * // Register a new agent
 * const nexus = await Nexus.register({
 *   slug: 'my-agent',
 *   name: 'My Agent Name'
 * });
 *
 * // Or connect with existing API key
 * const nexus = new Nexus({ apiKey: 'nex_xxx' });
 *
 * // Use memory
 * await nexus.memory.store('key', { data: 'value' });
 * const data = await nexus.memory.get('key');
 *
 * // Use discovery
 * await nexus.capabilities.register({
 *   name: 'translation',
 *   description: 'Translate text between languages'
 * });
 * const results = await nexus.discover({ query: 'translation' });
 *
 * // Invoke another agent's capability
 * const result = await nexus.invoke('agent-id', 'generate-image', {
 *   input: { prompt: 'a futuristic city' }
 * });
 *
 * // Send messages to other agents
 * await nexus.messages.send('agent-id', { text: 'Hello!' });
 * ```
 */
export class Nexus {
  private axiosClient: AxiosInstance;
  private client: NexusClient;
  private _memory: Memory;
  private _discovery: Discovery;
  private _messages: MessagingClient;
  private _invocations: InvocationClient;
  private _webhook: WebhookClient;

  constructor(config: NexusConfig) {
    const baseUrl = config.baseUrl || 'http://localhost:8000/api/v1';

    this.axiosClient = axios.create({
      baseURL: baseUrl,
      timeout: config.timeout || 30000,
      headers: {
        Authorization: `Bearer ${config.apiKey}`,
        'Content-Type': 'application/json',
      },
    });

    this.client = new NexusClient(this.axiosClient);
    this._memory = new Memory(this.axiosClient);
    this._discovery = new Discovery(this.axiosClient);
    this._messages = new MessagingClient(this.client);
    this._invocations = new InvocationClient(this.client);
    this._webhook = new WebhookClient(this.client);
  }

  /**
   * Register a new agent and return a connected client.
   */
  static async register(options: RegisterOptions): Promise<Nexus> {
    const baseUrl = options.baseUrl || 'http://localhost:8000/api/v1';

    const response = await axios.post<AgentCreateResponse>(
      `${baseUrl}/agents`,
      {
        slug: options.slug,
        name: options.name || options.slug,
        description: options.description,
        metadata: options.metadata || {},
      }
    );

    return new Nexus({
      apiKey: response.data.api_key,
      baseUrl,
    });
  }

  /**
   * Access memory operations.
   */
  get memory(): Memory {
    return this._memory;
  }

  /**
   * Access capability registration.
   */
  get capabilities(): Discovery {
    return this._discovery;
  }

  /**
   * Access messaging operations.
   */
  get messages(): MessagingClient {
    return this._messages;
  }

  /**
   * Access invocation operations.
   */
  get invocations(): InvocationClient {
    return this._invocations;
  }

  /**
   * Access webhook configuration.
   */
  get webhook(): WebhookClient {
    return this._webhook;
  }

  /**
   * Discover capabilities across all agents.
   */
  async discover(options?: {
    query?: string;
    name?: string;
    category?: string;
    tags?: string[];
    limit?: number;
  }): Promise<DiscoverResult[]> {
    return this._discovery.discover(options);
  }

  /**
   * Invoke a capability on another agent.
   *
   * @param agentId - Target agent's ID
   * @param capability - Name of the capability to invoke
   * @param options - Optional input data and settings
   */
  async invoke(
    agentId: string,
    capability: string,
    options?: {
      input?: Record<string, unknown>;
      timeoutSeconds?: number;
      asyncMode?: boolean;
    }
  ): Promise<Invocation> {
    return this._invocations.invoke(agentId, capability, options);
  }

  /**
   * Get pending work (invocations and messages) for this agent.
   */
  async pending(): Promise<PendingWork> {
    return this._invocations.pending();
  }

  /**
   * Complete an invocation with a result.
   *
   * @param invocationId - ID of the invocation to complete
   * @param result - Output data or error message
   */
  async complete(
    invocationId: string,
    result: {
      output?: Record<string, unknown>;
      error?: string;
    }
  ): Promise<Invocation> {
    return this._invocations.complete(invocationId, result);
  }

  /**
   * Get current agent info.
   */
  async me(): Promise<Agent> {
    const response = await this.axiosClient.get<Agent>('/agents/me');
    return response.data;
  }
}
