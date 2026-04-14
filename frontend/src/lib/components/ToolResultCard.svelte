<script lang="ts">
  import BaseChart from './BaseChart.svelte';

  interface Props {
    toolName: string;
    input: Record<string, unknown>;
    output: Record<string, unknown> | null;
    isLoading: boolean;
    isError: boolean;
  }

  let { toolName, input, output, isLoading, isError }: Props = $props();

  const TOOL_LABELS: Record<string, string> = {
    generate_design: 'Design Matrix',
    create_design: 'Design Matrix',
    analyze_experiment: 'Analysis Results',
    analyze_doe: 'Analysis Results',
    fit_linear_model: 'Model Fit',
    visualize_doe: 'Visualization',
    doe_knowledge: 'DOE Knowledge',
    suggest_next_runs: 'Suggested Runs',
    validate_design: 'Design Validation',
    compare_designs: 'Design Comparison',
  };

  let showInput = $state(false);
  let showRawOutput = $state(false);

  let isChart = $derived(
    toolName === 'visualize_doe' &&
    output != null &&
    typeof output.echarts === 'object' &&
    output.echarts != null,
  );

  let is3D = $derived(
    isChart &&
    (output!.plot_type === 'surface_3d' ||
      (output!.echarts as Record<string, unknown>)?.xAxis3D != null),
  );

  let chartTitle = $derived(
    isChart ? (output!.title as string) ?? '' : '',
  );

  let isDesignMatrix = $derived(
    output != null && Array.isArray(output.design_matrix),
  );

  let designMatrix = $derived(
    isDesignMatrix
      ? (output!.design_matrix as Record<string, unknown>[])
      : [],
  );

  let designColumns = $derived(
    designMatrix.length > 0 ? Object.keys(designMatrix[0]) : [],
  );

  let label = $derived(TOOL_LABELS[toolName] ?? toolName);
</script>

<div class="my-2 rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
  <!-- Header -->
  <div class="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b border-gray-200">
    {#if isLoading}
      <div class="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
    {:else if isError}
      <svg class="h-4 w-4 text-negative" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
      </svg>
    {:else}
      <svg class="h-4 w-4 text-positive" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
      </svg>
    {/if}

    <span class="text-sm font-medium text-gray-700">
      {#if isLoading}
        Running {label}...
      {:else}
        {label}
      {/if}
    </span>

    <button
      class="ml-auto text-xs text-gray-400 hover:text-gray-600"
      onclick={() => (showInput = !showInput)}
    >
      {showInput ? 'Hide' : 'Show'} input
    </button>
  </div>

  <!-- Collapsible input preview -->
  {#if showInput}
    <div class="px-3 py-2 bg-gray-50 border-b border-gray-100">
      <pre class="text-xs text-gray-500 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(input, null, 2)}</pre>
    </div>
  {/if}

  <!-- Body -->
  {#if isLoading}
    <div class="px-3 py-4 text-center text-sm text-gray-400">
      Executing...
    </div>
  {:else if output != null}
    <div class="p-3">
      {#if isError}
        <!-- Error output -->
        <div class="rounded bg-red-50 px-3 py-2 text-sm text-negative">
          {output.error ?? 'Tool execution failed'}
        </div>

      {:else if isChart}
        <!-- ECharts visualization -->
        {#if chartTitle}
          <h4 class="mb-2 text-sm font-medium text-gray-600">{chartTitle}</h4>
        {/if}
        <BaseChart
          option={output.echarts as Record<string, unknown>}
          height={is3D ? '500px' : '400px'}
          {is3D}
        />

      {:else if isDesignMatrix}
        <!-- Design matrix table -->
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr>
                {#each designColumns as col}
                  <th class="border-b border-gray-200 px-3 py-1.5 text-left text-xs font-medium uppercase text-gray-500">
                    {col}
                  </th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each designMatrix as row, i}
                <tr class={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                  {#each designColumns as col}
                    <td class="border-b border-gray-100 px-3 py-1.5 text-gray-700 font-mono">
                      {row[col]}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

      {:else}
        <!-- Generic JSON output -->
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs text-gray-400">Result</span>
          <button
            class="text-xs text-gray-400 hover:text-gray-600"
            onclick={() => (showRawOutput = !showRawOutput)}
          >
            {showRawOutput ? 'Collapse' : 'Expand'}
          </button>
        </div>
        <pre class="text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap rounded bg-gray-50 p-2 max-h-64 overflow-y-auto">{JSON.stringify(output, null, showRawOutput ? 2 : undefined)}</pre>
      {/if}
    </div>
  {/if}
</div>
