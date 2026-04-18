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

export type { Role };
