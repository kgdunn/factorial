<script lang="ts">
  import type { DetailLevel } from '$lib/state/chat.svelte';

  interface Props {
    value: DetailLevel;
    onchange: (level: DetailLevel) => void;
    disabled?: boolean;
  }

  let { value, onchange, disabled = false }: Props = $props();

  const OPTIONS: readonly { id: DetailLevel; label: string }[] = [
    { id: 'beginner', label: 'Beginner' },
    { id: 'intermediate', label: 'Intermediate' },
    { id: 'expert', label: 'Expert' },
  ];
</script>

<div class="flex items-center gap-2.5">
  <span
    class="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint"
  >
    detail
  </span>
  <div
    role="radiogroup"
    aria-label="Response detail level"
    class="inline-flex rounded-full border border-rule-soft bg-paper-2 p-0.5"
  >
    {#each OPTIONS as option (option.id)}
      {@const selected = value === option.id}
      <button
        type="button"
        role="radio"
        aria-checked={selected}
        {disabled}
        onclick={() => onchange(option.id)}
        class="cursor-pointer rounded-full px-3 py-1 font-sans text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 {selected
          ? 'bg-ink text-paper'
          : 'text-ink-soft hover:text-ink'}"
      >
        {option.label}
      </button>
    {/each}
  </div>
</div>
