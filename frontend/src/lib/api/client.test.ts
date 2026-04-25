/**
 * Tests for ``authFetch`` — in particular the transparent
 * refresh-on-401-and-retry behaviour, which keeps users from seeing
 * spurious "401" errors when their 30-minute access token expires
 * while the page is still open.
 */
import { type MockInstance, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { authFetch } from './client';
import { authState } from '$lib/state/auth.svelte';

function jsonResp(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('authFetch', () => {
  let fetchSpy: MockInstance<typeof globalThis.fetch>;

  beforeEach(() => {
    authState.accessToken = 'old-token';
    authState.refreshToken = 'refresh-token';
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
    authState.accessToken = null;
    authState.refreshToken = null;
  });

  function authHeader(call: number): string | null {
    const init = fetchSpy.mock.calls[call][1] as RequestInit | undefined;
    return new Headers(init?.headers).get('Authorization');
  }

  it('attaches the bearer token on the first attempt', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResp({ ok: true }));

    const resp = await authFetch('/api/v1/experiments');

    expect(resp.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(authHeader(0)).toBe('Bearer old-token');
  });

  it('refreshes once on 401 and retries with the new token', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResp({ detail: 'expired' }, 401)) // initial
      .mockResolvedValueOnce(
        jsonResp({ access_token: 'new-token', refresh_token: 'new-refresh' }),
      ) // POST /auth/refresh
      .mockResolvedValueOnce(jsonResp({ ok: true })); // retry

    const resp = await authFetch('/api/v1/experiments');

    expect(resp.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    expect(authHeader(0)).toBe('Bearer old-token');
    expect(authHeader(2)).toBe('Bearer new-token');
    expect(authState.accessToken).toBe('new-token');
  });

  it('returns the original 401 when the refresh call itself fails', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResp({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(jsonResp({ detail: 'bad refresh' }, 401));

    const resp = await authFetch('/api/v1/experiments');

    expect(resp.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    // ``authState.refresh()`` logs the user out on a failed refresh; the
    // layout auth guard then redirects to /login on the next render.
    expect(authState.accessToken).toBeNull();
  });

  it('shares a single refresh across concurrent 401s', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResp({ detail: 'expired' }, 401)) // req A initial
      .mockResolvedValueOnce(jsonResp({ detail: 'expired' }, 401)) // req B initial
      .mockResolvedValueOnce(
        jsonResp({ access_token: 'new-token', refresh_token: 'new-refresh' }),
      ) // single shared refresh
      .mockResolvedValueOnce(jsonResp({ ok: true })) // retry A
      .mockResolvedValueOnce(jsonResp({ ok: true })); // retry B

    const [a, b] = await Promise.all([
      authFetch('/api/v1/experiments'),
      authFetch('/api/v1/experiments?page=2'),
    ]);

    expect(a.status).toBe(200);
    expect(b.status).toBe(200);
    // Exactly one refresh call across the two retries.
    const refreshCalls = fetchSpy.mock.calls.filter(
      ([url]) => typeof url === 'string' && url.includes('/auth/refresh'),
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it('passes through unauthenticated when no token is present', async () => {
    authState.accessToken = null;
    fetchSpy.mockResolvedValueOnce(jsonResp({ ok: true }));

    await authFetch('/api/v1/experiments');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(authHeader(0)).toBeNull();
  });
});
