<script lang="ts">
  import { onMount } from 'svelte';
  import {
    createShareLink,
    listShareLinks,
    revokeShareLink,
  } from '$lib/api/experiments';
  import type { ShareLink } from '$lib/types';

  interface Props {
    experimentId: string;
    open: boolean;
    onClose: () => void;
  }

  let { experimentId, open = $bindable(), onClose }: Props = $props();

  type ExpiryChoice = '1d' | '7d' | '30d' | 'never';

  let shares = $state<ShareLink[]>([]);
  let loading = $state(false);
  let creating = $state(false);
  let error = $state<string | null>(null);
  let copiedToken = $state<string | null>(null);
  let expiryChoice = $state<ExpiryChoice>('30d');
  let allowResults = $state(true);

  async function refresh() {
    loading = true;
    error = null;
    try {
      const resp = await listShareLinks(experimentId);
      shares = resp.shares;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load shares';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (open) refresh();
  });

  onMount(() => {
    if (open) refresh();
  });

  function expiryPayload(): { expires_at: string | null; never_expire: boolean } {
    if (expiryChoice === 'never') return { expires_at: null, never_expire: true };
    const days = expiryChoice === '1d' ? 1 : expiryChoice === '7d' ? 7 : 30;
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + days);
    return { expires_at: d.toISOString(), never_expire: false };
  }

  async function handleCreate() {
    creating = true;
    error = null;
    try {
      const { expires_at, never_expire } = expiryPayload();
      await createShareLink(experimentId, {
        expires_at,
        never_expire,
        allow_results: allowResults,
      });
      await refresh();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to create share link';
    } finally {
      creating = false;
    }
  }

  async function handleRevoke(token: string) {
    try {
      await revokeShareLink(token);
      await refresh();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to revoke';
    }
  }

  async function handleCopy(url: string, token: string) {
    try {
      await navigator.clipboard.writeText(url);
      copiedToken = token;
      setTimeout(() => {
        if (copiedToken === token) copiedToken = null;
      }, 2000);
    } catch {
      // clipboard blocked — user can copy manually.
    }
  }

  function isActive(s: ShareLink): boolean {
    if (s.revoked_at) return false;
    if (s.expires_at && new Date(s.expires_at) <= new Date()) return false;
    return true;
  }

  function statusLabel(s: ShareLink): string {
    if (s.revoked_at) return 'Revoked';
    if (s.expires_at && new Date(s.expires_at) <= new Date()) return 'Expired';
    if (s.expires_at) return `Expires ${new Date(s.expires_at).toLocaleDateString()}`;
    return 'Never expires';
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 px-4"
    role="dialog"
    aria-modal="true"
  >
    <div class="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl">
      <div class="mb-4 flex items-start justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-800">Share this experiment</h2>
          <p class="text-sm text-gray-500">
            Mint a read-only link collaborators can open without signing in.
          </p>
        </div>
        <button
          class="text-gray-400 hover:text-gray-700"
          aria-label="Close"
          onclick={onClose}
        >
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
        </button>
      </div>

      <!-- Create form -->
      <div class="mb-5 rounded-md border border-gray-200 p-4">
        <h3 class="mb-3 text-sm font-medium text-gray-700">Create a new link</h3>

        <div class="mb-3">
          <div class="mb-1 text-xs font-medium text-gray-500">Expires</div>
          <div class="flex flex-wrap gap-2">
            {#each ['1d', '7d', '30d', 'never'] as choice (choice)}
              <label class="inline-flex cursor-pointer items-center gap-1 rounded-md border border-gray-300 px-3 py-1 text-sm {expiryChoice === choice ? 'border-primary bg-blue-50 text-primary' : 'text-gray-600'}">
                <input
                  type="radio"
                  class="sr-only"
                  name="expiry"
                  value={choice}
                  checked={expiryChoice === choice}
                  onchange={() => (expiryChoice = choice as ExpiryChoice)}
                />
                {choice === 'never' ? 'Never' : choice === '1d' ? '1 day' : choice === '7d' ? '7 days' : '30 days'}
              </label>
            {/each}
          </div>
        </div>

        <label class="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" bind:checked={allowResults} class="h-4 w-4" />
          Include run-level responses (uncheck to share design only)
        </label>

        <div class="mt-3 flex justify-end">
          <button
            class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
            onclick={handleCreate}
            disabled={creating}
          >
            {creating ? 'Creating…' : 'Create link'}
          </button>
        </div>
      </div>

      <!-- Existing shares -->
      <div>
        <h3 class="mb-2 text-sm font-medium text-gray-700">Existing links</h3>
        {#if error}
          <div class="mb-2 rounded-md bg-red-50 px-3 py-2 text-xs text-negative">{error}</div>
        {/if}
        {#if loading}
          <div class="py-4 text-center text-sm text-gray-500">Loading…</div>
        {:else if shares.length === 0}
          <div class="py-4 text-center text-sm text-gray-500">No links yet.</div>
        {:else}
          <ul class="divide-y divide-gray-100 rounded-md border border-gray-200">
            {#each shares as share (share.id)}
              <li class="flex items-center gap-3 px-3 py-2 text-sm">
                <div class="flex-1 overflow-hidden">
                  <div class="truncate font-mono text-xs text-gray-700">{share.url}</div>
                  <div class="flex gap-3 text-xs text-gray-500">
                    <span class="{isActive(share) ? 'text-positive' : 'text-gray-400'}">{statusLabel(share)}</span>
                    <span>Viewed {share.view_count}×</span>
                    <span>{share.allow_results ? 'Full results' : 'Design only'}</span>
                  </div>
                </div>
                {#if isActive(share)}
                  <button
                    class="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                    onclick={() => handleCopy(share.url, share.token)}
                  >
                    {copiedToken === share.token ? 'Copied!' : 'Copy'}
                  </button>
                  <button
                    class="rounded-md border border-red-200 px-2 py-1 text-xs text-negative hover:bg-red-50"
                    onclick={() => handleRevoke(share.token)}
                  >
                    Revoke
                  </button>
                {/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <div class="mt-5 flex justify-end">
        <button
          class="rounded-md border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          onclick={onClose}
        >
          Close
        </button>
      </div>
    </div>
  </div>
{/if}
