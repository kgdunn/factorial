<script lang="ts">
  import { authState } from '$lib/state/auth.svelte';
</script>

<svelte:head>
  <title>Factorial</title>
</svelte:head>

<div class="flex h-full flex-col items-center justify-center bg-surface px-6 text-center">
  <h1 class="text-4xl font-bold text-gray-800">
    <span class="text-primary">Factorial</span>
  </h1>
  <p class="mt-4 max-w-md text-lg text-gray-500">
    Design, run, and analyse experiments through a conversational agent,
    using Design of Experiments methodology.
  </p>
  {#if authState.isAuthenticated}
    <a
      href="/chat"
      class="mt-8 inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-medium text-white
             shadow-sm hover:bg-primary-dark transition-colors"
    >
      Start chatting
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
      </svg>
    </a>
  {:else}
    <a
      href="/register"
      class="mt-8 inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-medium text-white
             shadow-sm hover:bg-primary-dark transition-colors"
    >
      Request access
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
      </svg>
    </a>
  {/if}
</div>
