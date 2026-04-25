<script lang="ts">
  import { goto } from '$app/navigation';
  import { authState } from '$lib/state/auth.svelte';
  import {
    listSessions,
    logoutEverywhere,
    revokeSession,
    type SessionSummary,
  } from '$lib/api/sessions';

  let sessions = $state<SessionSummary[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let confirmingLogoutAll = $state(false);

  async function refresh() {
    loading = true;
    error = null;
    try {
      sessions = await listSessions();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load sessions';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (authState.isAuthenticated) {
      void refresh();
    }
  });

  async function handleRevoke(publicId: string, isCurrent: boolean) {
    try {
      await revokeSession(publicId);
      if (isCurrent) {
        // Server already revoked our cookie's session; fall back to login.
        authState.user = null;
        await goto('/login');
        return;
      }
      await refresh();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to revoke';
    }
  }

  async function handleLogoutEverywhere() {
    try {
      await logoutEverywhere();
      authState.user = null;
      await goto('/login');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to sign out';
    }
  }

  function relTime(iso: string): string {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const sec = Math.floor(diffMs / 1000);
    if (sec < 60) return 'just now';
    if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`;
    return d.toLocaleDateString();
  }
</script>

<div class="mx-auto max-w-3xl px-4 py-8">
  <h1 class="mb-1 font-sans text-2xl font-semibold text-ink">Your profile</h1>
  <p class="mb-6 text-sm text-ink-soft">Account details and active sessions.</p>

  {#if authState.user}
    <section class="mb-8 rounded-lg border border-rule bg-paper-2 p-5">
      <h2 class="mb-3 text-sm font-medium text-ink">Account</h2>
      <dl class="grid grid-cols-1 gap-y-2 text-sm sm:grid-cols-3">
        <dt class="text-ink-faint">Email</dt>
        <dd class="sm:col-span-2 font-mono text-ink">{authState.user.email}</dd>

        {#if authState.user.display_name}
          <dt class="text-ink-faint">Display name</dt>
          <dd class="sm:col-span-2 text-ink">{authState.user.display_name}</dd>
        {/if}

        {#if authState.user.balance_usd != null}
          <dt class="text-ink-faint">Balance</dt>
          <dd class="sm:col-span-2 font-mono text-ink">
            ${Number(authState.user.balance_usd).toFixed(2)}
            <span class="text-ink-faint">
              ({authState.user.balance_tokens ?? 0} tokens)
            </span>
          </dd>
        {/if}
      </dl>
    </section>
  {/if}

  <section class="mb-6 rounded-lg border border-rule bg-paper-2 p-5">
    <div class="mb-3 flex items-baseline justify-between">
      <h2 class="text-sm font-medium text-ink">Active sessions</h2>
      <button
        class="font-sans text-sm text-ink-soft underline-offset-2 hover:underline disabled:opacity-50"
        onclick={() => (confirmingLogoutAll = true)}
        disabled={loading || sessions.length === 0}
      >
        Sign out everywhere
      </button>
    </div>

    <p class="mb-4 text-xs text-ink-faint">
      Each row is a browser that has an active session. Revoking one signs that
      browser out the next time it makes a request. Streaming chat replies
      already in flight finish before the cookie is rejected.
    </p>

    {#if error}
      <p class="mb-3 text-sm text-[color:var(--color-negative)]">{error}</p>
    {/if}

    {#if loading}
      <p class="text-sm text-ink-faint">Loading…</p>
    {:else if sessions.length === 0}
      <p class="text-sm text-ink-faint">No active sessions.</p>
    {:else}
      <ul class="divide-y divide-rule">
        {#each sessions as s (s.public_id)}
          <li class="flex items-center justify-between py-3 text-sm">
            <div class="min-w-0 flex-1 pr-3">
              <div class="truncate text-ink">
                {s.user_agent ?? 'Unknown device'}
                {#if s.is_current}
                  <span class="ml-2 rounded-full bg-ink px-2 py-0.5 text-xs text-paper">
                    this device
                  </span>
                {/if}
              </div>
              <div class="font-mono text-xs text-ink-faint">
                {s.ip ?? '—'} · last seen {relTime(s.last_used_at)}
              </div>
            </div>
            <button
              class="rounded-md px-3 py-1 text-xs text-ink-soft hover:bg-ink/5"
              onclick={() => handleRevoke(s.public_id, s.is_current)}
            >
              Sign out
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if confirmingLogoutAll}
    <div
      class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 px-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h3 class="mb-2 text-sm font-medium text-gray-800">Sign out everywhere?</h3>
        <p class="mb-4 text-sm text-gray-600">
          Every browser, including this one, will be signed out. You'll need to sign
          in again to come back.
        </p>
        <div class="flex justify-end gap-2">
          <button
            class="rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-100"
            onclick={() => (confirmingLogoutAll = false)}
          >
            Cancel
          </button>
          <button
            class="rounded-md bg-[color:var(--color-negative)] px-4 py-2 text-sm font-medium text-paper hover:bg-red-700"
            onclick={handleLogoutEverywhere}
          >
            Sign out everywhere
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>
