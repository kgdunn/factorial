/**
 * Authenticated fetch wrapper.
 *
 * Injects the Authorization header with the current access token.
 * Used by experiments.ts and sse.ts to ensure all API calls are authenticated.
 */

import { authState } from '$lib/state/auth.svelte';

/**
 * Wrapper around fetch() that injects the Bearer token.
 * Falls through to regular fetch if no token is available.
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const token = authState.accessToken;
  if (!token) {
    return fetch(input, init);
  }

  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);

  return fetch(input, { ...init, headers });
}
