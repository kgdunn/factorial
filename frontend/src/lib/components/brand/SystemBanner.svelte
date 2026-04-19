<script lang="ts">
  import { anthropicStatus } from '$lib/state/anthropicStatus.svelte';

  const visible = $derived(anthropicStatus.pollFailed || (anthropicStatus.status !== 'ok' && anthropicStatus.status !== 'unknown'));

  const tone = $derived.by(() => {
    if (anthropicStatus.pollFailed) return 'down';
    return anthropicStatus.status;
  });

  const message = $derived.by(() => {
    if (anthropicStatus.pollFailed) return 'Cannot reach the server. Check your connection.';
    if (anthropicStatus.status === 'down') return 'The AI service is currently unavailable. Please try again in a moment.';
    if (anthropicStatus.status === 'slow') return 'Responses may be slower than usual right now.';
    return '';
  });
</script>

{#if visible}
  <div
    role="status"
    aria-live="polite"
    class="flex items-center justify-center gap-2 px-4 py-2 font-sans text-sm {tone === 'slow'
      ? 'bg-[color:var(--color-clay-tint)] text-clay-ink'
      : 'bg-[color:var(--color-negative)] text-white'}"
  >
    <span>{message}</span>
  </div>
{/if}
