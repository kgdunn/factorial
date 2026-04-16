<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { authState } from '$lib/state/auth.svelte';

  let { children }: { children: Snippet } = $props();

  // Pages that don't require authentication
  const publicPaths = ['/', '/login', '/register', '/register/complete'];

  // Auth guard: redirect to /login if not authenticated on protected pages
  $effect(() => {
    const currentPath = $page.url.pathname;
    if (!authState.isAuthenticated && !publicPaths.includes(currentPath)) {
      goto('/login');
    }
  });

  function handleLogout() {
    authState.logout();
    goto('/login');
  }
</script>

<div class="flex h-screen flex-col">
  <!-- Navigation bar -->
  <nav class="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
    <a href="/" class="text-lg font-bold text-gray-800">
      Agentic <span class="text-primary">DOE</span>
    </a>
    <div class="flex items-center gap-6">
      {#if authState.isAuthenticated}
        <a
          href="/chat"
          class="text-sm text-gray-600 hover:text-primary transition-colors"
        >
          Chat
        </a>
        <a
          href="/experiments"
          class="text-sm text-gray-600 hover:text-primary transition-colors"
        >
          Experiments
        </a>
        {#if authState.user?.is_admin}
          <a
            href="/admin/signups"
            class="text-sm text-gray-600 hover:text-primary transition-colors"
          >
            Admin
          </a>
        {/if}
        <span class="text-sm text-gray-500">
          {authState.user?.display_name || authState.user?.email || ''}
        </span>
        <button
          onclick={handleLogout}
          class="text-sm text-gray-600 hover:text-red-600 transition-colors"
        >
          Sign out
        </button>
      {:else}
        <a
          href="/login"
          class="text-sm text-gray-600 hover:text-primary transition-colors"
        >
          Sign in
        </a>
        <a
          href="/register"
          class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 transition-colors"
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
