/**
 * Webhook management operations
 */

import { AxiosInstance } from 'axios';

export interface WebhookEndpoint {
  id: string;
  name: string;
  description?: string;
  url: string;
  secret: string;
  event_types: string[];
  is_active: boolean;
  retry_policy: 'exponential' | 'linear' | 'none';
  max_retries: number;
  timeout_seconds: number;
  custom_headers: Record<string, string>;
  total_deliveries: number;
  successful_deliveries: number;
  failed_deliveries: number;
  last_triggered_at?: string;
  last_success_at?: string;
  last_failure_at?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateWebhookOptions {
  name: string;
  url: string;
  event_types: string[];
  description?: string;
  retry_policy?: 'exponential' | 'linear' | 'none';
  max_retries?: number;
  timeout_seconds?: number;
  custom_headers?: Record<string, string>;
}

export interface UpdateWebhookOptions {
  name?: string;
  url?: string;
  event_types?: string[];
  is_active?: boolean;
  retry_policy?: 'exponential' | 'linear' | 'none';
  max_retries?: number;
}

export interface DeliveryLog {
  id: string;
  webhook_endpoint_id: string;
  event_id?: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: 'pending' | 'delivered' | 'failed' | 'retrying';
  attempts: number;
  response_status_code?: number;
  response_body?: string;
  response_time_ms?: number;
  last_error?: string;
  next_retry_at?: string;
  created_at: string;
  delivered_at?: string;
}

/**
 * Webhooks client for webhook endpoint management.
 */
export class Webhooks {
  constructor(private client: AxiosInstance) {}

  /**
   * Create a new webhook endpoint.
   * @returns The created webhook including the secret (save this!)
   */
  async create(options: CreateWebhookOptions): Promise<WebhookEndpoint> {
    const response = await this.client.post<WebhookEndpoint>('/webhooks', {
      name: options.name,
      url: options.url,
      event_types: options.event_types,
      description: options.description,
      retry_policy: options.retry_policy ?? 'exponential',
      max_retries: options.max_retries ?? 5,
      timeout_seconds: options.timeout_seconds ?? 30,
      custom_headers: options.custom_headers ?? {},
    });
    return response.data;
  }

  /**
   * List all webhook endpoints.
   */
  async list(options?: { limit?: number; offset?: number }): Promise<WebhookEndpoint[]> {
    const response = await this.client.get<{ webhooks: WebhookEndpoint[] }>('/webhooks', {
      params: {
        limit: options?.limit ?? 50,
        offset: options?.offset ?? 0,
      },
    });
    return response.data.webhooks;
  }

  /**
   * Get a webhook by ID.
   */
  async get(webhookId: string): Promise<WebhookEndpoint> {
    const response = await this.client.get<WebhookEndpoint>(`/webhooks/${webhookId}`);
    return response.data;
  }

  /**
   * Update a webhook endpoint.
   */
  async update(webhookId: string, options: UpdateWebhookOptions): Promise<WebhookEndpoint> {
    const response = await this.client.patch<WebhookEndpoint>(`/webhooks/${webhookId}`, options);
    return response.data;
  }

  /**
   * Delete a webhook endpoint.
   */
  async delete(webhookId: string): Promise<void> {
    await this.client.delete(`/webhooks/${webhookId}`);
  }

  /**
   * Send a test ping to the webhook.
   */
  async test(webhookId: string): Promise<{ delivery_id: string }> {
    const response = await this.client.post<{ delivery_id: string }>(
      `/webhooks/${webhookId}/test`
    );
    return response.data;
  }

  /**
   * Rotate the webhook's signing secret.
   * @returns The new secret (save this!)
   */
  async rotateSecret(webhookId: string): Promise<{ secret: string }> {
    const response = await this.client.post<{ secret: string }>(
      `/webhooks/${webhookId}/rotate-secret`
    );
    return response.data;
  }

  /**
   * List delivery logs for a webhook.
   */
  async listDeliveries(
    webhookId: string,
    options?: {
      status?: 'pending' | 'delivered' | 'failed' | 'retrying';
      limit?: number;
      offset?: number;
    }
  ): Promise<DeliveryLog[]> {
    const params: Record<string, unknown> = {
      limit: options?.limit ?? 50,
      offset: options?.offset ?? 0,
    };
    if (options?.status) {
      params.status = options.status;
    }
    const response = await this.client.get<{ deliveries: DeliveryLog[] }>(
      `/webhooks/${webhookId}/deliveries`,
      { params }
    );
    return response.data.deliveries;
  }

  /**
   * Manually retry a failed delivery.
   */
  async retryDelivery(deliveryId: string): Promise<DeliveryLog> {
    const response = await this.client.post<DeliveryLog>(
      `/webhooks/deliveries/${deliveryId}/retry`
    );
    return response.data;
  }
}
