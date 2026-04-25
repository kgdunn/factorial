<script lang="ts">
  /**
   * Multi-step modal that guides the user through:
   *   pick → parsing → (clarify → parsing) → confirm → save
   * for an Excel/CSV DOE design upload.
   */
  import {
    finalizeUpload,
    submitUploadAnswers,
    uploadDesign,
  } from '$lib/api/uploads';
  import type {
    ClarifyingQuestion,
    ParsedDesignPayload,
  } from '$lib/types';
  import ExperimentDataTable from './ExperimentDataTable.svelte';

  interface Props {
    open: boolean;
    onClose: () => void;
    onComplete: (experimentId: string) => void;
  }

  let { open, onClose, onComplete }: Props = $props();

  type View = 'pick' | 'parsing' | 'clarify' | 'confirm' | 'error';

  let view = $state<View>('pick');
  let uploadId = $state<string | null>(null);
  let parsed = $state<ParsedDesignPayload | null>(null);
  let questions = $state<ClarifyingQuestion[]>([]);
  let answers = $state<Record<string, string>>({});
  let errorMessage = $state('');
  let experimentName = $state('');
  let dragActive = $state(false);

  function reset() {
    view = 'pick';
    uploadId = null;
    parsed = null;
    questions = [];
    answers = {};
    errorMessage = '';
    experimentName = '';
    dragActive = false;
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleFile(file: File) {
    view = 'parsing';
    errorMessage = '';
    try {
      const resp = await uploadDesign(file);
      uploadId = resp.upload_id;
      experimentName = file.name.replace(/\.[^.]+$/, '') || 'Imported design';
      if (resp.status === 'parsed' && resp.parsed) {
        parsed = resp.parsed;
        view = 'confirm';
      } else if (resp.status === 'needs_clarification' && resp.questions) {
        questions = resp.questions;
        answers = Object.fromEntries(resp.questions.map((q) => [q.id, q.options?.[0] ?? '']));
        view = 'clarify';
      } else {
        errorMessage = 'Unexpected response from the server.';
        view = 'error';
      }
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : 'Upload failed';
      view = 'error';
    }
  }

  async function handleAnswers() {
    if (!uploadId) return;
    view = 'parsing';
    errorMessage = '';
    try {
      const resp = await submitUploadAnswers(uploadId, answers);
      if (resp.status === 'parsed' && resp.parsed) {
        parsed = resp.parsed;
        view = 'confirm';
      } else {
        errorMessage = 'The server still needs clarification. Try uploading again.';
        view = 'error';
      }
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : 'Failed to submit answers';
      view = 'error';
    }
  }

  async function handleSave() {
    if (!uploadId || !parsed) return;
    view = 'parsing';
    errorMessage = '';
    try {
      const exp = await finalizeUpload(uploadId, {
        name: experimentName.trim() || undefined,
        parsed,
      });
      onComplete(exp.id);
      reset();
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : 'Failed to save experiment';
      view = 'error';
    }
  }

  function handleCellEdit(rowIdx: number, col: string, value: string) {
    if (!parsed) return;
    const next = [...parsed.design_actual];
    next[rowIdx] = { ...next[rowIdx], [col]: value };
    parsed = { ...parsed, design_actual: next };
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    dragActive = false;
    const file = e.dataTransfer?.files?.[0];
    if (file) void handleFile(file);
  }

  function onPick(e: Event) {
    const target = e.target as HTMLInputElement;
    const file = target.files?.[0];
    if (file) void handleFile(file);
    target.value = '';
  }

  const factorColumns = $derived(parsed?.factors.map((f) => f.name) ?? []);
  const responseColumns = $derived(parsed?.responses.map((r) => r.name) ?? []);
</script>

{#if open}
  <div
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 px-4"
    role="dialog"
    aria-modal="true"
    aria-label="Import experiment from spreadsheet"
  >
    <button
      type="button"
      class="absolute inset-0 cursor-default"
      aria-label="Close dialog"
      onclick={handleClose}
    ></button>
    <div class="relative z-10 flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg bg-white p-6 shadow-xl">
      <div class="mb-4 flex items-start justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-800">Import from spreadsheet</h2>
          <p class="text-sm text-gray-500">
            Upload an Excel or CSV file. Claude will detect factors, levels, responses, and any results already entered.
          </p>
        </div>
        <button class="text-gray-400 hover:text-gray-700" aria-label="Close" onclick={handleClose}>
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-auto">
        {#if view === 'pick'}
          <label
            class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition {dragActive ? 'border-primary bg-blue-50/40' : 'border-gray-300 hover:border-gray-400'}"
            ondragover={(e) => {
              e.preventDefault();
              dragActive = true;
            }}
            ondragleave={() => (dragActive = false)}
            ondrop={onDrop}
          >
            <svg class="mb-3 h-10 w-10 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 7.5m0 0L7.5 12M12 7.5v9" /></svg>
            <span class="text-sm font-medium text-gray-700">Drop a .xlsx or .csv here</span>
            <span class="mt-1 text-xs text-gray-500">or click to choose a file</span>
            <input class="sr-only" type="file" accept=".xlsx,.csv" onchange={onPick} />
          </label>
        {:else if view === 'parsing'}
          <div class="flex flex-col items-center gap-3 py-12 text-center">
            <div class="h-8 w-8 animate-spin rounded-full border-2 border-gray-200 border-t-primary"></div>
            <p class="text-sm text-gray-700">Analysing your design with Claude…</p>
          </div>
        {:else if view === 'clarify'}
          <div class="space-y-4">
            <p class="text-sm text-gray-600">
              Claude needs a bit more information about the file. Answer the questions below to continue.
            </p>
            {#each questions as q (q.id)}
              <div>
                <p class="mb-1 text-sm font-medium text-gray-700">{q.question}</p>
                {#if q.column_ref}
                  <p class="mb-1 text-xs text-gray-400">Column: <code>{q.column_ref}</code></p>
                {/if}
                {#if q.options && q.options.length > 0}
                  <div class="flex flex-wrap gap-2">
                    {#each q.options as opt (opt)}
                      <label class="inline-flex cursor-pointer items-center gap-1 rounded-md border border-gray-300 px-3 py-1 text-sm {answers[q.id] === opt ? 'border-primary bg-blue-50 text-primary' : 'text-gray-600'}">
                        <input
                          type="radio"
                          class="sr-only"
                          name={q.id}
                          value={opt}
                          checked={answers[q.id] === opt}
                          onchange={() => (answers = { ...answers, [q.id]: opt })}
                        />
                        {opt}
                      </label>
                    {/each}
                  </div>
                {:else}
                  <input
                    class="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                    bind:value={answers[q.id]}
                  />
                {/if}
              </div>
            {/each}
            <div class="flex justify-end">
              <button class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90" onclick={handleAnswers}>
                Submit answers
              </button>
            </div>
          </div>
        {:else if view === 'confirm' && parsed}
          <div class="space-y-4">
            <div>
              <label class="mb-1 block text-sm font-medium text-gray-700" for="upload-experiment-name">
                Experiment name
              </label>
              <input
                id="upload-experiment-name"
                class="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                bind:value={experimentName}
              />
            </div>
            <p class="text-xs text-gray-500">
              Orientation: <strong>{parsed.orientation}</strong>
              · {parsed.factors.length} factor{parsed.factors.length === 1 ? '' : 's'}
              · {parsed.responses.length} response{parsed.responses.length === 1 ? '' : 's'}
              · {parsed.design_actual.length} run{parsed.design_actual.length === 1 ? '' : 's'}
              · click any cell to edit before saving
            </p>
            <ExperimentDataTable
              rows={parsed.design_actual}
              {factorColumns}
              {responseColumns}
              editable
              onCellEdit={handleCellEdit}
            />
            <div class="flex justify-end gap-2">
              <button
                class="rounded-md border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                onclick={handleClose}
              >
                Cancel
              </button>
              <button
                class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90"
                onclick={handleSave}
              >
                Save as experiment
              </button>
            </div>
          </div>
        {:else if view === 'error'}
          <div class="space-y-3 py-8 text-center">
            <p class="rounded-md bg-red-50 px-4 py-3 text-sm text-negative">{errorMessage}</p>
            <button
              class="rounded-md border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
              onclick={reset}
            >
              Try again
            </button>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
