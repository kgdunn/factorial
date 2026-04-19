/**
 * Rolling LLM connection status, polled from the backend.
 *
 * Drives the global SystemBanner. Polls `/api/v1/health/llm` every 20s
 * (paused while the tab is hidden). When an in-flight SSE chat surfaces
 * an `anthropic_unavailable` error, we short-circuit to `down`
 * optimistically and schedule a confirming poll a few seconds later —
 * otherwise a user who just saw the failure would wait up to one full
 * poll interval to see the banner.
 *
 * Three consecutive fetch failures set `pollFailed`, which renders a
 * separate "cannot reach the server" banner. This distinguishes a
 * backend outage from an upstream Anthropic outage so operators can
 * tell at a glance which side is broken.
 */

export type AnthropicStatus = 'ok' | 'slow' | 'down' | 'unknown';

const POLL_INTERVAL_MS = 20_000;
const SSE_FAST_PATH_DELAY_MS = 5_000;
const MAX_CONSECUTIVE_FETCH_FAILURES = 3;

interface HealthResponse {
  status: AnthropicStatus;
  sample_count?: number;
  error_count?: number;
  error_rate?: number;
  p95_latency_ms?: number | null;
  last_error?: string | null;
  last_error_at?: string | null;
  updated_at?: string;
}

class AnthropicStatusStore {
  status = $state<AnthropicStatus>('unknown');
  lastError = $state<string | null>(null);
  p95LatencyMs = $state<number | null>(null);
  pollFailed = $state(false);

  private intervalId: ReturnType<typeof setInterval> | null = null;
  private fastPathTimer: ReturnType<typeof setTimeout> | null = null;
  private consecutiveFailures = 0;
  private visibilityHandler: (() => void) | null = null;

  start() {
    if (typeof window === 'undefined') return;
    if (this.intervalId !== null) return;

    // Kick off one immediate poll so the banner reflects reality on page load.
    void this.pollOnce();

    this.intervalId = setInterval(() => void this.pollOnce(), POLL_INTERVAL_MS);

    this.visibilityHandler = () => {
      if (document.hidden) return;
      // Coming back from a hidden tab — refresh immediately.
      void this.pollOnce();
    };
    document.addEventListener('visibilitychange', this.visibilityHandler);
  }

  stop() {
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    if (this.fastPathTimer !== null) {
      clearTimeout(this.fastPathTimer);
      this.fastPathTimer = null;
    }
    if (this.visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.visibilityHandler);
      this.visibilityHandler = null;
    }
  }

  /** Called when an SSE error event arrives with kind === "anthropic_unavailable". */
  markErrorFromSSE(detail: string | null) {
    this.status = 'down';
    this.lastError = detail;
    // Confirm (or clear) via a fresh poll shortly after — the backend
    // tracker may reclassify based on the wider rolling window.
    if (this.fastPathTimer !== null) clearTimeout(this.fastPathTimer);
    this.fastPathTimer = setTimeout(() => void this.pollOnce(), SSE_FAST_PATH_DELAY_MS);
  }

  private async pollOnce() {
    if (typeof document !== 'undefined' && document.hidden) return;

    try {
      const response = await fetch('/api/v1/health/llm', {
        method: 'GET',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = (await response.json()) as HealthResponse;
      this.status = data.status ?? 'unknown';
      this.lastError = data.last_error ?? null;
      this.p95LatencyMs = data.p95_latency_ms ?? null;
      this.consecutiveFailures = 0;
      this.pollFailed = false;
    } catch {
      this.consecutiveFailures += 1;
      if (this.consecutiveFailures >= MAX_CONSECUTIVE_FETCH_FAILURES) {
        this.pollFailed = true;
      }
    }
  }
}

export const anthropicStatus = new AnthropicStatusStore();
