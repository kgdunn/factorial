<script lang="ts">
  import {
    FEEDBACK_TOPIC_LABELS,
    feedbackScreenshotUrl,
    listAdminFeedback,
    replyToFeedback,
    setFeedbackReplied,
    type FeedbackRow,
  } from '$lib/api/feedback';

  type Filter = 'unreplied' | 'replied' | 'all';

  let items = $state<FeedbackRow[]>([]);
  let total = $state(0);
  let page = $state(1);
  const pageSize = 50;
  let filter = $state<Filter>('unreplied');
  let loading = $state(true);
  let error = $state<string | null>(null);

  let expandedId = $state<string | null>(null);
  let replyDrafts = $state<Record<string, string>>({});
  let screenshotPreviewId = $state<string | null>(null);
  let busyId = $state<string | null>(null);

  async function load() {
    loading = true;
    error = null;
    try {
      const replied =
        filter === 'all' ? undefined : filter === 'replied' ? true : false;
      const res = await listAdminFeedback(page, pageSize, replied);
      items = res.items;
      total = res.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load feedback';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    void filter;
    void page;
    load();
  });

  function quoteOriginal(row: FeedbackRow): string {
    const lines = row.message.split('\n');
    return `\n\n> ${lines.join('\n> ')}`;
  }

  function startReply(row: FeedbackRow) {
    expandedId = expandedId === row.id ? null : row.id;
    if (expandedId === row.id && !replyDrafts[row.id]) {
      replyDrafts[row.id] = quoteOriginal(row).trim();
    }
  }

  async function sendReply(row: FeedbackRow) {
    const body = (replyDrafts[row.id] ?? '').trim();
    if (body.length < 10) {
      error = 'Reply must be at least 10 characters.';
      return;
    }
    busyId = row.id;
    error = null;
    try {
      await replyToFeedback(row.id, body);
      expandedId = null;
      delete replyDrafts[row.id];
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to send reply';
    } finally {
      busyId = null;
    }
  }

  async function toggleReplied(row: FeedbackRow) {
    busyId = row.id;
    error = null;
    try {
      await setFeedbackReplied(row.id, row.replied_at === null);
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to update';
    } finally {
      busyId = null;
    }
  }

  function excerpt(text: string, n = 140): string {
    const squished = text.replace(/\s+/g, ' ').trim();
    return squished.length > n ? squished.slice(0, n) + '…' : squished;
  }

  function formatDate(iso: string): string {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }
</script>

