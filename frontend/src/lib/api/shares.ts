/**
 * Unauthenticated client for the public share endpoints.
 *
 * These calls deliberately use plain fetch (not authFetch) so a visitor
 * without an account can still load the share page.
 */

import type { ExportFormat, PublicExperimentView } from '$lib/types';

const BASE = '/api/v1/public/experiments';

export async function fetchPublicShare(token: string): Promise<PublicExperimentView> {
  const resp = await fetch(`${BASE}/${encodeURIComponent(token)}`);
  if (resp.status === 404) {
    throw new Error('This share link is no longer valid.');
  }
  if (resp.status === 429) {
    throw new Error('Too many requests. Please try again shortly.');
  }
  if (!resp.ok) throw new Error(`Failed to load share (${resp.status})`);
  return resp.json();
}

export async function exportPublicShare(
  token: string,
  format: ExportFormat,
): Promise<Blob> {
  const url = new URL(
    `${BASE}/${encodeURIComponent(token)}/export`,
    window.location.origin,
  );
  url.searchParams.set('format', format);
  const resp = await fetch(url.toString());
  if (!resp.ok) throw new Error(`Export failed (${resp.status})`);
  return resp.blob();
}
