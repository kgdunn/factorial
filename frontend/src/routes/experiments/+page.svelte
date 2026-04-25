<script lang="ts">
  import { goto } from '$app/navigation';
  import { experimentsState } from '$lib/state/experiments.svelte';
  import type { ExperimentStatus, ExperimentSummary } from '$lib/types';
  import TopBar from '$lib/components/brand/TopBar.svelte';
  import Btn from '$lib/components/brand/Btn.svelte';
  import StatusPill, { type StatusKind } from '$lib/components/brand/StatusPill.svelte';
  import Icon from '$lib/components/brand/Icon.svelte';
  import UploadWizardModal from '$lib/components/UploadWizardModal.svelte';

  let confirmDeleteId = $state<string | null>(null);
  let uploadOpen = $state(false);

  const FILTERS: { id: ExperimentStatus | null; label: string }[] = [
    { id: null, label: 'All' },
    { id: 'active', label: 'Running' },
    { id: 'completed', label: 'Analysed' },
    { id: 'draft', label: 'Drafts' },
  ];

  const STATUS_MAP: Record<ExperimentStatus, StatusKind> = {
    draft: 'draft',
    active: 'running',
    completed: 'analysed',
    archived: 'done',
  };

  $effect(() => {
    experimentsState.loadExperiments();
  });

  function formatRelative(dateStr: string): string {
    const d = new Date(dateStr);
    const diffMs = Date.now() - d.getTime();
    const hours = Math.floor(diffMs / 3_600_000);
    if (hours < 1) return 'just now';
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return 'yesterday';
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function designMeta(exp: ExperimentSummary): string {
    const dt = exp.design_type?.replace(/_/g, ' ') ?? '—';
    const runs = exp.n_runs != null ? `${exp.n_runs} runs` : '—';
    return `${dt} · ${runs}`;
  }

  let stats = $derived.by(() => {
    const running = experimentsState.experiments.filter((e) => e.status === 'active').length;
    const completed = experimentsState.experiments.filter((e) => e.status === 'completed').length;
    const draft = experimentsState.experiments.filter((e) => e.status === 'draft').length;
    return [
      { k: 'active', v: String(running), l: 'experiments running' },
      { k: 'pending', v: String(draft), l: 'waiting to start' },
      { k: 'decided', v: String(completed), l: 'analysed' },
      { k: 'total', v: String(experimentsState.total), l: 'experiments tracked' },
    ];
  });

  let totalPages = $derived(
    Math.max(1, Math.ceil(experimentsState.total / experimentsState.pageSize)),
  );

  async function handleDelete(id: string) {
    await experimentsState.remove(id);
    confirmDeleteId = null;
  }
</script>

<svelte:head>
  <title>Projects | factori.al</title>
</svelte:head>

<div class="h-full overflow-y-auto bg-paper">
  <TopBar breadcrumb="workspace · experiments" title={title} actions={actions} />

  {#snippet title()}Projects{/snippet}

  {#snippet actions()}
    <Btn variant="ghost" icon="search" size="sm">Search</Btn>
    <Btn variant="ghost" icon="upload" size="sm" onclick={() => (uploadOpen = true)}>
      Import from file
    </Btn>
    <Btn variant="primary" icon="plus" href="/chat">New experiment</Btn>
  {/snippet}

  <div class="px-9 pb-16 pt-7">
    <!-- Stat cards -->
    <div class="mb-8 grid grid-cols-4 gap-3.5">
      {#each stats as s (s.k)}
        <div class="rounded-xl border border-rule-soft bg-paper-2 px-5 py-4.5">
          <div class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-faint">
            {s.k}
          </div>
          <div class="my-0.5 font-serif italic text-[40px] leading-none text-ink">
            {s.v}
          </div>
          <div class="font-sans text-xs text-ink-soft">{s.l}</div>
        </div>
      {/each}
    </div>

    <!-- Filter row -->
    <div class="mb-3.5 flex items-baseline gap-3.5">
      <div class="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
        All experiments
      </div>
      <div class="ml-auto flex gap-1.5">
        {#each FILTERS as f (f.label)}
          {@const active = experimentsState.statusFilter === f.id}
          <button
            type="button"
            class="cursor-pointer rounded-full border px-2.5 py-1.5 font-sans text-xs transition-colors
                   {active
                     ? 'border-transparent bg-ink text-paper'
                     : 'border-rule bg-transparent text-ink-soft hover:bg-paper-2'}"
            onclick={() => experimentsState.setFilter(f.id)}
          >
            {f.label}
          </button>
        {/each}
      </div>
    </div>

    {#if experimentsState.error}
      <div class="mb-4 rounded-xl border border-[color:var(--color-negative)]/30 bg-[#FBECE8] px-4 py-3 font-sans text-sm text-[color:var(--color-negative)]">
        {experimentsState.error}
      </div>
    {/if}

    {#if experimentsState.isLoading}
      <div class="flex items-center justify-center py-16">
        <div
          class="h-7 w-7 animate-spin rounded-full border-[3px] border-clay border-t-transparent"
        ></div>
      </div>
    {:else if experimentsState.experiments.length === 0}
      <div
        class="rounded-xl border border-dashed border-rule bg-paper px-8 py-16 text-center"
      >
        <div class="font-serif italic text-[28px] leading-tight text-ink">
          No experiments yet.
        </div>
        <div class="mx-auto mt-2 max-w-md font-sans text-sm text-ink-soft">
          Start a conversation with the agent — name a response, a few factors,
          and roughly how many runs you can afford. The agent will draft a plan.
        </div>
        <div class="mt-6 flex justify-center gap-3">
          <Btn variant="primary" icon="arrow" href="/chat">Start with the agent</Btn>
          <Btn variant="ghost" icon="upload" onclick={() => (uploadOpen = true)}>
            Import from spreadsheet
          </Btn>
        </div>
      </div>
    {:else}
      <div class="overflow-hidden rounded-xl border border-rule bg-paper">
        <div
          class="grid grid-cols-[1.6fr_1fr_140px_140px_100px_40px] border-b border-rule-soft bg-paper-2 px-5 py-3.5 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint"
        >
          <div>Experiment</div>
          <div>Design</div>
          <div>Runs</div>
          <div>Status</div>
          <div>Updated</div>
          <div></div>
        </div>
        {#each experimentsState.experiments as exp, i (exp.id)}
          {@const kind = STATUS_MAP[exp.status]}
          <div
            class="grid grid-cols-[1.6fr_1fr_140px_140px_100px_40px] items-center px-5 py-4 transition-colors hover:bg-paper-2
                   {i < experimentsState.experiments.length - 1 ? 'border-b border-rule-soft' : ''}"
          >
            <div>
              <a
                href="/experiments/{exp.id}"
                class="font-serif italic text-[22px] leading-tight text-ink hover:text-clay-ink"
              >
                {exp.name}
              </a>
              <div class="mt-0.5 font-sans text-xs text-ink-faint">
                {exp.id.slice(0, 8)}
              </div>
            </div>
            <div class="font-mono text-xs text-ink-soft">{designMeta(exp)}</div>
            <div class="flex items-center gap-2.5 font-mono text-[11px] text-ink-soft">
              {#if exp.n_runs != null}
                {exp.n_runs}
              {:else}
                —
              {/if}
            </div>
            <div><StatusPill status={kind} /></div>
            <div class="font-mono text-[11px] text-ink-faint">
              {formatRelative(exp.updated_at)}
            </div>
            <div class="flex justify-end">
              {#if confirmDeleteId === exp.id}
                <div class="flex gap-1">
                  <button
                    type="button"
                    class="cursor-pointer rounded bg-[color:var(--color-negative)] px-2 py-1 font-sans text-[11px] text-white"
                    onclick={() => handleDelete(exp.id)}
                  >
                    Confirm
                  </button>
                  <button
                    type="button"
                    class="cursor-pointer rounded border border-rule px-2 py-1 font-sans text-[11px] text-ink-soft"
                    onclick={() => (confirmDeleteId = null)}
                  >
                    Cancel
                  </button>
                </div>
              {:else}
                <button
                  type="button"
                  onclick={() => (confirmDeleteId = exp.id)}
                  class="cursor-pointer rounded p-1 text-ink-faint transition-colors hover:text-[color:var(--color-negative)]"
                  aria-label="Delete experiment"
                >
                  <Icon name="dots" size={16} />
                </button>
              {/if}
            </div>
          </div>
        {/each}
      </div>

      {#if totalPages > 1}
        <div class="mt-5 flex items-center justify-between font-mono text-xs text-ink-faint">
          <span>
            {(experimentsState.page - 1) * experimentsState.pageSize + 1}–{Math.min(
              experimentsState.page * experimentsState.pageSize,
              experimentsState.total,
            )} of {experimentsState.total}
          </span>
          <div class="flex gap-2">
            <Btn
              variant="ghost"
              size="sm"
              disabled={experimentsState.page <= 1}
              onclick={() => experimentsState.goToPage(experimentsState.page - 1)}
            >
              Previous
            </Btn>
            <Btn
              variant="ghost"
              size="sm"
              disabled={experimentsState.page >= totalPages}
              onclick={() => experimentsState.goToPage(experimentsState.page + 1)}
            >
              Next
            </Btn>
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>

<UploadWizardModal
  open={uploadOpen}
  onClose={() => (uploadOpen = false)}
  onComplete={(experimentId) => {
    uploadOpen = false;
    goto(`/experiments/${experimentId}`);
  }}
/>