<div class="mx-auto max-w-6xl px-6 py-6">
  <div class="mb-4 flex items-center justify-between gap-4">
    <div>
      <h2 class="text-xl font-semibold text-gray-900">Feedback inbox</h2>
      <p class="text-sm text-gray-500">
        User-submitted notes via the in-app Give feedback button.
      </p>
    </div>
    <div class="flex gap-1 rounded-md border border-gray-200 p-0.5">
      {#each ['unreplied', 'all', 'replied'] as f (f)}
        <button
          type="button"
          class="rounded px-3 py-1 text-xs font-medium transition-colors
            {filter === f ? 'bg-primary text-white' : 'text-gray-600 hover:bg-gray-100'}"
          onclick={() => {
            filter = f as Filter;
            page = 1;
          }}
        >
          {f === 'unreplied' ? 'Unreplied' : f === 'replied' ? 'Replied' : 'All'}
        </button>
      {/each}
    </div>
  </div>

  {#if error}
    <div class="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-negative" role="alert">
      {error}
    </div>
  {/if}

  {#if loading}
    <div class="py-10 text-center text-sm text-gray-500">Loading…</div>
  {:else if items.length === 0}
    <div class="py-10 text-center text-sm text-gray-500">
      Nothing here right now.
    </div>
  {:else}
    <div class="overflow-x-auto rounded-md border border-gray-200 bg-white">
      <table class="min-w-full divide-y divide-gray-200 text-sm">
        <thead class="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase">
          <tr>
            <th class="px-4 py-2">Date</th>
            <th class="px-4 py-2">User</th>
            <th class="px-4 py-2">Topic</th>
            <th class="px-4 py-2">Excerpt</th>
            <th class="px-4 py-2">Page</th>
            <th class="px-4 py-2">Shot</th>
            <th class="px-4 py-2">Replied</th>
            <th class="px-4 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          {#each items as row (row.id)}
            <tr class="align-top">
              <td class="px-4 py-2 font-mono text-xs text-gray-700">
                {formatDate(row.created_at)}
              </td>
              <td class="px-4 py-2 text-gray-800">{row.user_email}</td>
              <td class="px-4 py-2 text-gray-800">
                {FEEDBACK_TOPIC_LABELS[row.topic]}
              </td>
              <td class="max-w-md px-4 py-2 text-gray-700">
                {excerpt(row.message)}
              </td>
              <td class="px-4 py-2 font-mono text-xs text-gray-500">
                {#if row.page_url}
                  <a
                    href={row.page_url}
                    class="text-primary hover:underline"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {row.page_url.replace(/^https?:\/\/[^/]+/, '') || '/'}
                  </a>
                {:else}
                  —
                {/if}
              </td>
              <td class="px-4 py-2">
                {#if row.has_screenshot}
                  <button
                    type="button"
                    class="text-xs text-primary hover:underline"
                    onclick={() => (screenshotPreviewId = row.id)}
                  >
                    View
                  </button>
                {:else}
                  <span class="text-xs text-gray-400">—</span>
                {/if}
              </td>
              <td class="px-4 py-2">
                {#if row.replied_at}
                  <span class="text-xs text-gray-600">
                    ✓ {formatDate(row.replied_at)}
                    {#if row.replied_by_email}
                      <div class="text-[11px] text-gray-400">
                        by {row.replied_by_email}
                      </div>
                    {/if}
                  </span>
                {:else}
                  <span class="text-xs text-gray-400">—</span>
                {/if}
              </td>
              <td class="px-4 py-2 text-right">
                <div class="flex justify-end gap-1">
                  <button
                    type="button"
                    class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
                    onclick={() => startReply(row)}
                    disabled={busyId === row.id}
                  >
                    {expandedId === row.id ? 'Cancel' : 'Reply'}
                  </button>
                  <button
                    type="button"
                    class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
                    onclick={() => toggleReplied(row)}
                    disabled={busyId === row.id}
                    title={row.replied_at
                      ? 'Mark as unreplied'
                      : 'Mark as replied (no email)'}
                  >
                    {row.replied_at ? 'Unmark' : 'Mark replied'}
                  </button>
                </div>
              </td>
            </tr>
            {#if expandedId === row.id}
              <tr>
                <td class="bg-gray-50 px-4 py-3" colspan="8">
                  <div class="flex flex-col gap-2">
                    <div class="font-sans text-xs text-gray-500">
                      Reply to {row.user_email}. They'll get this by email.
                    </div>
                    <textarea
                      bind:value={replyDrafts[row.id]}
                      rows="6"
                      class="w-full resize-y rounded-md border border-gray-200 bg-white px-3 py-2 font-sans text-sm text-gray-800 focus:border-primary focus:outline-none"
                    ></textarea>
                    <div class="flex justify-end gap-2">
                      <button
                        type="button"
                        class="rounded-md border border-gray-200 px-3 py-1 text-xs text-gray-700 hover:bg-gray-50"
                        onclick={() => (expandedId = null)}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        class="rounded-md bg-primary px-3 py-1 text-xs font-medium text-white hover:bg-primary/90 disabled:opacity-50"
                        onclick={() => sendReply(row)}
                        disabled={busyId === row.id}
                      >
                        {busyId === row.id ? 'Sending…' : 'Send reply'}
                      </button>
                    </div>
                  </div>
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>

    <div class="mt-3 flex items-center justify-between text-xs text-gray-500">
      <span>Total: {total}</span>
      <div class="flex gap-1">
        <button
          type="button"
          class="rounded-md border border-gray-200 px-2 py-1 disabled:opacity-50"
          onclick={() => (page = Math.max(1, page - 1))}
          disabled={page === 1}
        >
          Prev
        </button>
        <span class="px-2 py-1">Page {page}</span>
        <button
          type="button"
          class="rounded-md border border-gray-200 px-2 py-1 disabled:opacity-50"
          onclick={() => (page = page + 1)}
          disabled={page * pageSize >= total}
        >
          Next
        </button>
      </div>
    </div>
  {/if}

  {#if screenshotPreviewId}
    <div
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 px-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="flex max-h-[90vh] max-w-5xl flex-col overflow-hidden rounded-lg bg-white">
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-2">
          <span class="text-sm text-gray-700">Screenshot</span>
          <button
            type="button"
            class="text-gray-400 hover:text-gray-700"
            aria-label="Close"
            onclick={() => (screenshotPreviewId = null)}
          >
            ✕
          </button>
        </div>
        <img
          src={feedbackScreenshotUrl(screenshotPreviewId)}
          alt="Feedback screenshot"
          class="max-h-[85vh] max-w-full object-contain"
        />
      </div>
    </div>
  {/if}
</div>
