/**
 * REST API client for cookie-based authentication.
 *
 * The session and CSRF cookies are set by the backend on /auth/login (and
 * /auth/setup/complete and /signup/invite/register) and are sent
 * automatically by the browser on subsequent requests. Nothing in the
 * frontend touches localStorage; identity comes from /auth/me.
 */

import { csrfHeader } from './csrf';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  background: string | null;
  is_admin: boolean;
  created_at: string | null;
  balance_usd: string | null;
  balance_tokens: number | null;
}

function browserTimezone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

export async function postLogin(
  email: string,
  password: string,
): Promise<UserProfile> {
  const payload: Record<string, string> = { email, password };
  const tz = browserTimezone();
  if (tz) payload.timezone = tz;

  const resp = await fetch('/api/v1/auth/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (resp.status === 401) throw new Error('Invalid email or password');
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Login failed: ${resp.status}`);
  }
  return resp.json();
}

export async function postLogout(): Promise<void> {
  await fetch('/api/v1/auth/logout', {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeader(),
  });
}

export async function getMe(): Promise<UserProfile | null> {
  const resp = await fetch('/api/v1/auth/me', { credentials: 'include' });
  if (resp.status === 401) return null;
  if (!resp.ok) throw new Error('Failed to fetch user profile');
  return resp.json();
}

// ---------------------------------------------------------------------------
// Password reset / first-time setup
// ---------------------------------------------------------------------------

export interface SetupValidateResponse {
  email: string;
  valid: boolean;
  purpose: 'setup' | 'reset' | null;
}

export async function postPasswordResetRequest(email: string): Promise<void> {
  // Always returns 202 whether the email exists or not (no enumeration).
  await fetch('/api/v1/auth/password-reset/request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
}

export async function getSetupValidation(token: string): Promise<SetupValidateResponse> {
  const resp = await fetch(`/api/v1/auth/setup/validate?token=${encodeURIComponent(token)}`);
  if (!resp.ok) throw new Error('Failed to validate link');
  return resp.json();
}

export async function postSetupComplete(token: string, password: string): Promise<UserProfile> {
  const resp = await fetch('/api/v1/auth/setup/complete', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Setup failed: ${resp.status}`);
  }
  return resp.json();
}
