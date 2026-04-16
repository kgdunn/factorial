<script lang="ts">
  import { page } from '$app/stores';
  import BaseChart from '$lib/components/BaseChart.svelte';
  import DesignMatrix from '$lib/components/DesignMatrix.svelte';
  import SignupCTA from '$lib/components/SignupCTA.svelte';
  import { exportPublicShare, fetchPublicShare } from '$lib/api/shares';
  import type { ExportFormat, PublicExperimentView } from '$lib/types';

  let view = $state<PublicExperimentView | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);

  $effect(() => {
    const token = $page.params.token;
    if (!token) return;
    loading = true;
    error = null;
    fetchPublicShare(token)
      .then((v) => {
        view = v;
      })
      .catch((e) => {
        error = e instanceof Error ? e.message : 'Unable to load share';
      })
      .finally(() => {
        loading = false;
      });
  });

  let matrix = $derived(() => {
    if (!view?.design_data) return [];
    return (
      (view.design_data.design_actual as Record<string, unknown>[]) ??
      (view.design_data.design_coded as Record<string, unknown>[]) ??
      []
    );
  });

  function getEchartsPlots(): Record<string, unknown>[] {
    if (!view?.design_data) return [];
    const plots = (view.design_data.plots as unknown[]) ?? [];
    if (!Array.isArray(plots)) return [];
    return plots
      .map((p) => {
        if (p && typeof p === 'object' && 'echarts' in p) {
          return (p as { echarts?: Record<string, unknown> }).echarts;
        }
        return p as Record<string, unknown>;
      })
      .filter((o): o is Record<string, unknown> => !!o && typeof o === 'object');
  }

  let plots = $derived(getEchartsPlots());

  function expiryLabel(v: PublicExperimentView): string {
    if (!v.expires_at) return 'Link never expires';
    const d = new Date(v.expires_at);
    return `Link expires ${d.toLocaleDateString()}`;
  }

  async function handleDownload(format: ExportFormat) {
    if (!view) return;
    try {
      const blob = await exportPublicShare(view.token, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${view.name.replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase()}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Download failed';
    }
  }
</script>

<svelte:head>
  <title>{view?.name ?? 'Shared Experiment'} | Agentic DOE</title>
</svelte:head>

<div class="min-h-full overflow-y-auto bg-gray-50">
  <div class="mx-auto max-w-5xl px-6 py-10">
    {#if loading}
      <div class="flex items-center justify-center py-12">
        <div class="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
      </div>
    {:else if error}
      <div class="rounded-lg bg-white p-8 text-center shadow-sm">
        <h1 class="text-xl font-semibold text-gray-800">Link unavailable</h1>
        <p class="mt-2 text-sm text-gray-600">{error}</p>
        <a
          href="/"
          class="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
        >
          Go to homepage
        </a>
      </div>
    {:else if view}
      <!-- Hero CTA -->
      <div class="mb-6">
        <SignupCTA token={view.token} variant="hero" />
      </div>

      <!-- Header -->
      <div class="mb-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="flex-1">
            <h1 class="text-2xl font-bold text-gray-800">{view.name}</h1>
            <div class="mt-2 flex flex-wrap items-center gap-4 text-sm text-gray-500">
              {#if view.design_type}
                <span>{view.design_type.replace(/_/g, ' ')}</span>
              {/if}
              {#if view.n_factors}
                <span>{view.n_factors} factors</span>
              {/if}
              {#if view.n_runs}
                <span>{view.n_runs} runs</span>
              {/if}
              {#if view.owner_display_name}
                <span>Shared by {view.owner_display_name}</span>
              {/if}
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500">
              <span class="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-600">
                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><path d="M10 12a2 2 0 100-4 2 2 0 000 4z" /><path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" /></svg>
                Viewed {view.view_count} {view.view_count === 1 ? 'time' : 'times'}
              </span>
              <span>{expiryLabel(view)}</span>
              {#if !view.allow_results}
                <span class="rounded-full bg-yellow-50 px-2 py-0.5 text-yellow-700">Design only — responses hidden</span>
              {/if}
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              class="rounded-md border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
              onclick={() => handleDownload('pdf')}
            >
              Download PDF
            </button>
            <button
              class="rounded-md border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
              onclick={() => handleDownload('md')}
            >
              Download Markdown
            </button>
            {#if view.allow_results}
              <button
                class="rounded-md border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
                onclick={() => handleDownload('xlsx')}
              >
                Download Excel
              </button>
              <button
                class="rounded-md border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
                onclick={() => handleDownload('csv')}
              >
                Download CSV
              </button>
            {/if}
          </div>
        </div>
      </div>

      <!-- Design Matrix -->
      {#if matrix().length > 0}
        <div class="mb-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 class="mb-4 text-lg font-semibold text-gray-800">Design Matrix</h2>
          <DesignMatrix matrix={matrix()} />
        </div>
      {/if}

      <!-- Plots -->
      {#if plots.length > 0}
        <div class="mb-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 class="mb-4 text-lg font-semibold text-gray-800">Analysis</h2>
          {#each plots as option, i (i)}
            <div id="plot-{i}" class="mb-4">
              <BaseChart {option} height="420px" />
            </div>
          {/each}
        </div>
      {/if}

      <!-- Footer CTA -->
      <div class="mt-8">
        <SignupCTA token={view.token} variant="footer" />
      </div>

      <p class="mt-6 text-center text-xs text-gray-400">
        This is a read-only snapshot shared via Agentic DOE.
      </p>
    {/if}
  </div>
</div>
