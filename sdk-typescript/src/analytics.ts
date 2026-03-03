/**
 * Analytics operations
 */

import { AxiosInstance } from 'axios';

export interface DashboardData {
  total_requests: number;
  total_memories: number;
  total_capabilities: number;
  period: {
    days: number;
    start: string;
    end: string;
  };
  trends?: {
    requests_change: number;
    memories_change: number;
  };
}

export interface UsageMetric {
  metric_type: string;
  count: number;
  sum_value?: number;
  avg_value?: number;
  timestamp?: string;
}

export interface UsageData {
  metrics: UsageMetric[];
  period: {
    days: number;
    granularity: string;
  };
}

export interface TimelinePoint {
  timestamp: string;
  count: number;
  value?: number;
}

export interface EndpointMetric {
  endpoint: string;
  method: string;
  request_count: number;
  error_count: number;
  avg_latency_ms: number;
  p95_latency_ms?: number;
}

export interface StorageData {
  current: {
    memory_count: number;
    memory_bytes: number;
    media_count: number;
    media_bytes: number;
    relationship_count: number;
  };
  history: Array<{
    date: string;
    memory_count: number;
    memory_bytes: number;
  }>;
}

/**
 * Analytics client for usage metrics and dashboards.
 */
export class Analytics {
  constructor(private client: AxiosInstance) {}

  /**
   * Get dashboard summary.
   */
  async dashboard(days: number = 7): Promise<DashboardData> {
    const response = await this.client.get<DashboardData>('/analytics/dashboard', {
      params: { days },
    });
    return response.data;
  }

  /**
   * Get usage metrics.
   */
  async usage(options?: {
    metric_types?: string[];
    granularity?: 'hour' | 'day';
    days?: number;
  }): Promise<UsageData> {
    const params: Record<string, unknown> = {
      granularity: options?.granularity ?? 'hour',
      days: options?.days ?? 7,
    };
    if (options?.metric_types) {
      params.metric_types = options.metric_types;
    }
    const response = await this.client.get<UsageData>('/analytics/usage', { params });
    return response.data;
  }

  /**
   * Get usage timeline data for charts.
   */
  async timeline(options?: {
    metric_type?: string;
    granularity?: 'hour' | 'day';
    days?: number;
  }): Promise<TimelinePoint[]> {
    const response = await this.client.get<{ timeline: TimelinePoint[] }>(
      '/analytics/usage/timeline',
      {
        params: {
          metric_type: options?.metric_type ?? 'api_request',
          granularity: options?.granularity ?? 'hour',
          days: options?.days ?? 7,
        },
      }
    );
    return response.data.timeline;
  }

  /**
   * Get per-endpoint metrics.
   */
  async endpoints(options?: {
    endpoint?: string;
    days?: number;
  }): Promise<EndpointMetric[]> {
    const params: Record<string, unknown> = {
      days: options?.days ?? 7,
    };
    if (options?.endpoint) {
      params.endpoint = options.endpoint;
    }
    const response = await this.client.get<{ endpoints: EndpointMetric[] }>(
      '/analytics/endpoints',
      { params }
    );
    return response.data.endpoints;
  }

  /**
   * Get storage usage.
   */
  async storage(days: number = 30): Promise<StorageData> {
    const response = await this.client.get<StorageData>('/analytics/storage', {
      params: { days },
    });
    return response.data;
  }

  /**
   * Export analytics data.
   */
  async export(options?: {
    format?: 'json' | 'csv';
    start_date?: string;
    end_date?: string;
    metric_types?: string[];
  }): Promise<unknown> {
    const params: Record<string, unknown> = {
      format: options?.format ?? 'json',
    };
    if (options?.start_date) params.start_date = options.start_date;
    if (options?.end_date) params.end_date = options.end_date;
    if (options?.metric_types) params.metric_types = options.metric_types;

    const response = await this.client.get('/analytics/export', { params });
    return response.data;
  }
}
