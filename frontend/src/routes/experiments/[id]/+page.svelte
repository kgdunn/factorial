<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { experimentsState } from '$lib/state/experiments.svelte';
  import ExperimentDataTable from '$lib/components/ExperimentDataTable.svelte';
  import DesignEvaluationBlock from '$lib/components/DesignEvaluationBlock.svelte';
  import ExportMenu from '$lib/components/ExportMenu.svelte';
  import ResultsEntryForm from '$lib/components/ResultsEntryForm.svelte';
  import ShareModal from '$lib/components/ShareModal.svelte';
  import type { ExperimentStatus } from '$lib/types';

  const STATUS_OPTIONS: ExperimentStatus[] = ['draft', 'active', 'completed', 'archived'];

  const STATUS_COLORS: Record<ExperimentStatus, string> = {
    draft: 'bg-gray-100 text-gray-700',
    active: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    archived: 'bg-yellow-100 text-yellow-700',
  };

  let isEditingName = $state(false);
  let editName = $state('');
  let showCoded = $state(false);
  let confirmDelete = $state(false);
  let saveSuccess = $state(false);
  let shareModalOpen = $state(false);

  // Load experiment when page params change
  $effect(() => {
    const id = $page.params.id;
    if (id) {
      experimentsState.loadExperiment(id);
    }
  });

  let exp = $derived(experimentsState.currentExperiment);

  let designMatrix = $derived(() => {
    if (!exp?.design_data) return [];
    if (showCoded) {
      return (exp.design_data.design_coded as Record<string, unknown>[]) ?? [];
    }
    return (
      (exp.design_data.design_actual as Record<string, unknown>[]) ??
      (exp.design_data.design_matrix as Record<string, unknown>[]) ??
      []
    );
  });

  function startEditName() {
    if (!exp) return;
    editName = exp.name;
    isEditingName = true;
  }

  async function saveName() {
    if (!exp || !editName.trim()) return;
    await experimentsState.update(exp.id, { name: editName.trim() });
    isEditingName = false;
  }

  function cancelEditName() {
    isEditingName = false;
  }

  async function handleStatusChange(e: Event) {
    if (!exp) return;
    const target = e.target as HTMLSelectElement;
    await experimentsState.update(exp.id, { status: target.value });
  }

  async function handleDelete() {
    if (!exp) return;
    await experimentsState.remove(exp.id);
    goto('/experiments');
  }

  async function handleSaveResults(results: Record<string, unknown>[]) {
    if (!exp) return;
    await experimentsState.addResults(exp.id, results);
    saveSuccess = true;
    setTimeout(() => { saveSuccess = false; }, 3000);
  }

  async function handleReEvaluate(payload: {
    assumed_sigma?: number;
    effect_size?: number;
    alpha?: number;
  }) {
    if (!exp) return;
    await experimentsState.reEvaluate(exp.id, payload);
  }
</script>

<svelte:head>
  <title>{exp?.name ?? 'Experiment'} | Factorial</title>
</svelte:head>

