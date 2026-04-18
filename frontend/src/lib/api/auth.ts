/**
 * REST API client for authentication endpoints.
 */

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  background: string | null;
  is_admin: boolean;
  created_at: string | null;
}

export async function postRegister(
  email: string,
  password: string,
  displayName?: string,
  background?: string,
): Promise<TokenResponse> {
  const body: Record<string, string> = { email, password };
  if (displayName) body.display_name = displayName;
  if (background) body.background = background;

  const resp = await fetch('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (resp.status === 409) throw new Error('Email already registered');
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Registration failed: ${resp.status}`);
  }
  return resp.json();
}

export async function postLogin(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const resp = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

  if (resp.status === 401) throw new Error('Invalid email or password');
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Login failed: ${resp.status}`);
  }
  return resp.json();
}

export async function postRefresh(
  refreshToken: string,
): Promise<TokenResponse> {
  const resp = await fetch('/api/v1/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!resp.ok) throw new Error('Token refresh failed');
  return resp.json();
}

export async function getMe(accessToken: string): Promise<UserProfile> {
  const resp = await fetch('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

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

export async function postSetupComplete(token: string, password: string): Promise<TokenResponse> {
  const resp = await fetch('/api/v1/auth/setup/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Setup failed: ${resp.status}`);
  }
  return resp.json();
}
