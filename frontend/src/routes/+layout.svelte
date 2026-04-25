<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { authState } from '$lib/state/auth.svelte';
  import { anthropicStatus } from '$lib/state/anthropicStatus.svelte';
  import Wordmark from '$lib/components/brand/Wordmark.svelte';
  import SystemBanner from '$lib/components/brand/SystemBanner.svelte';
  import ReauthModal from '$lib/components/auth/ReauthModal.svelte';
  import FeedbackLauncher from '$lib/components/feedback/FeedbackLauncher.svelte';

  let { children }: { children: Snippet } = $props();

  onMount(() => {
    anthropicStatus.start();
    return () => anthropicStatus.stop();
  });

  // Pages that don't require authentication
  const publicPaths = ['/', '/login', '/register', '/register/complete', '/prototype'];
  // Path prefixes that don't require authentication.
  // /auth/ holds the token-gated pages /auth/setup and /auth/reset, which
  // an unauthenticated user must reach via an emailed link.
  const publicPathPrefixes = ['/share/', '/auth/'];

  function isPublicPath(path: string): boolean {
    if (publicPaths.includes(path)) return true;
    return publicPathPrefixes.some((prefix) => path.startsWith(prefix));
  }

  // Auth guard: redirect to /login if not authenticated on protected pages.
  // Wait for the initial /auth/me round-trip so we don't redirect-flash on
  // cold load when the user is actually signed in via cookie.
  $effect(() => {
    if (!authState.bootComplete) return;
    const currentPath = $page.url.pathname;
    if (!authState.isAuthenticated && !isPublicPath(currentPath)) {
      goto('/login');
    }
  });

  async function handleLogout() {
    await authState.logout();
    goto('/login');
  }
</script>

<div class="flex h-dvh flex-col bg-paper">
  <SystemBanner />
  <!-- Navigation bar -->
  <nav class="flex flex-wrap items-center justify-between gap-y-2 border-b border-rule bg-paper-2 px-4 py-3 sm:px-6">
    <a href="/" class="flex items-center" aria-label="factori.al home">
      <Wordmark size={22} />
    </a>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2 sm:gap-6">
      {#if authState.isAuthenticated}
        <a
          href="/chat"
          class="font-sans text-sm text-ink-soft transition-colors hover:text-ink"
        >
          Agent
        </a>
        <a
          href="/experiments"
          class="font-sans text-sm text-ink-soft transition-colors hover:text-ink"
        >
          Projects
        </a>
        {#if authState.user?.is_admin}
          <a
            href="/admin/signups"
            class="font-sans text-sm text-ink-soft transition-colors hover:text-ink"
          >
            Admin
          </a>
        {/if}
        {#if authState.user?.balance_usd != null}
          <span
            class="hidden font-mono text-xs text-ink-faint sm:inline"
            title={`${authState.user.balance_tokens ?? 0} tokens`}
          >
            ${Number(authState.user.balance_usd).toFixed(2)}
          </span>
        {/if}
        <a
          href="/profile"
          class="hidden font-mono text-xs text-ink-faint underline-offset-2 hover:text-ink hover:underline sm:inline"
          title="Profile and active sessions"
        >
          {authState.user?.display_name || authState.user?.email || ''}
        </a>
        <button
          onclick={handleLogout}
          class="cursor-pointer font-sans text-sm text-ink-soft transition-colors hover:text-[color:var(--color-negative)]"
        >
          Sign out
        </button>
      {:else}
        <a
          href="/login"
          class="font-sans text-sm text-ink-soft transition-colors hover:text-ink"
        >
          Sign in
        </a>
        <a
          href="/register"
          class="rounded-full bg-ink px-4 py-1.5 font-sans text-sm font-medium text-paper transition-colors hover:bg-black/90"
        >
          Request access
        </a>
      {/if}
    </div>
  </nav>

  <!-- Page content -->
  <main class="flex-1 overflow-hidden">
    {@render children()}
  </main>

  <FeedbackLauncher />
  <ReauthModal />
</div>
