<script lang="ts">
  import type { PhaseState, PlanBlock, PlanStep } from '$lib/types';

  interface Props {
    plan: PlanBlock;
    /** Live phase pill, only shown while this is the in-flight bubble. */
    currentPhase: PhaseState | null;
    /** True only for the plan attached to the in-flight assistant message. */
    isStreaming: boolean;
  }

  let { plan, currentPhase, isStreaming }: Props = $props();

  // Tick once per second so elapsed times stay live without a per-row
  // setInterval. Cleaned up automatically via $effect.
  let now = $state(Date.now());
  $effect(() => {
    if (!isStreaming) return;
    const id = setInterval(() => {
      now = Date.now();
    }, 1000);
    return () => clearInterval(id);
  });

  function formatElapsed(ms: number): string {
    const total = Math.max(0, Math.floor(ms / 1000));
    if (total < 60) return `${total}s`;
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}m ${s.toString().padStart(2, '0')}s`;
  }

  function stepElapsed(step: PlanStep): string | null {
    if (step.status === 'in_progress' && step.startedAt) {
      return formatElapsed(now - step.startedAt);
    }
    if (
      (step.status === 'completed' || step.status === 'skipped') &&
      step.startedAt &&
      step.completedAt
    ) {
      return formatElapsed(step.completedAt - step.startedAt);
    }
    return null;
  }

  function phaseLabel(p: PhaseState): string {
    if (p.label) return p.label;
    switch (p.phase) {
      case 'thinking':
        return 'Thinking';
      case 'streaming':
        return 'Writing response';
      case 'calling_tool':
        return p.tool ? `Running ${p.tool}` : 'Running tool';
      case 'finalizing':
        return 'Finalizing';
      default:
        return p.phase;
    }
  }

  let inProgressIdx = $derived(
    plan.steps.findIndex((s) => s.status === 'in_progress'),
  );
  let totalSteps = $derived(plan.steps.length);
  let inProgressStep = $derived(
    inProgressIdx >= 0 ? plan.steps[inProgressIdx] : null,
  );
</script>

<div
  class="my-2 rounded-md border border-stone-200 bg-stone-50/60 px-3 py-2 text-sm
         dark:border-stone-700 dark:bg-stone-800/40"
  data-testid="plan-checklist"
>
  <!-- Compact mobile header: only the in-progress step + count. -->
  <div class="flex items-center gap-2 sm:hidden">
    {#if inProgressStep}
      <span
        class="inline-block h-2 w-2 flex-none animate-pulse rounded-full bg-amber-500"
        aria-hidden="true"
      ></span>
      <span class="truncate text-stone-700 dark:text-stone-200">
        Step {inProgressIdx + 1} of {totalSteps}: {inProgressStep.text}
      </span>
      {#if stepElapsed(inProgressStep)}
        <span class="ml-auto flex-none text-xs text-stone-500 tabular-nums">
          {stepElapsed(inProgressStep)}
        </span>
      {/if}
    {:else}
      <span class="truncate text-stone-600 dark:text-stone-300">
        Plan · {totalSteps} steps
      </span>
    {/if}
  </div>

  <!-- Full desktop list -->
  <ol class="hidden space-y-1.5 sm:block">
    {#each plan.steps as step, i (i)}
      {@const elapsed = stepElapsed(step)}
      <li class="flex items-start gap-2 leading-snug">
        <span class="mt-0.5 flex-none" aria-hidden="true">
          {#if step.status === 'completed'}
            <svg
              class="h-4 w-4 text-emerald-600 dark:text-emerald-400"
              viewBox="0 0 16 16"
              fill="currentColor"
            >
              <path d="M13.5 4.5L6 12L2.5 8.5l1-1L6 10l6.5-6.5z" />
            </svg>
          {:else if step.status === 'in_progress'}
            <svg
              class="h-4 w-4 animate-spin text-amber-600 dark:text-amber-400"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="8" cy="8" r="6" opacity="0.25" />
              <path d="M14 8a6 6 0 0 0-6-6" />
            </svg>
          {:else if step.status === 'skipped'}
            <svg
              class="h-4 w-4 text-stone-400"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M3 8h10" />
            </svg>
          {:else}
            <svg
              class="h-4 w-4 text-stone-400"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="8" cy="8" r="5" />
            </svg>
          {/if}
        </span>
        <span
          class="min-w-0 flex-1"
          class:text-stone-400={step.status === 'pending'}
          class:line-through={step.status === 'skipped'}
          class:text-stone-700={step.status === 'completed' ||
            step.status === 'in_progress'}
          class:dark:text-stone-200={step.status === 'completed' ||
            step.status === 'in_progress'}
        >
          {step.text}
          {#if step.note}
            <span class="ml-1 text-stone-500 dark:text-stone-400">
              · {step.note}
            </span>
          {/if}
        </span>
        {#if elapsed}
          <span class="flex-none text-xs text-stone-500 tabular-nums">
            {elapsed}
          </span>
        {/if}
      </li>
    {/each}
  </ol>

  <!-- Live phase footer pill — only while this bubble is the in-flight one. -->
  {#if isStreaming && currentPhase}
    <div
      class="mt-2 flex items-center gap-2 border-t border-stone-200/70 pt-2 text-xs
             text-stone-700 dark:border-stone-700/60 dark:text-stone-300"
    >
      <span
        class="inline-block h-1.5 w-1.5 flex-none animate-pulse rounded-full bg-amber-500"
        aria-hidden="true"
      ></span>
      <span class="truncate">{phaseLabel(currentPhase)}</span>
      <span class="ml-auto flex-none tabular-nums">
        {formatElapsed(now - currentPhase.startedAt)}
      </span>
    </div>
  {/if}
</div>
