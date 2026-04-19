/**
 * Typed client for the user feedback API.
 */

import { authFetch } from './client';

export type FeedbackTopic =
  | 'incorrect_response'
  | 'improvement'
  | 'bug'
  | 'other';

export const FEEDBACK_TOPIC_LABELS: Record<FeedbackTopic, string> = {
  incorrect_response: 'Incorrect response',
  improvement: 'Improvement suggestion',
  bug: 'Bug / error',
  other: 'Other',
};

export interface FeedbackSubmitRequest {
  topic: FeedbackTopic;
  message: string;
  page_url?: string;
  user_agent?: string;
  viewport?: string;
  screenshot_png_b64?: string;
}

export interface FeedbackSubmitResponse {
  id: string;
  created_at: string;
}

export interface FeedbackRow {
  id: string;
  user_id: string;
  user_email: string;
  user_display_name: string | null;
  topic: FeedbackTopic;
  message: string;
  page_url: string | null;
  user_agent: string | null;
  viewport: string | null;
  app_version: string | null;
  has_screenshot: boolean;
  replied_at: string | null;
  replied_by_user_id: string | null;
  replied_by_email: string | null;
  reply_body: string | null;
  created_at: string;
}

export interface FeedbackListResponse {
  items: FeedbackRow[];
  total: number;
  page: number;
  page_size: number;
}

async function ensureOk(resp: Response, fallback: string): Promise<Response> {
  if (!resp.ok) {
    let detail = fallback;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp;
}

export async function submitFeedback(
  payload: FeedbackSubmitRequest,
): Promise<FeedbackSubmitResponse> {
  const resp = await authFetch('/api/v1/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await ensureOk(resp, 'Failed to submit feedback');
  return (await resp.json()) as FeedbackSubmitResponse;
}

export async function listAdminFeedback(
  page = 1,
  pageSize = 50,
  replied?: boolean,
): Promise<FeedbackListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (replied !== undefined) params.set('replied', String(replied));
  const resp = await authFetch(`/api/v1/admin/feedback?${params.toString()}`);
  await ensureOk(resp, 'Failed to load feedback');
  return (await resp.json()) as FeedbackListResponse;
}

export async function replyToFeedback(id: string, body: string): Promise<void> {
  const resp = await authFetch(`/api/v1/admin/feedback/${id}/reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  });
  await ensureOk(resp, 'Failed to send reply');
}

export async function setFeedbackReplied(
  id: string,
  replied: boolean,
): Promise<void> {
  const resp = await authFetch(`/api/v1/admin/feedback/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ replied }),
  });
  await ensureOk(resp, 'Failed to update feedback');
}

export function feedbackScreenshotUrl(id: string): string {
  return `/api/v1/feedback/${id}/screenshot`;
}
