<script lang="ts">
  import ScatterDot from './ScatterDot.svelte';

  interface Props {
    size?: number;
    onclick?: () => void;
    class?: string;
  }

  let { size = 20, onclick, class: klass = '' }: Props = $props();

  const isButton = $derived(typeof onclick === 'function');
</script>

{#snippet mark()}
  <span
    class="inline-flex items-baseline leading-none tracking-[-0.015em] font-serif italic text-ink {klass}"
    style="font-size: {size}px;"
  >
    factori
    <span
      class="inline-flex items-center justify-center"
      style="width: 0.32em; height: 0.32em; margin: 0 0.05em 0.12em;"
    >
      <ScatterDot size="100%" />
    </span>
    <span class="text-clay-ink">al</span>
  </span>
{/snippet}

{#if isButton}
  <button type="button" {onclick} class="cursor-pointer bg-transparent border-none p-0">
    {@render mark()}
  </button>
{:else}
  {@render mark()}
{/if}
