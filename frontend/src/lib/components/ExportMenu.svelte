<script lang="ts">
  import { exportExperiment } from '$lib/api/experiments';
  import type { ExportFormat } from '$lib/types';

  interface Props {
    experimentId: string;
    experimentName: string;
  }

  let { experimentId, experimentName }: Props = $props();

  let open = $state(false);
  let confirmPdf = $state(false);
  let busy = $state(false);
  let error = $state<string | null>(null);

  // ``ext`` is the filename extension; it usually matches ``format`` but
  // differs for ``md_code`` (the backend emits ``.md``, not ``.md_code``).
  interface FormatEntry {
    format: ExportFormat;
    label: string;
    hint: string;
    ext: string;
  }

  const REPORT_FORMATS: FormatEntry[] = [
    { format: 'pdf', label: 'PDF', hint: 'Printable report with embedded plots', ext: 'pdf' },
    { format: 'xlsx', label: 'Excel (.xlsx)', hint: 'Design + responses as spreadsheet tabs', ext: 'xlsx' },
    { format: 'csv', label: 'CSV', hint: 'Design matrix + responses, single sheet', ext: 'csv' },
    { format: 'md', label: 'Markdown', hint: 'Plain-text report for docs', ext: 'md' },
  ];

  // Reproducible code formats — replay the recorded tool calls locally
  // via ``process_improve.tool_spec.execute_tool_call``.  The ``zip``
  // bundle is the primary deliverable (code + data + pinned deps +
  // README); the other three are individual artifacts for users who
  // want just one file.  See ``docs/architecture/reproducibility.md``.
  const CODE_FORMATS: FormatEntry[] = [
    { format: 'zip', label: 'Reproducible bundle (.zip)', hint: 'Code + data + README — re-run locally', ext: 'zip' },
    { format: 'ipynb', label: 'Jupyter notebook', hint: 'Narrative + runnable cells', ext: 'ipynb' },
    { format: 'py', label: 'Python script', hint: 'execute_tool_call() per step', ext: 'py' },
    { format: 'md_code', label: 'Literate Markdown', hint: 'Prose with fenced code blocks', ext: 'md' },
  ];

  function slug(name: string): string {
    return (
      name
        .replace(/[^a-zA-Z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .toLowerCase() || 'experiment'
    );
  }

  function extFor(format: ExportFormat): string {
    return [...REPORT_FORMATS, ...CODE_FORMATS].find((f) => f.format === format)?.ext ?? format;
  }

  async function download(format: ExportFormat, acknowledgeShare = false) {
    busy = true;
    error = null;
    try {
      const blob = await exportExperiment(experimentId, format, { acknowledgeShare });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${slug(experimentName)}.${extFor(format)}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      open = false;
      confirmPdf = false;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Export failed';
    } finally {
      busy = false;
    }
  }

  function handlePick(format: ExportFormat) {
    if (format === 'pdf') {
      confirmPdf = true;
      return;
    }
    download(format);
  }
</script>

<div class="relative inline-block">
  <button
    type="button"
    class="rounded-lg border border-gray-300 bg-white px-4 py-1.5 text-sm font-medium text-gray-700
           hover:bg-gray-50 transition-colors"
    onclick={() => (open = !open)}
    aria-haspopup="menu"
    aria-expanded={open}
  >
    Export
    <svg class="ml-1 inline h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
    </svg>
  </button>

  {#if open}
    <div
      role="menu"
      class="absolute right-0 z-10 mt-1 w-72 origin-top-right rounded-md border border-gray-200 bg-white shadow-lg"
    >
      <div class="border-b border-gray-100 px-4 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
        Report
      </div>
      <ul class="py-1">
        {#each REPORT_FORMATS as fmt (fmt.format)}
          <li>
            <button
              type="button"
              class="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              disabled={busy}
              onclick={() => handlePick(fmt.format)}
            >
              <div class="font-medium">{fmt.label}</div>
              <div class="text-xs text-gray-500">{fmt.hint}</div>
            </button>
          </li>
        {/each}
      </ul>
      <div class="border-t border-gray-100 px-4 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
        Reproducible code
      </div>
      <ul class="py-1">
        {#each CODE_FORMATS as fmt (fmt.format)}
          <li>
            <button
              type="button"
              class="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              disabled={busy}
              onclick={() => handlePick(fmt.format)}
            >
              <div class="font-medium">{fmt.label}</div>
              <div class="text-xs text-gray-500">{fmt.hint}</div>
            </button>
          </li>
        {/each}
      </ul>
      {#if error}
        <div class="border-t border-gray-100 px-4 py-2 text-xs text-negative">{error}</div>
      {/if}
    </div>
  {/if}

  {#if confirmPdf}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Include analysis plots?</h3>
        <p class="mb-4 text-sm text-gray-600">
          The PDF embeds each analysis plot as a static image. Interactive versions
          will still be available via the shareable link in the report footer.
          Continue?
        </p>
        <div class="flex justify-end gap-2">
          <button
            class="rounded-md border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            onclick={() => (confirmPdf = false)}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
            onclick={() => download('pdf', true)}
            disabled={busy}
          >
            {busy ? 'Preparing…' : 'Download PDF'}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>
