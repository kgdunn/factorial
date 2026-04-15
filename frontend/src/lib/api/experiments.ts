/**
 * REST API client for experiment CRUD operations.
 */

import { authFetch } from '$lib/api/client';
import type {
  ChatMessage,
  ExperimentDetail,
  ExperimentListResponse,
  ResultsResponse,
} from '$lib/types';

const BASE = '/api/v1/experiments';

export async function fetchExperiments(
  params?: { status?: string; page?: number; page_size?: number },
): Promise<ExperimentListResponse> {
  const url = new URL(BASE, window.location.origin);
  if (params?.status) url.searchParams.set('status', params.status);
  if (params?.page) url.searchParams.set('page', String(params.page));
  if (params?.page_size) url.searchParams.set('page_size', String(params.page_size));

  const resp = await authFetch(url.toString());
  if (!resp.ok) throw new Error(`Failed to fetch experiments: ${resp.status}`);
  return resp.json();
}

export async function fetchExperiment(id: string): Promise<ExperimentDetail> {
  const resp = await authFetch(`${BASE}/${id}`);
  if (!resp.ok) throw new Error(`Failed to fetch experiment: ${resp.status}`);
  return resp.json();
}

export async function updateExperiment(
  id: string,
  body: { name?: string; status?: string },
): Promise<ExperimentDetail> {
  const resp = await authFetch(`${BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Failed to update experiment: ${resp.status}`);
  return resp.json();
}

export async function deleteExperiment(id: string): Promise<void> {
  const resp = await authFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(`Failed to delete experiment: ${resp.status}`);
}

export async function submitResults(
  id: string,
  results: Record<string, unknown>[],
): Promise<ResultsResponse> {
  const resp = await authFetch(`${BASE}/${id}/results`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results }),
  });
  if (!resp.ok) throw new Error(`Failed to submit results: ${resp.status}`);
  return resp.json();
}

export async function fetchResults(id: string): Promise<ResultsResponse> {
  const resp = await authFetch(`${BASE}/${id}/results`);
  if (!resp.ok) throw new Error(`Failed to fetch results: ${resp.status}`);
  return resp.json();
}

export async function fetchConversationMessages(
  conversationId: string,
): Promise<{ conversation_id: string; title: string; messages: ChatMessage[] }> {
  const resp = await authFetch(`/api/v1/chat/${conversationId}/messages`);
  if (!resp.ok) throw new Error(`Failed to fetch messages: ${resp.status}`);
  return resp.json();
}
