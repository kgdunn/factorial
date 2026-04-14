<script lang="ts">
  import type { ECharts } from 'echarts';

  interface Props {
    option: Record<string, unknown>;
    height?: string;
    is3D?: boolean;
    class?: string;
  }

  let {
    option,
    height = '400px',
    is3D = false,
    class: className = '',
  }: Props = $props();

  let container: HTMLDivElement | undefined = $state();
  let chartInstance: ECharts | undefined = $state();

  // Initialise ECharts when the container mounts
  $effect(() => {
    if (!container) return;

    let disposed = false;
    let ro: ResizeObserver | undefined;

    (async () => {
      const echarts = await import('echarts');
      if (is3D) {
        await import('echarts-gl');
      }
      if (disposed || !container) return;

      const chart = echarts.init(container);
      chart.setOption(option as never, { notMerge: true });
      chartInstance = chart;

      ro = new ResizeObserver(() => chart.resize());
      ro.observe(container);
    })();

    return () => {
      disposed = true;
      ro?.disconnect();
      chartInstance?.dispose();
      chartInstance = undefined;
    };
  });

  // Update chart when the option prop changes (after initial load)
  $effect(() => {
    if (chartInstance && option) {
      chartInstance.setOption(option as never, { notMerge: true });
    }
  });
</script>

<div
  bind:this={container}
  class="w-full {className}"
  style:height
></div>
