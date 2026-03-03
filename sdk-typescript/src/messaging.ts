/**
 * Messaging and invocation functionality for Nexus SDK.
 */

import { NexusClient } from './client';

export interface Message {
  id: string;
  from_agent_id: string;
  to_agent_id: string;
  subject?: string;
  content: Record<string, unknown>;
  reply_to_id?: string;
  status: string;
  created_at: string;
  read_at?: string;
}

export interface MessageList {
  messages: Message[];
  total: number;
}

export interface Invocation {
  id: string;
  caller_agent_id: string;
  target_agent_id: string;
  capability_id: string;
  capability_name?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'timeout';
  input_data: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface InvocationList {
  invocations: Invocation[];
  total: number;
}

export interface PendingInvocation {
  id: string;
  caller_agent_id: string;
  caller_agent_name?: string;
  capability_name: string;
  input_data: Record<string, unknown>;
  created_at: string;
  timeout_seconds: number;
}

export interface PendingWork {
  invocations: PendingInvocation[];
  messages: Message[];
}

export interface WebhookConfig {
  endpoint_url: string;
  events: string[];
  active: boolean;
}

/**
 * Client for agent-to-agent messaging.
 */
export class MessagingClient {
  constructor(private client: NexusClient) {}

  /**
   * Send a message to another agent.
   */
  async send(
    toAgentId: string,
    content: Record<string, unknown>,
    options?: {
      subject?: string;
      replyToId?: string;
    }
  ): Promise<Message> {
    const data: Record<string, unknown> = {
      to_agent_id: toAgentId,
      content,
    };
    if (options?.subject) data.subject = options.subject;
    if (options?.replyToId) data.reply_to_id = options.replyToId;

    return this.client.post<Message>('/messages', data);
  }

  /**
   * Get messages received by this agent.
   */
  async inbox(options?: {
    unreadOnly?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<MessageList> {
    const params = new URLSearchParams({
      inbox: 'true',
      unread_only: String(options?.unreadOnly ?? false),
      limit: String(options?.limit ?? 50),
      offset: String(options?.offset ?? 0),
    });
    return this.client.get<MessageList>(`/messages?${params}`);
  }

  /**
   * Get messages sent by this agent.
   */
  async sent(options?: { limit?: number; offset?: number }): Promise<MessageList> {
    const params = new URLSearchParams({
      inbox: 'false',
      limit: String(options?.limit ?? 50),
      offset: String(options?.offset ?? 0),
    });
    return this.client.get<MessageList>(`/messages?${params}`);
  }

  /**
   * Mark a message as read.
   */
  async markRead(messageId: string): Promise<Message> {
    return this.client.post<Message>(`/messages/${messageId}/read`, {});
  }
}

/**
 * Client for invoking capabilities on other agents.
 */
export class InvocationClient {
  constructor(private client: NexusClient) {}

  /**
   * Invoke a capability on another agent.
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
    const data = {
      input: options?.input ?? {},
      timeout_seconds: options?.timeoutSeconds ?? 30,
      async_mode: options?.asyncMode ?? false,
    };
    return this.client.post<Invocation>(`/invoke/${agentId}/${capability}`, data);
  }

  /**
   * Get an invocation by ID.
   */
  async get(invocationId: string): Promise<Invocation> {
    return this.client.get<Invocation>(`/invocations/${invocationId}`);
  }

  /**
   * List invocations for this agent.
   */
  async list(options?: {
    asCaller?: boolean;
    status?: string;
    limit?: number;
  }): Promise<InvocationList> {
    const params = new URLSearchParams({
      as_caller: String(options?.asCaller ?? true),
      limit: String(options?.limit ?? 50),
    });
    if (options?.status) params.set('status', options.status);
    return this.client.get<InvocationList>(`/invocations?${params}`);
  }

  /**
   * Get pending work for this agent (invocations and messages).
   */
  async pending(): Promise<PendingWork> {
    return this.client.get<PendingWork>('/agents/me/pending');
  }

  /**
   * Complete an invocation with a result.
   */
  async complete(
    invocationId: string,
    result: {
      output?: Record<string, unknown>;
      error?: string;
    }
  ): Promise<Invocation> {
    const data: Record<string, unknown> = {};
    if (result.output !== undefined) data.output = result.output;
    if (result.error !== undefined) data.error = result.error;
    return this.client.post<Invocation>(`/invocations/${invocationId}/complete`, data);
  }
}

/**
 * Client for managing webhooks.
 */
export class WebhookClient {
  constructor(private client: NexusClient) {}

  /**
   * Configure webhook for receiving invocations and messages.
   */
  async set(
    endpointUrl: string,
    events?: string[]
  ): Promise<WebhookConfig> {
    return this.client.post<WebhookConfig>('/agents/me/webhook', {
      endpoint_url: endpointUrl,
      events: events ?? ['invocation', 'message'],
    });
  }

  /**
   * Get current webhook configuration.
   */
  async get(): Promise<WebhookConfig | null> {
    return this.client.get<WebhookConfig | null>('/agents/me/webhook');
  }

  /**
   * Remove webhook configuration.
   */
  async remove(): Promise<void> {
    await this.client.delete('/agents/me/webhook');
  }
}
