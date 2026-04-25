/**
 * Tests for ``authFetch`` in the cookie-auth world:
 *
 * - credentials: 'include' on every call (so the browser sends the cookie)
 * - X-CSRF-Token mirrored from the factorial_csrf cookie on unsafe methods
 * - 401 opens the inline reauth modal once and replays the request
 * - 5xx is surfaced unchanged (no logout, no modal)
 */
import { type MockInstance, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { authFetch } from './client';
import * as reauth from '$lib/state/reauth.svelte';

function jsonResp(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('authFetch', () => {
  let fetchSpy: MockInstance<typeof globalThis.fetch>;

  beforeEach(() => {
    document.cookie = 'factorial_csrf=test-csrf; path=/';
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
    document.cookie = 'factorial_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  function init(call: number): RequestInit {
    return fetchSpy.mock.calls[call][1] as RequestInit;
  }

  it("sends credentials: 'include' on every call", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResp({ ok: true }));
    await authFetch('/api/v1/experiments');
    expect(init(0).credentials).toBe('include');
  });

  it('attaches X-CSRF-Token from the cookie on POST', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResp({ ok: true }));
    await authFetch('/api/v1/experiments', { method: 'POST' });
    const headers = new Headers(init(0).headers);
    expect(headers.get('X-CSRF-Token')).toBe('test-csrf');
  });

  it('does not attach X-CSRF-Token on GET', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResp({ ok: true }));
    await authFetch('/api/v1/experiments');
    const headers = new Headers(init(0).headers);
    expect(headers.get('X-CSRF-Token')).toBeNull();
  });

  it('opens the reauth modal on 401 and retries on success', async () => {
    fetchSpy
      .mockResolvedValueOnce(jsonResp({ detail: 'expired' }, 401)) // initial
      .mockResolvedValueOnce(jsonResp({ ok: true })); // retry

    const triggerSpy = vi
      .spyOn(reauth, 'triggerReauth')
      .mockResolvedValueOnce(undefined);

    const resp = await authFetch('/api/v1/experiments');

    expect(resp.status).toBe(200);
    expect(triggerSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    triggerSpy.mockRestore();
  });

  it('returns the original 401 when the user cancels reauth', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResp({ detail: 'expired' }, 401));

    const triggerSpy = vi
      .spyOn(reauth, 'triggerReauth')
      .mockRejectedValueOnce(new Error('cancelled'));

    const resp = await authFetch('/api/v1/experiments');

    expect(resp.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    triggerSpy.mockRestore();
  });

  it('does not open the reauth modal on 5xx — surfaces the error', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResp({ detail: 'down' }, 503));

    const triggerSpy = vi.spyOn(reauth, 'triggerReauth');

    const resp = await authFetch('/api/v1/experiments');

    expect(resp.status).toBe(503);
    expect(triggerSpy).not.toHaveBeenCalled();
    triggerSpy.mockRestore();
  });
});
