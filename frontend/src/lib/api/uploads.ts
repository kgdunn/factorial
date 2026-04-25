/**
 * REST API client for the DOE experiment upload flow.
 *
 * Three operations mirror the backend endpoints under
 * ``/api/v1/experiments/uploads``:
 *
 * 1. ``uploadDesign(file)`` — multipart upload, returns either a
 *    parsed structure or clarifying questions.
 * 2. ``submitUploadAnswers(uploadId, answers)`` — second round-trip.
 * 3. ``finalizeUpload(uploadId, body)`` — persist the user-confirmed
 *    structure and surface the resulting Experiment.
 */

import { authFetch } from '$lib/api/client';
import type {
  ExperimentDetail,
  ParsedDesignPayload,
  UploadParseResponse,
} from '$lib/types';

const BASE = '/api/v1/experiments/uploads';

async function readErrorDetail(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    if (typeof body?.detail === 'string') return body.detail;
  } catch {
    /* fall through */
  }
  return `Request failed with status ${resp.status}`;
}

export async function uploadDesign(file: File): Promise<UploadParseResponse> {
  const fd = new FormData();
  fd.append('file', file);
  const resp = await authFetch(BASE, { method: 'POST', body: fd });
  if (!resp.ok) throw new Error(await readErrorDetail(resp));
  return resp.json();
}

export async function submitUploadAnswers(
  uploadId: string,
  answers: Record<string, string>,
): Promise<UploadParseResponse> {
  const resp = await authFetch(`${BASE}/${uploadId}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  });
  if (!resp.ok) throw new Error(await readErrorDetail(resp));
  return resp.json();
}

export async function finalizeUpload(
  uploadId: string,
  body: { name?: string; parsed: ParsedDesignPayload },
): Promise<ExperimentDetail> {
  const resp = await authFetch(`${BASE}/${uploadId}/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readErrorDetail(resp));
  return resp.json();
}
