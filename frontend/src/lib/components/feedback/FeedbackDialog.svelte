<script lang="ts">
  import { authState } from '$lib/state/auth.svelte';
  import {
    FEEDBACK_TOPIC_LABELS,
    submitFeedback,
    type FeedbackTopic,
  } from '$lib/api/feedback';

  interface Props {
    open: boolean;
  }

  let { open = $bindable() }: Props = $props();

  const MAX_MESSAGE = 5000;
  const MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024;

  let topic = $state<FeedbackTopic>('incorrect_response');
  let message = $state('');
  let includeScreenshot = $state(true);
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let success = $state(false);

  const remaining = $derived(MAX_MESSAGE - message.length);
  const canSubmit = $derived(
    message.trim().length >= 10 && message.length <= MAX_MESSAGE && !submitting,
  );

  function reset() {
    topic = 'incorrect_response';
    message = '';
    includeScreenshot = true;
    error = null;
    success = false;
  }

  function close() {
    if (submitting) return;
    open = false;
    // Keep success state visible briefly; reset on next open.
    setTimeout(reset, 300);
  }

  async function captureScreenshot(): Promise<string | null> {
    try {
      const { default: html2canvas } = await import('html2canvas');
      const canvas = await html2canvas(document.body, {
        logging: false,
        useCORS: true,
        scale: Math.min(1, 1600 / document.body.scrollWidth),
      });
      const dataUrl = canvas.toDataURL('image/png');
      const b64 = dataUrl.split(',')[1] ?? '';
      // Rough size check: base64 expands by 4/3.
      if ((b64.length * 3) / 4 > MAX_SCREENSHOT_BYTES) {
        error = 'Screenshot is too large to include; sending without it.';
        return null;
      }
      return b64;
    } catch (err) {
      console.error('html2canvas failed', err);
      error = 'Could not capture a screenshot; sending without it.';
      return null;
    }
  }

  async function handleSubmit(event: Event) {
    event.preventDefault();
    if (!canSubmit) return;
    submitting = true;
    error = null;

    let screenshot: string | undefined;
    if (includeScreenshot && typeof window !== 'undefined') {
      // Hide the dialog briefly so it doesn't appear in the screenshot.
      const dialogEl = document.getElementById('feedback-dialog-wrapper');
      if (dialogEl) dialogEl.style.visibility = 'hidden';
      try {
        const b64 = await captureScreenshot();
        if (b64) screenshot = b64;
      } finally {
        if (dialogEl) dialogEl.style.visibility = '';
      }
    }

    try {
      await submitFeedback({
        topic,
        message,
        page_url: typeof window !== 'undefined' ? window.location.href : undefined,
        user_agent:
          typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
        viewport:
          typeof window !== 'undefined'
            ? `${window.innerWidth}x${window.innerHeight}`
            : undefined,
        screenshot_png_b64: screenshot,
      });
      success = true;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to submit feedback';
    } finally {
      submitting = false;
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape' && open) close();
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <div
    id="feedback-dialog-wrapper"
    class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 px-4"
    role="dialog"
    aria-modal="true"
    aria-labelledby="feedback-title"
  >
    <div class="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
      <div class="mb-4 flex items-start justify-between">
        <div>
          <h2 id="feedback-title" class="font-serif text-xl text-ink">
            Give feedback
          </h2>
          <p class="mt-0.5 text-xs text-ink-faint">
            Signed in as {authState.user?.email ?? 'unknown'}
          </p>
        </div>
        <button
          type="button"
          class="cursor-pointer text-ink-faint hover:text-ink"
          aria-label="Close"
          onclick={close}
          disabled={submitting}
        >
          <svg
            class="h-5 w-5"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          >
            <path d="M5 5 L15 15 M15 5 L5 15" />
          </svg>
        </button>
      </div>

      {#if success}
        <div class="rounded-md border border-rule bg-clay-tint px-4 py-6 text-center">
          <p class="font-serif text-lg text-ink">Thanks — we got it.</p>
          <p class="mt-1 text-sm text-ink-soft">
            A copy has been emailed to you and to the site administrators.
          </p>
          <button
            type="button"
            class="mt-4 cursor-pointer rounded-full bg-clay px-4 py-2 text-sm font-medium text-white hover:bg-clay-ink"
            onclick={close}
          >
            Close
          </button>
        </div>
      {:else}
        <form onsubmit={handleSubmit} class="flex flex-col gap-4">
          <label class="flex flex-col gap-1">
            <span class="font-sans text-xs font-medium text-ink-soft"
              >Topic</span
            >
            <select
              bind:value={topic}
              class="rounded-md border border-rule bg-white px-3 py-2 font-sans text-sm text-ink focus:border-clay focus:outline-none"
              disabled={submitting}
            >
              {#each Object.entries(FEEDBACK_TOPIC_LABELS) as [value, label] (value)}
                <option {value}>{label}</option>
              {/each}
            </select>
          </label>

          <label class="flex flex-col gap-1">
            <span class="font-sans text-xs font-medium text-ink-soft"
              >What would you like to tell us?</span
            >
            <textarea
              bind:value={message}
              rows="5"
              maxlength={MAX_MESSAGE}
              placeholder="Be as specific as you can — what happened, what you expected, what you were trying to do."
              class="resize-y rounded-md border border-rule bg-white px-3 py-2 font-sans text-sm text-ink placeholder:text-ink-faint focus:border-clay focus:outline-none"
              disabled={submitting}
              required
            ></textarea>
            <span class="self-end font-mono text-[11px] text-ink-faint">
              {remaining} left
            </span>
          </label>

          <label class="flex items-start gap-2">
            <input
              type="checkbox"
              bind:checked={includeScreenshot}
              class="mt-1 h-4 w-4 accent-clay"
              disabled={submitting}
            />
            <span class="flex flex-col gap-0.5">
              <span class="flex items-center gap-1.5 font-sans text-sm text-ink">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.4"
                  aria-hidden="true"
                >
                  <path d="M3 6 H6 L7.5 4 H12.5 L14 6 H17 V15 H3 Z" />
                  <circle cx="10" cy="10.5" r="2.8" />
                </svg>
                Include a screenshot of this page
              </span>
              <span class="text-[11px] text-ink-faint">
                Your screenshot is sent to site administrators only.
              </span>
            </span>
          </label>

          {#if error}
            <div
              class="rounded-md bg-red-50 px-3 py-2 text-xs text-[color:var(--color-negative)]"
              role="alert"
            >
              {error}
            </div>
          {/if}

          <div class="flex items-center justify-between gap-3">
            <span class="text-[11px] text-ink-faint">
              You'll get an email copy.
            </span>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="cursor-pointer rounded-full border border-rule px-4 py-2 font-sans text-sm text-ink-soft hover:bg-paper-2"
                onclick={close}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                class="cursor-pointer rounded-full bg-clay px-4 py-2 font-sans text-sm font-medium text-white transition-colors hover:bg-clay-ink disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canSubmit}
              >
                {submitting ? 'Sending…' : 'Submit'}
              </button>
            </div>
          </div>
        </form>
      {/if}
    </div>
  </div>
{/if}
