/**
 * POST-based SSE client for the chat endpoint, plus a GET-based
 * resume client that replays persisted events after a dropped stream.
 *
 * The backend uses POST for SSE (not GET), so the browser's native
 * EventSource API cannot be used. This module uses fetch() with a
 * ReadableStream and manual SSE line parsing instead — which has the
 * side benefit of letting us read ``id:`` lines (EventSource exposes
 * them too, but not before the first event, and not via a clean API
 * alongside custom event names).
 */

import { anthropicStatus } from '$lib/state/anthropicStatus.svelte';
import { triggerReauth } from '$lib/state/reauth.svelte';
import type {
  ExperimentCreatedEvent,
  PhaseEvent,
  PlanEvent,
  PlanUpdateEvent,
  SSECallbacks,
} from '$lib/types';

import { csrfHeader } from './csrf';

// ---------------------------------------------------------------------------
// SSE line parser
// ---------------------------------------------------------------------------

export async function parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: string, data: string, id: string | null) => void,
  signal: AbortSignal,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';
  let currentData = '';
  let currentId: string | null = null;

  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    // sse_starlette emits CRLF terminators per the SSE spec; native browser
    // EventSource handles both, but our manual parser must too — splitting
    // on `\n` alone leaves a stray `\r` on the blank separator line and the
    // ``line === ''`` dispatch check never fires.
    const lines = buffer.split(/\r\n|\n/);
    // Keep the last (possibly incomplete) line in the buffer
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith(':')) {
        // SSE comment / keep-alive ping -- ignore
        continue;
      }

      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        currentData += (currentData ? '\n' : '') + line.slice(6);
      } else if (line.startsWith('id: ')) {
        currentId = line.slice(4).trim();
      } else if (line === '') {
        // Blank line = end of event
        if (currentEvent && currentData) {
          onEvent(currentEvent, currentData, currentId);
        }
        currentEvent = '';
        currentData = '';
        currentId = null;
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Event dispatcher
// ---------------------------------------------------------------------------

function dispatchSSEEvent(
  event: string,
  rawData: string,
  eventId: string | null,
  callbacks: SSECallbacks,
): void {
  if (eventId) {
    callbacks.onEventId?.(eventId);
  }

  let data: Record<string, unknown>;
  try {
    data = JSON.parse(rawData);
  } catch {
    callbacks.onError(`Failed to parse SSE data: ${rawData}`);
    return;
  }

  switch (event) {
    case 'conversation_id':
      callbacks.onConversationId(
        data.conversation_id as string,
        data.turn_id as string | undefined,
      );
      break;
    case 'token':
      callbacks.onToken(data.text as string);
      break;
    case 'tool_start':
      callbacks.onToolStart(
        data.tool as string,
        data.input as Record<string, unknown>,
      );
      break;
    case 'tool_result':
      callbacks.onToolResult(
        data.tool as string,
        data.output as Record<string, unknown>,
      );
      break;
    case 'done':
      callbacks.onDone();
      break;
    case 'error':
      if (data.kind === 'anthropic_unavailable') {
        // Optimistically flip the global banner to 'down' ahead of the
        // next scheduled health poll, so the chatting user sees what
        // just happened instead of waiting up to 20s.
        anthropicStatus.markErrorFromSSE((data.detail as string | null) ?? null);
      }
      callbacks.onError(data.message as string);
      break;
    case 'experiment_created':
      callbacks.onExperimentCreated?.(data as unknown as ExperimentCreatedEvent);
      break;
    case 'plan':
      callbacks.onPlan?.(data as unknown as PlanEvent);
      break;
    case 'plan_update':
      callbacks.onPlanUpdate?.(data as unknown as PlanUpdateEvent);
      break;
    case 'phase':
      callbacks.onPhase?.(data as unknown as PhaseEvent);
      break;
    case 'interrupted':
      callbacks.onInterrupted?.(
        (data.message as string) ??
          'The stream was interrupted. You can retry to regenerate the response.',
      );
      break;
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Stream a chat message to the backend and dispatch SSE events via
 * callbacks. Returns an AbortController for cancellation.
 */
export function streamChat(
  message: string,
  conversationId: string | null,
  detailLevel: 'beginner' | 'intermediate' | 'expert',
  callbacks: SSECallbacks,
): AbortController {
  const controller = new AbortController();

  const body: Record<string, unknown> = { message, detail_level: detailLevel };
  if (conversationId) {
    body.conversation_id = conversationId;
  }

  (async () => {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...csrfHeader(),
      };

      let response = await fetch('/api/v1/chat', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (response.status === 401) {
        // Session expired before the stream opened; pause for re-auth
        // and replay the request once.
        try {
          await triggerReauth();
        } catch {
          callbacks.onError('Session expired');
          return;
        }
        response = await fetch('/api/v1/chat', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', ...csrfHeader() },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
      }

      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`Server error ${response.status}: ${text}`);
        return;
      }

      if (!response.body) {
        callbacks.onError('Response body is empty');
        return;
      }

      const reader = response.body.getReader();
      await parseSSEStream(
        reader,
        (event, data, id) => dispatchSSEEvent(event, data, id, callbacks),
        controller.signal,
      );
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // User cancelled -- not an error
        return;
      }
      callbacks.onError(
        err instanceof Error ? err.message : 'Connection failed',
      );
    }
  })();

  return controller;
}

/**
 * Resume a previously-interrupted SSE chat stream.
 *
 * Sends ``Last-Event-ID`` if ``lastEventId`` is given so the backend
 * can skip events the client has already seen. Otherwise the backend
 * replays the most recent turn for the conversation from the start.
 */
export function resumeChatStream(
  conversationId: string,
  lastEventId: string | null,
  callbacks: SSECallbacks,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const headers: Record<string, string> = {};
      if (lastEventId) {
        headers['Last-Event-ID'] = lastEventId;
      }

      let response = await fetch(
        `/api/v1/chat/${encodeURIComponent(conversationId)}/resume`,
        {
          method: 'GET',
          credentials: 'include',
          headers,
          signal: controller.signal,
        },
      );

      if (response.status === 401) {
        try {
          await triggerReauth();
        } catch {
          callbacks.onError('Session expired');
          return;
        }
        response = await fetch(
          `/api/v1/chat/${encodeURIComponent(conversationId)}/resume`,
          {
            method: 'GET',
            credentials: 'include',
            headers,
            signal: controller.signal,
          },
        );
      }

      if (response.status === 404) {
        // Nothing to resume — surface as an interrupted signal so the
        // UI doesn't spin.
        callbacks.onInterrupted?.('No events available to resume.');
        return;
      }

      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`Resume failed ${response.status}: ${text}`);
        return;
      }

      if (!response.body) {
        callbacks.onError('Resume response body is empty');
        return;
      }

      const reader = response.body.getReader();
      await parseSSEStream(
        reader,
        (event, data, id) => dispatchSSEEvent(event, data, id, callbacks),
        controller.signal,
      );
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return;
      }
      callbacks.onError(
        err instanceof Error ? err.message : 'Resume connection failed',
      );
    }
  })();

  return controller;
}
