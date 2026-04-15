/**
 * POST-based SSE client.
 *
 * The backend uses POST for SSE (not GET), so the browser's native
 * EventSource API cannot be used. This module uses fetch() with a
 * ReadableStream and manual SSE line parsing instead.
 */

import { authState } from '$lib/state/auth.svelte';
import type { ExperimentCreatedEvent, SSECallbacks } from '$lib/types';

// ---------------------------------------------------------------------------
// SSE line parser
// ---------------------------------------------------------------------------

async function parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: string, data: string) => void,
  signal: AbortSignal,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';
  let currentData = '';

  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
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
      } else if (line === '') {
        // Blank line = end of event
        if (currentEvent && currentData) {
          onEvent(currentEvent, currentData);
        }
        currentEvent = '';
        currentData = '';
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
  callbacks: SSECallbacks,
): void {
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(rawData);
  } catch {
    callbacks.onError(`Failed to parse SSE data: ${rawData}`);
    return;
  }

  switch (event) {
    case 'conversation_id':
      callbacks.onConversationId(data.conversation_id as string);
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
      callbacks.onError(data.message as string);
      break;
    case 'experiment_created':
      callbacks.onExperimentCreated?.(data as unknown as ExperimentCreatedEvent);
      break;
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Stream a chat message to the backend and dispatch SSE events via callbacks.
 *
 * Returns an AbortController that can be used to cancel the request.
 */
export function streamChat(
  message: string,
  conversationId: string | null,
  callbacks: SSECallbacks,
): AbortController {
  const controller = new AbortController();

  const body: Record<string, unknown> = { message };
  if (conversationId) {
    body.conversation_id = conversationId;
  }

  (async () => {
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (authState.accessToken) {
        headers['Authorization'] = `Bearer ${authState.accessToken}`;
      }

      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });

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
        (event, data) => dispatchSSEEvent(event, data, callbacks),
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
