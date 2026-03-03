/**
 * Multi-tenant operations
 */

import { AxiosInstance } from 'axios';

export interface TenantSettings {
  id: string;
  account_id: string;
  subdomain?: string;
  custom_domain?: string;
  logo_url?: string;
  primary_color?: string;
  display_name?: string;
  features: Record<string, boolean>;
  allowed_ip_ranges?: string[];
  require_2fa: boolean;
  session_timeout_minutes: number;
  allowed_oauth_providers?: string[];
  rate_limit_multiplier: number;
  custom_rate_limits?: Record<string, number>;
  webhook_signing_version: string;
  data_region?: string;
  is_active: boolean;
  suspended_at?: string;
  suspension_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateTenantSettingsOptions {
  subdomain?: string;
  custom_domain?: string;
  display_name?: string;
  logo_url?: string;
  primary_color?: string;
  features?: Record<string, boolean>;
  allowed_ip_ranges?: string[];
  rate_limit_multiplier?: number;
  allowed_oauth_providers?: string[];
}

export interface UpdateTenantSettingsOptions {
  subdomain?: string;
  custom_domain?: string;
  display_name?: string;
  logo_url?: string;
  primary_color?: string;
  features?: Record<string, boolean>;
  allowed_ip_ranges?: string[];
  rate_limit_multiplier?: number;
  allowed_oauth_providers?: string[];
}

export interface TenantLimits {
  agents: {
    current: number;
    limit: number;
  };
  memories: {
    current: number;
    limit: number;
  };
  storage_bytes: {
    current: number;
    limit: number;
  };
  webhooks: {
    current: number;
    limit: number;
  };
  api_requests_per_minute: number;
}

export interface TenantInvite {
  id: string;
  account_id: string;
  email: string;
  role: 'admin' | 'member' | 'viewer';
  token: string;
  expires_at: string;
  accepted_at?: string;
  created_by?: string;
  created_at: string;
}

/**
 * Tenants client for multi-tenant management.
 */
export class Tenants {
  constructor(private client: AxiosInstance) {}

  /**
   * Get tenant settings.
   * @returns Tenant settings or null if not configured
   */
  async getSettings(): Promise<TenantSettings | null> {
    try {
      const response = await this.client.get<TenantSettings>('/tenants/settings');
      return response.data;
    } catch (error: unknown) {
      if ((error as { response?: { status?: number } })?.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  /**
   * Create tenant settings.
   */
  async createSettings(options: CreateTenantSettingsOptions): Promise<TenantSettings> {
    const response = await this.client.post<TenantSettings>('/tenants/settings', {
      subdomain: options.subdomain,
      custom_domain: options.custom_domain,
      display_name: options.display_name,
      logo_url: options.logo_url,
      primary_color: options.primary_color,
      features: options.features,
      allowed_ip_ranges: options.allowed_ip_ranges,
      rate_limit_multiplier: options.rate_limit_multiplier ?? 1.0,
      allowed_oauth_providers: options.allowed_oauth_providers,
    });
    return response.data;
  }

  /**
   * Update tenant settings.
   */
  async updateSettings(options: UpdateTenantSettingsOptions): Promise<TenantSettings> {
    const response = await this.client.patch<TenantSettings>('/tenants/settings', options);
    return response.data;
  }

  /**
   * Get resource limits for the tenant.
   */
  async getLimits(): Promise<TenantLimits> {
    const response = await this.client.get<TenantLimits>('/tenants/limits');
    return response.data;
  }

  /**
   * Create a tenant invite.
   */
  async invite(email: string, role: 'admin' | 'member' | 'viewer' = 'member'): Promise<TenantInvite> {
    const response = await this.client.post<TenantInvite>('/tenants/invites', {
      email,
      role,
    });
    return response.data;
  }

  /**
   * List pending invites.
   */
  async listInvites(options?: { limit?: number; offset?: number }): Promise<TenantInvite[]> {
    const response = await this.client.get<{ invites: TenantInvite[] }>('/tenants/invites', {
      params: {
        limit: options?.limit ?? 50,
        offset: options?.offset ?? 0,
      },
    });
    return response.data.invites;
  }

  /**
   * Revoke an invite.
   */
  async revokeInvite(inviteId: string): Promise<void> {
    await this.client.delete(`/tenants/invites/${inviteId}`);
  }
}
