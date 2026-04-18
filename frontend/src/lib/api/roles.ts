/**
 * REST API client for role endpoints.
 *
 * `GET /roles` is public (used by the signup form to populate its
 * dropdown). All mutations require admin auth.
 */

import { authFetch } from './client';

export interface Role {
  id: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export async function getRoles(): Promise<Role[]> {
  const resp = await fetch('/api/v1/roles');
  if (!resp.ok) throw new Error('Failed to load roles');
  const data = await resp.json();
  return data.roles;
}

export async function createRole(name: string, description: string | null): Promise<Role> {
  const resp = await authFetch('/api/v1/roles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to create role: ${resp.status}`);
  }
  return resp.json();
}

export async function updateRole(id: string, description: string | null): Promise<Role> {
  const resp = await authFetch(`/api/v1/roles/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to update role: ${resp.status}`);
  }
  return resp.json();
}

export async function deleteRole(id: string): Promise<void> {
  const resp = await authFetch(`/api/v1/roles/${id}`, { method: 'DELETE' });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to delete role: ${resp.status}`);
  }
}
