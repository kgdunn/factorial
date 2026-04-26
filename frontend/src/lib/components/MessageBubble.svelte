<script lang="ts">
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';
  import type { ChatMessage } from '$lib/types';
  import { chatState } from '$lib/state/chat.svelte';
  import PlanChecklist from './PlanChecklist.svelte';
  import ToolResultCard from './ToolResultCard.svelte';

  interface Props {
    message: ChatMessage;
    isLastAssistant?: boolean;
    isStreaming?: boolean;
  }

  let {
    message,
    isLastAssistant = false,
    isStreaming = false,
  }: Props = $props();

  marked.setOptions({ async: false, breaks: true });

  function renderMarkdown(text: string): string {
    const raw = marked.parse(text) as string;
    return DOMPurify.sanitize(raw);
  }

  let isUser = $derived(message.role === 'user');
  let showCursor = $derived(isLastAssistant && isStreaming);

  /** Tool names that exist purely as plan-metadata channels and must
   *  never render as tool-call cards (the SSE stream suppresses them
   *  but a REST-loaded conversation history still has the rows). */
  const META_TOOL_NAMES = new Set(['record_plan', 'update_plan']);
</script>

<div class="mb-5 flex gap-3.5 {isUser ? 'flex-row-reverse' : ''}">
  <div
    class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-mono text-xs
           {isUser
             ? 'bg-ink text-paper'
             : 'bg-clay-tint text-clay-ink border border-[#EBD9C7]'}"
  >
    {#if isUser}
      you
    {:else}
      ⌁
    {/if}
  </div>

  <div
    class="min-w-0 max-w-[680px] rounded-xl border px-4 py-3.5 font-sans text-[14px] leading-[1.6]
           {isUser
             ? 'bg-clay-tint border-[#EBD9C7] text-ink'
             : 'bg-paper-2 border-rule-soft text-ink'}"
  >
    {#each message.content as block}
      {#if block.type === 'text'}
        {#if isUser}
          <p class="whitespace-pre-wrap">{block.text}</p>
        {:else}
          <div
            class="prose prose-sm max-w-none font-sans
                   prose-headings:font-serif prose-headings:italic prose-headings:text-ink
                   prose-p:text-ink prose-p:my-1
                   prose-strong:text-clay-ink prose-em:text-clay-ink prose-em:font-serif
                   prose-code:text-clay-ink prose-code:bg-paper-3 prose-code:px-1 prose-code:rounded
                   prose-pre:bg-ink prose-pre:text-paper prose-pre:rounded-lg
                   prose-a:text-clay-ink prose-a:underline
                   prose-table:text-sm
                   prose-th:border prose-th:border-rule prose-th:px-2 prose-th:py-1
                   prose-td:border prose-td:border-rule-soft prose-td:px-2 prose-td:py-1"
          >
            {@html renderMarkdown(block.text)}
          </div>
        {/if}
      {:else if block.type === 'plan'}
        <PlanChecklist
          plan={block}
          currentPhase={isLastAssistant && isStreaming ? chatState.currentPhase : null}
          isStreaming={isLastAssistant && isStreaming}
        />
      {:else if block.type === 'tool_use'}
        {#if block.isLoading && !META_TOOL_NAMES.has(block.name)}
          <div class="my-2 flex items-center gap-2 font-mono text-xs text-ink-faint">
            <div
              class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-clay border-t-transparent"
            ></div>
            <span>Calling {block.name}…</span>
          </div>
        {/if}
      {:else if block.type === 'tool_result'}
        {#if !META_TOOL_NAMES.has(block.toolName)}
          <ToolResultCard
            toolName={block.toolName}
            input={(() => {
              const toolUse = message.content.find(
                (b) => b.type === 'tool_use' && b.id === block.toolUseId,
              );
              return toolUse?.type === 'tool_use' ? toolUse.input : {};
            })()}
            output={block.output}
            isLoading={false}
            isError={block.isError}
          />
        {/if}
      {/if}
    {/each}

    {#if showCursor}
      <span class="ml-0.5 inline-block h-4 w-2 animate-pulse bg-ink-faint align-text-bottom"></span>
    {/if}
  </div>
</div>
