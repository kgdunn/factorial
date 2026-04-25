/**
 * Regression tests for the manual SSE parser.
 *
 * The backend (sse_starlette) emits CRLF line terminators per the SSE spec.
 * A previous version of this parser split on '\n' only and checked for an
 * empty separator line via ``line === ''`` — which silently failed when the
 * blank line was actually '\r'. The streamed events never reached the
 * dispatcher and the chat UI hung with no rendered text.
 *
 * Tests below cover both CRLF and LF terminators, chunk boundaries that
 * split events mid-line, and SSE comments / keep-alives.
 */
import { describe, expect, it, vi } from 'vitest';

import { parseSSEStream } from './sse';

type Captured = { event: string; data: string; id: string | null };

function streamFromChunks(chunks: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
  return stream.getReader();
}

async function collect(chunks: string[]): Promise<Captured[]> {
  const captured: Captured[] = [];
  await parseSSEStream(
    streamFromChunks(chunks),
    (event, data, id) => captured.push({ event, data, id }),
    new AbortController().signal,
  );
  return captured;
}

describe('parseSSEStream', () => {
  it('dispatches CRLF-terminated events (sse_starlette default wire format)', async () => {
    const wire =
      'id: turn-1:1\r\nevent: token\r\ndata: {"text":"hello"}\r\n\r\n' +
      'id: turn-1:2\r\nevent: done\r\ndata: {}\r\n\r\n';

    const events = await collect([wire]);

    expect(events).toEqual([
      { event: 'token', data: '{"text":"hello"}', id: 'turn-1:1' },
      { event: 'done', data: '{}', id: 'turn-1:2' },
    ]);
  });

  it('also handles LF-only terminators (back-compat with non-spec emitters)', async () => {
    const wire = 'event: token\ndata: {"text":"hi"}\n\n';

    const events = await collect([wire]);

    expect(events).toEqual([{ event: 'token', data: '{"text":"hi"}', id: null }]);
  });

  it('reassembles events split across chunk boundaries', async () => {
    // Split mid-payload and right at the CRLF separator to exercise the
    // ``buffer = lines.pop()`` carry-over path.
    const events = await collect([
      'event: token\r\ndata: {"text":"par',
      't one"}\r\n\r\nevent: token\r\n',
      'data: {"text":"part two"}\r\n\r\n',
    ]);

    expect(events).toEqual([
      { event: 'token', data: '{"text":"part one"}', id: null },
      { event: 'token', data: '{"text":"part two"}', id: null },
    ]);
  });

  it('ignores SSE comments / keep-alive pings', async () => {
    const wire =
      ': ping - 2026-04-25T14:00:00Z\r\n\r\n' +
      'event: token\r\ndata: {"text":"after-ping"}\r\n\r\n';

    const events = await collect([wire]);

    expect(events).toEqual([{ event: 'token', data: '{"text":"after-ping"}', id: null }]);
  });

  it('does not dispatch an event missing either name or data', async () => {
    const onEvent = vi.fn();
    const wire =
      'id: orphan\r\n\r\n' + // id with no event/data — should not fire
      'event: ping\r\n\r\n' + // event with no data — should not fire
      'event: token\r\ndata: {"text":"real"}\r\n\r\n';

    await parseSSEStream(streamFromChunks([wire]), onEvent, new AbortController().signal);

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith('token', '{"text":"real"}', null);
  });
});
