<script lang="ts">
  /**
   * Modal wrapper around `<ExperimentDataTable>`.
   *
   * Presentation only — the consumer wires the F2 keyboard shortcut
   * (or button click) and toggles `open`. Closes on Escape or
   * backdrop click.
   */
  import ExperimentDataTable from './ExperimentDataTable.svelte';

  interface Props {
    open: boolean;
    onClose: () => void;
    title?: string;
    rows: Record<string, unknown>[];
    factorColumns: string[];
    responseColumns?: string[];
  }

  let {
    open,
    onClose,
    title = 'Experiment data',
    rows,
    factorColumns,
    responseColumns = [],
  }: Props = $props();

  let copied = $state(false);

  function handleBackdropKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  }

  function copyAsTsv() {
    const cols = [...factorColumns, ...responseColumns];
    const header = cols.join('\t');
    const lines = rows.map((r) =>
      cols.map((c) => (r[c] === null || r[c] === undefined ? '' : String(r[c]))).join('\t'),
    );
    const tsv = [header, ...lines].join('\n');
    navigator.clipboard
      ?.writeText(tsv)
      .then(() => {
        copied = true;
        setTimeout(() => (copied = false), 2000);
      })
      .catch(() => {
        /* clipboard blocked — silent */
      });
  }
</script>

<svelte:window onkeydown={open ? handleBackdropKey : undefined} />

{#if open}
  <div
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 px-4"
    role="dialog"
    aria-modal="true"
    aria-label={title}
  >
    <button
      type="button"
      class="absolute inset-0 cursor-default"
      aria-label="Close dialog"
      onclick={onClose}
    ></button>
    <div class="relative z-10 flex max-h-[90vh] w-full max-w-5xl flex-col rounded-lg bg-white p-6 shadow-xl">
      <div class="mb-4 flex items-start justify-between">
        <h2 class="text-lg font-semibold text-gray-800">{title}</h2>
        <div class="flex items-center gap-2">
          <button
            class="rounded-md border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
            onclick={copyAsTsv}
            disabled={rows.length === 0}
          >
            {copied ? 'Copied!' : 'Copy as TSV'}
          </button>
          <button
            class="text-gray-400 hover:text-gray-700"
            aria-label="Close"
            onclick={onClose}
          >
            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg>
          </button>
        </div>
      </div>
      <div class="min-h-0 flex-1 overflow-auto">
        <ExperimentDataTable {rows} {factorColumns} {responseColumns} />
      </div>
    </div>
  </div>
{/if}
