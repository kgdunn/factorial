/**
 * Cookie-aware fetch wrapper.
 *
 * The session cookie is sent automatically; the wrapper just adds the
 * CSRF header on state-changing requests and recovers from a 401 by
 * opening the inline re-auth modal once and replaying the request after
 * sign-in. Concurrent 401s share a single modal via the reauth state.
 *
 * 5xx responses are surfaced to the caller and never trigger logout —
 * a brief deploy-time outage no longer kicks the user back to /login.
 */

import { triggerReauth } from '$lib/state/reauth.svelte';

import { csrfHeader } from './csrf';

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function withCookieHeaders(init: RequestInit | undefined): RequestInit {
  const method = (init?.method || 'GET').toUpperCase();
  const headers = new Headers(init?.headers);
  if (UNSAFE_METHODS.has(method)) {
    for (const [k, v] of Object.entries(csrfHeader())) headers.set(k, v);
  }
  return { ...init, credentials: 'include', headers };
}

/**
 * Wrapper around fetch() that injects credentials + CSRF and recovers
 * from a single 401 by opening the inline re-auth modal and retrying.
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const resp = await fetch(input, withCookieHeaders(init));
  if (resp.status !== 401) return resp;

  // Drain the body so the connection can close cleanly while the user
  // sits on the modal.
  await resp.text().catch(() => undefined);

  try {
    await triggerReauth();
  } catch {
    return resp; // user cancelled — let the caller handle the 401
  }

  return fetch(input, withCookieHeaders(init));
}
