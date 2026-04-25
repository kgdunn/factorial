/**
 * REST API client for session management.
 *
 * Lists the current user's active sessions, revokes a specific session,
 * and signs out everywhere. The credential cookie value never leaves
 * the server — endpoints address sessions by ``public_id``.
 */

import { authFetch } from './client';

export interface SessionSummary {
  public_id: string;
  created_at: string;
  last_used_at: string;
  user_agent: string | null;
  ip: string | null;
  is_current: boolean;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const resp = await authFetch('/api/v1/auth/sessions');
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to load sessions: ${resp.status}`);
  }
  return resp.json();
}

export async function revokeSession(publicId: string): Promise<void> {
  const resp = await authFetch(`/api/v1/auth/sessions/${publicId}`, {
    method: 'DELETE',
  });
  if (!resp.ok && resp.status !== 404) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to revoke session: ${resp.status}`);
  }
}

export async function logoutEverywhere(): Promise<void> {
  const resp = await authFetch('/api/v1/auth/logout-all', { method: 'POST' });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed: ${resp.status}`);
  }
}
