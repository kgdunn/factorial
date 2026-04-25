/**
 * Read the factorial_csrf cookie and produce the X-CSRF-Token header.
 *
 * The backend rejects state-changing requests when this header doesn't
 * match the cookie (double-submit). The cookie is set by the backend at
 * login time and is non-httpOnly so the SPA can read it.
 */

const CSRF_COOKIE = 'factorial_csrf';
const CSRF_HEADER = 'X-CSRF-Token';

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const prefix = `${name}=`;
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) return trimmed.slice(prefix.length);
  }
  return null;
}

export function csrfToken(): string | null {
  return readCookie(CSRF_COOKIE);
}

export function csrfHeader(): Record<string, string> {
  const token = csrfToken();
  return token ? { [CSRF_HEADER]: token } : {};
}
