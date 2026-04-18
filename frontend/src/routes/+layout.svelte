<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { authState } from '$lib/state/auth.svelte';
  import Wordmark from '$lib/components/brand/Wordmark.svelte';

  let { children }: { children: Snippet } = $props();

  // Pages that don't require authentication
  const publicPaths = ['/', '/login', '/register', '/register/complete', '/prototype'];
  // Path prefixes that don't require authentication
  const publicPathPrefixes = ['/share/'];

  function isPublicPath(path: string): boolean {
    if (publicPaths.includes(path)) return true;
    return publicPathPrefixes.some((prefix) => path.startsWith(prefix));
  }

  // Auth guard: redirect to /login if not authenticated on protected pages
  $effect(() => {
    const currentPath = $page.url.pathname;
    if (!authState.isAuthenticated && !isPublicPath(currentPath)) {
      goto('/login');
    }
  });

  function handleLogout() {
    authState.logout();
    goto('/login');
  }
</script>

<div class="flex h-screen flex-col bg-paper">
  <!-- Navigation bar -->
  <nav class="flex items-center justify-between border-b border-rule bg-paper-2 px-6 py-3">
    <a href="/" class="flex items-center" aria-label="factori.al home">
      <Wordmark size={22} />
    </a>
    <div class="flex items-center gap-6">
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
        <span class="font-mono text-xs text-ink-faint">
          {authState.user?.display_name || authState.user?.email || ''}
        </span>
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
</div>
