<script lang="ts">
  import type { Snippet } from 'svelte';

  export interface Tab {
    label: string;
    active?: boolean;
    onclick?: () => void;
  }

  interface Props {
    breadcrumb?: string;
    title: Snippet;
    actions?: Snippet;
    tabs?: Tab[];
  }

  let { breadcrumb, title, actions, tabs }: Props = $props();
</script>

<div class="border-b border-rule bg-paper">
  <div class="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:gap-5 sm:px-9 sm:py-5">
    <div class="min-w-0 flex-1">
      {#if breadcrumb}
        <div
          class="mb-1 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint"
        >
          {breadcrumb}
        </div>
      {/if}
      <div
        class="font-serif italic text-[26px] leading-[1.1] text-ink tracking-[-0.01em] sm:text-[32px]"
      >
        {@render title()}
      </div>
    </div>
    {#if actions}
      <div class="flex flex-wrap gap-2.5 sm:flex-nowrap sm:justify-end">
        {@render actions()}
      </div>
    {/if}
  </div>
  {#if tabs && tabs.length}
    <div class="flex gap-1 overflow-x-auto px-5 sm:px-7">
      {#each tabs as tab (tab.label)}
        <button
          type="button"
          onclick={tab.onclick}
          class="-mb-px cursor-pointer border-b-2 px-4 py-2.5 font-sans text-[13px] transition-colors
                 {tab.active
                   ? 'border-clay text-ink'
                   : 'border-transparent text-ink-faint hover:text-ink-soft'}"
        >
          {tab.label}
        </button>
      {/each}
    </div>
  {/if}
</div>
