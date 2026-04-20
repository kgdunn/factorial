/**
 * REST API client for the admin user-management endpoints.
 */

import type { Role } from './roles';
import { authFetch } from './client';

export interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  is_active: boolean;
  role: { id: string; name: string; description: string | null } | null;
  created_at: string;

  // Sign-in activity + geo (populated on login; null for never-logged-in accounts).
  last_login_at: string | null;
  last_login_ip: string | null;
  country: string | null;
  timezone: string | null;

  // Balance (null when no user_balances row exists yet).
  balance_usd: string | null;
  balance_tokens: number | null;

  // Lifetime LLM spend + activity rollups.
  total_cost_usd: string;
  total_markup_cost_usd: string;
  total_tokens: number;
  conversation_count: number;
  last_conversation_at: string | null;

  feedback_count: number;
  open_experiments: number;
  avg_runs_per_experiment: number | null;

  signup_status: string | null;
  disclaimers_accepted: boolean | null;
}

export interface AdminUserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserUpdate {
  is_admin?: boolean;
  is_active?: boolean;
  role_id?: string | null;
  clear_role?: boolean;
  display_name?: string;
}

export interface ResetPasswordResponse {
  message: string;
  url: string;
}

export interface BalanceTopUp {
  usd?: string;
  tokens?: number;
}

export interface AdminBalanceResponse {
  user_id: string;
  balance_usd: string;
  balance_tokens: number;
}

export async function getAdminUsers(opts: {
  page?: number;
  pageSize?: number;
  search?: string;
  adminsOnly?: boolean;
} = {}): Promise<AdminUserListResponse> {
  const params = new URLSearchParams();
  params.set('page', String(opts.page ?? 1));
  params.set('page_size', String(opts.pageSize ?? 50));
  if (opts.search) params.set('search', opts.search);
  if (opts.adminsOnly) params.set('admins_only', 'true');

  const resp = await authFetch(`/api/v1/admin/users?${params}`);
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to load users: ${resp.status}`);
  }
  return resp.json();
}

export async function patchAdminUser(id: string, body: AdminUserUpdate): Promise<AdminUser> {
  const resp = await authFetch(`/api/v1/admin/users/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to update user: ${resp.status}`);
  }
  return resp.json();
}

export async function postResetUserPassword(id: string): Promise<ResetPasswordResponse> {
  const resp = await authFetch(`/api/v1/admin/users/${id}/reset-password`, {
    method: 'POST',
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to issue reset link: ${resp.status}`);
  }
  return resp.json();
}

export async function postTopUpBalance(
  id: string,
  body: BalanceTopUp,
): Promise<AdminBalanceResponse> {
  const resp = await authFetch(`/api/v1/admin/users/${id}/balance/topup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ usd: body.usd ?? '0', tokens: body.tokens ?? 0 }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to top up balance: ${resp.status}`);
  }
  return resp.json();
}

export type { Role };
