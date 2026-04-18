<script lang="ts">
  export type StatusKind = 'running' | 'analysed' | 'done' | 'draft';

  interface Props {
    status: StatusKind;
    label?: string;
  }

  let { status, label }: Props = $props();

  const STYLES: Record<StatusKind, { bg: string; color: string; dot: string; label: string }> = {
    running: {
      bg: 'bg-[color:var(--color-clay-tint)]',
      color: 'text-clay-ink',
      dot: 'bg-clay',
      label: 'running',
    },
    analysed: {
      bg: 'bg-[#E8EFE8]',
      color: 'text-[#3C5240]',
      dot: 'bg-moss',
      label: 'analysed',
    },
    done: {
      bg: 'bg-paper-2',
      color: 'text-ink-soft',
      dot: 'bg-ink-faint',
      label: 'closed',
    },
    draft: {
      bg: 'bg-paper-2',
      color: 'text-ink-faint',
      dot: 'bg-ink-faint',
      label: 'draft',
    },
  };

  const s = $derived(STYLES[status]);
</script>

<span
  class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] {s.bg} {s.color}"
>
  <span class="inline-block h-[5px] w-[5px] rounded-full {s.dot}"></span>
  {label ?? s.label}
</span>
