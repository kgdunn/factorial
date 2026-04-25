<script lang="ts">
  import BaseChart from './BaseChart.svelte';
  import ExperimentDataTable from './ExperimentDataTable.svelte';

  interface Props {
    evaluation: Record<string, unknown>;
    onReEvaluate?: (payload: {
      assumed_sigma?: number;
      effect_size?: number;
      alpha?: number;
    }) => Promise<void> | void;
  }

  let { evaluation, onReEvaluate }: Props = $props();

  let sigmaInput = $state('');
  let effectInput = $state('');
  let alphaInput = $state('');
  let running = $state(false);

  function labelise(key: string): string {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function isScalar(value: unknown): value is string | number | boolean | null {
    return (
      value === null ||
      typeof value === 'string' ||
      typeof value === 'number' ||
      typeof value === 'boolean'
    );
  }

  function isTableRows(value: unknown): value is Record<string, unknown>[] {
    return (
      Array.isArray(value) &&
      value.length > 0 &&
      value.every((row) => typeof row === 'object' && row !== null && !Array.isArray(row))
    );
  }

  function isScalarDict(value: unknown): value is Record<string, string | number | boolean | null> {
    return (
      typeof value === 'object' &&
      value !== null &&
      !Array.isArray(value) &&
      Object.values(value).every(isScalar)
    );
  }

  type SummaryEntry = [string, string | number | boolean | null];
  type TableEntry = { title: string; columns: string[]; rows: Record<string, unknown>[] };

  let summary = $derived.by<SummaryEntry[]>(() => {
    const out: SummaryEntry[] = [];
    for (const [key, value] of Object.entries(evaluation)) {
      if (key === 'error') continue;
      if (isScalar(value)) out.push([labelise(key), value]);
    }
    return out;
  });

  let tables = $derived.by<TableEntry[]>(() => {
    const out: TableEntry[] = [];
    for (const [key, value] of Object.entries(evaluation)) {
      if (key === 'error') continue;
      if (isTableRows(value)) {
        const columns = Array.from(
          value.reduce<Set<string>>((acc, row) => {
            Object.keys(row).forEach((k) => acc.add(k));
            return acc;
          }, new Set<string>()),
        );
        out.push({ title: labelise(key), columns, rows: value });
      } else if (isScalarDict(value)) {
        out.push({
          title: labelise(key),
          columns: ['name', 'value'],
          rows: Object.entries(value).map(([name, v]) => ({ name, value: v })),
        });
      }
    }
    return out;
  });

  // Try to detect a power-per-term dict so we can render a bar chart.
  let powerEntries = $derived.by<Array<{ term: string; power: number }> | null>(() => {
    const power = (evaluation.power ?? evaluation.power_analysis) as unknown;
    if (!power || typeof power !== 'object' || Array.isArray(power)) return null;
    const entries: Array<{ term: string; power: number }> = [];
    for (const [term, value] of Object.entries(power as Record<string, unknown>)) {
      if (typeof value === 'number') entries.push({ term, power: value });
    }
    return entries.length > 0 ? entries : null;
  });

  let powerOption = $derived.by<Record<string, unknown> | null>(() => {
    if (!powerEntries) return null;
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: '8%', right: '4%', bottom: '10%', top: '8%', containLabel: true },
      xAxis: {
        type: 'category',
        data: powerEntries.map((p) => p.term),
        axisLabel: { rotate: 30 },
      },
      yAxis: { type: 'value', min: 0, max: 1, name: 'Power' },
      series: [
        {
          type: 'bar',
          data: powerEntries.map((p) => +p.power.toFixed(3)),
          itemStyle: { color: '#2563eb' },
        },
      ],
    };
  });

  async function handleReEvaluate(e: Event) {
    e.preventDefault();
    if (!onReEvaluate || running) return;
    running = true;
    try {
      const payload: { assumed_sigma?: number; effect_size?: number; alpha?: number } = {};
      if (sigmaInput.trim()) payload.assumed_sigma = Number(sigmaInput);
      if (effectInput.trim()) payload.effect_size = Number(effectInput);
      if (alphaInput.trim()) payload.alpha = Number(alphaInput);
      await onReEvaluate(payload);
    } finally {
      running = false;
    }
  }
</script>

<div class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
  <h2 class="mb-4 text-lg font-semibold text-gray-800">Evaluation</h2>

  {#if summary.length > 0}
    <dl class="mb-6 grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-4">
      {#each summary as [label, value]}
        <div class="rounded bg-gray-50 px-3 py-2">
          <dt class="text-xs uppercase text-gray-500">{label}</dt>
          <dd class="mt-1 font-mono text-sm text-gray-800">
            {value === null ? '—' : typeof value === 'number' ? (+value).toPrecision(4) : value}
          </dd>
        </div>
      {/each}
    </dl>
  {/if}

  {#if powerOption}
    <div class="mb-6">
      <h3 class="mb-2 text-sm font-semibold text-gray-700">Power per term</h3>
      <BaseChart option={powerOption} height="260px" />
    </div>
  {/if}

  {#each tables as table}
    <div class="mb-6">
      <h3 class="mb-2 text-sm font-semibold text-gray-700">{table.title}</h3>
      <ExperimentDataTable rows={table.rows} factorColumns={table.columns} />
    </div>
  {/each}

  {#if onReEvaluate}
    <form
      class="mt-6 flex flex-wrap items-end gap-3 border-t border-gray-100 pt-4"
      onsubmit={handleReEvaluate}
    >
      <label class="flex flex-col text-xs text-gray-600">
        Assumed σ
        <input
          class="mt-1 w-24 rounded border border-gray-300 px-2 py-1 text-sm"
          type="number"
          step="0.01"
          min="0"
          bind:value={sigmaInput}
          placeholder="1.0"
        />
      </label>
      <label class="flex flex-col text-xs text-gray-600">
        Effect size
        <input
          class="mt-1 w-24 rounded border border-gray-300 px-2 py-1 text-sm"
          type="number"
          step="0.01"
          bind:value={effectInput}
          placeholder="2.0"
        />
      </label>
      <label class="flex flex-col text-xs text-gray-600">
        α
        <input
          class="mt-1 w-24 rounded border border-gray-300 px-2 py-1 text-sm"
          type="number"
          step="0.01"
          min="0"
          max="1"
          bind:value={alphaInput}
          placeholder="0.05"
        />
      </label>
      <button
        type="submit"
        class="rounded bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-50"
        disabled={running}
      >
        {running ? 'Evaluating…' : 'Re-evaluate'}
      </button>
    </form>
  {/if}
</div>