<div class="h-full overflow-y-auto">
  <div class="mx-auto max-w-5xl px-6 py-8">
    <!-- Back link -->
    <a
      href="/experiments"
      class="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-primary transition-colors"
    >
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
      Back to Experiments
    </a>

    {#if experimentsState.isLoading}
      <div class="flex items-center justify-center py-12">
        <div class="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
      </div>
    {:else if experimentsState.error}
      <div class="rounded-lg bg-red-50 px-4 py-3 text-sm text-negative">
        {experimentsState.error}
      </div>
    {:else if exp}
      <!-- Header Section -->
      <div class="mb-8 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1">
            {#if isEditingName}
              <div class="flex items-center gap-2">
                <input
                  type="text"
                  class="flex-1 rounded border border-gray-300 px-3 py-1.5 text-lg font-bold
                         focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  bind:value={editName}
                  onkeydown={(e) => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') cancelEditName(); }}
                />
                <button
                  class="rounded bg-primary px-3 py-1.5 text-sm text-white hover:bg-primary-dark"
                  onclick={saveName}
                >
                  Save
                </button>
                <button
                  class="rounded bg-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-300"
                  onclick={cancelEditName}
                >
                  Cancel
                </button>
              </div>
            {:else}
              <h1
                class="text-2xl font-bold text-gray-800 cursor-pointer hover:text-primary transition-colors"
                onclick={startEditName}
                title="Click to edit"
              >
                {exp.name}
              </h1>
            {/if}

            <div class="mt-2 flex items-center gap-4 text-sm text-gray-500">
              {#if exp.design_type}
                <span>{exp.design_type.replace(/_/g, ' ')}</span>
              {/if}
              {#if exp.n_factors}
                <span>{exp.n_factors} factors</span>
              {/if}
              {#if exp.n_runs}
                <span>{exp.n_runs} runs</span>
              {/if}
            </div>
          </div>

          <div class="flex items-center gap-3">
            <!-- Status dropdown -->
            <select
              class="rounded border border-gray-300 px-3 py-1.5 text-sm
                     focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary
                     {STATUS_COLORS[exp.status as ExperimentStatus] ?? ''}"
              value={exp.status}
              onchange={handleStatusChange}
            >
              {#each STATUS_OPTIONS as status}
                <option value={status}>{status.charAt(0).toUpperCase() + status.slice(1)}</option>
              {/each}
            </select>

            <!-- Export + Share -->
            <ExportMenu experimentId={exp.id} experimentName={exp.name} />
            <button
              class="rounded-lg border border-primary px-4 py-1.5 text-sm font-medium text-primary
                     hover:bg-blue-50 transition-colors"
              onclick={() => (shareModalOpen = true)}
            >
              Share
            </button>

            <!-- Return to Chat -->
            {#if exp.conversation_id}
              <a
                href="/chat?conversation_id={exp.conversation_id}"
                class="rounded-lg border border-primary px-4 py-1.5 text-sm font-medium text-primary
                       hover:bg-blue-50 transition-colors"
              >
                Return to Chat
              </a>
            {/if}

            <!-- Delete -->
            {#if confirmDelete}
              <button
                class="rounded bg-negative px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
                onclick={handleDelete}
              >
                Confirm Delete
              </button>
              <button
                class="rounded bg-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-300"
                onclick={() => (confirmDelete = false)}
              >
                Cancel
              </button>
            {:else}
              <button
                class="rounded px-3 py-1.5 text-sm text-gray-400 hover:bg-red-50 hover:text-negative transition-colors"
                onclick={() => (confirmDelete = true)}
              >
                Delete
              </button>
            {/if}
          </div>
        </div>
      </div>

      <!-- Design Matrix Section -->
      {#if exp.design_data}
        <div class="mb-8 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-lg font-semibold text-gray-800">Design Matrix</h2>
            {#if exp.design_data.design_coded && exp.design_data.design_actual}
              <button
                class="rounded border border-gray-300 px-3 py-1 text-xs text-gray-500 hover:bg-gray-50"
                onclick={() => (showCoded = !showCoded)}
              >
                {showCoded ? 'Show Actual' : 'Show Coded'}
              </button>
            {/if}
          </div>
          <ExperimentDataTable
            rows={designMatrix()}
            factorColumns={designMatrix().length > 0 ? Object.keys(designMatrix()[0]) : []}
          />
        </div>
      {/if}

      <!-- Evaluation Section -->
      {#if exp.evaluation_data}
        <div class="mb-8">
          <DesignEvaluationBlock
            evaluation={exp.evaluation_data}
            onReEvaluate={handleReEvaluate}
          />
        </div>
      {/if}

      <!-- Results Entry Section -->
      {#if exp.design_data}
        <div class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          {#if saveSuccess}
            <div class="mb-4 rounded-lg bg-green-50 px-4 py-2 text-sm text-positive">
              Results saved successfully.
            </div>
          {/if}
          <ResultsEntryForm
            designData={exp.design_data}
            resultsData={exp.results_data}
            onSave={handleSaveResults}
          />
        </div>
      {/if}

      <ShareModal
        experimentId={exp.id}
        bind:open={shareModalOpen}
        onClose={() => (shareModalOpen = false)}
      />
    {/if}
  </div>
</div>
