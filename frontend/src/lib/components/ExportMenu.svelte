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

  const FORMATS: { format: ExportFormat; label: string; hint: string }[] = [
    { format: 'pdf', label: 'PDF', hint: 'Printable report with embedded plots' },
    { format: 'xlsx', label: 'Excel (.xlsx)', hint: 'Design + responses as spreadsheet tabs' },
    { format: 'csv', label: 'CSV', hint: 'Design matrix + responses, single sheet' },
    { format: 'md', label: 'Markdown', hint: 'Plain-text report for docs' },
  ];

  function slug(name: string): string {
    return (
      name
        .replace(/[^a-zA-Z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .toLowerCase() || 'experiment'
    );
  }

  async function download(format: ExportFormat, acknowledgeShare = false) {
    busy = true;
    error = null;
    try {
      const blob = await exportExperiment(experimentId, format, { acknowledgeShare });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${slug(experimentName)}.${format}`;
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
      class="absolute right-0 z-10 mt-1 w-64 origin-top-right rounded-md border border-gray-200 bg-white shadow-lg"
    >
      <ul class="py-1">
        {#each FORMATS as fmt (fmt.format)}
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
