<script lang="ts">
  import { page } from '$app/stores';
  import { authState } from '$lib/state/auth.svelte';
  import FeedbackDialog from './FeedbackDialog.svelte';

  let open = $state(false);

  const visible = $derived(
    authState.isAuthenticated && !$page.url.pathname.startsWith('/admin'),
  );
</script>

{#if visible}
  <button
    type="button"
    class="fixed right-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-50 flex items-center gap-2 rounded-full bg-clay p-3 font-sans text-sm font-medium text-white shadow-lg transition-colors hover:bg-clay-ink focus-visible:ring-2 focus-visible:ring-clay focus-visible:ring-offset-2 focus-visible:outline-none sm:right-5 sm:bottom-5 sm:px-4 sm:py-2.5"
    aria-label="Give feedback"
    onclick={() => (open = true)}
  >
    <svg
      width="16"
      height="16"
      viewBox="0 0 20 20"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linejoin="round"
    >
      <path d="M3 4 H17 V13 H11 L7 16 V13 H3 Z" />
    </svg>
    <span class="hidden sm:inline">Give feedback</span>
  </button>
{/if}

<FeedbackDialog bind:open />
