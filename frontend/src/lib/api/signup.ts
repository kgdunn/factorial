/**
 * REST API client for signup request and invite endpoints.
 */

import type { TokenResponse } from './auth';
import { authFetch } from './client';

export interface SignupSubmitResponse {
  message: string;
}

export interface InviteValidateResponse {
  email: string;
  valid: boolean;
}

export interface SignupDetail {
  id: string;
  email: string;
  use_case: string;
  status: string;
  admin_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface SignupListResponse {
  signups: SignupDetail[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Public endpoints
// ---------------------------------------------------------------------------

export async function postSignupRequest(
  email: string,
  useCase: string,
): Promise<SignupSubmitResponse> {
  const resp = await fetch('/api/v1/signup/request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, use_case: useCase }),
  });

  if (resp.status === 409) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || 'A signup request for this email already exists');
  }
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Signup request failed: ${resp.status}`);
  }
  return resp.json();
}

export async function getInviteValidation(
  token: string,
): Promise<InviteValidateResponse> {
  const resp = await fetch(`/api/v1/signup/invite/validate?token=${encodeURIComponent(token)}`);
  if (!resp.ok) throw new Error('Failed to validate invite');
  return resp.json();
}

export async function postInviteRegister(
  token: string,
  password: string,
  displayName?: string,
  background?: string,
): Promise<TokenResponse> {
  const body: Record<string, string> = { token, password };
  if (displayName) body.display_name = displayName;
  if (background) body.background = background;

  const resp = await fetch('/api/v1/signup/invite/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Registration failed: ${resp.status}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// Admin endpoints (require auth)
// ---------------------------------------------------------------------------

export async function getAdminSignups(
  status?: string,
  page: number = 1,
  pageSize: number = 50,
): Promise<SignupListResponse> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('page', String(page));
  params.set('page_size', String(pageSize));

  const resp = await authFetch(`/api/v1/signup/admin/list?${params}`);
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to fetch signups: ${resp.status}`);
  }
  return resp.json();
}

export async function postApproveSignup(signupId: string): Promise<void> {
  const resp = await authFetch(`/api/v1/signup/admin/${signupId}/approve`, {
    method: 'POST',
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Approve failed: ${resp.status}`);
  }
}

export async function postRejectSignup(
  signupId: string,
  note?: string,
): Promise<void> {
  const resp = await authFetch(`/api/v1/signup/admin/${signupId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note || null }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Reject failed: ${resp.status}`);
  }
}
