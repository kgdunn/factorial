<script lang="ts">
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';
  import type { ChatMessage } from '$lib/types';
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

  // Configure marked for synchronous parsing
  marked.setOptions({ async: false, breaks: true });

  function renderMarkdown(text: string): string {
    const raw = marked.parse(text) as string;
    return DOMPurify.sanitize(raw);
  }

  let isUser = $derived(message.role === 'user');
  let showCursor = $derived(isLastAssistant && isStreaming);
</script>

<div class="flex {isUser ? 'justify-end' : 'justify-start'} mb-4">
  <div class="max-w-[80%] {isUser
    ? 'bg-primary text-white rounded-2xl rounded-br-md'
    : 'bg-gray-100 text-gray-800 rounded-2xl rounded-bl-md'
  } px-4 py-3">

    {#each message.content as block}
      {#if block.type === 'text'}
        {#if isUser}
          <p class="whitespace-pre-wrap text-sm">{block.text}</p>
        {:else}
          <!-- Assistant text rendered as markdown -->
          <div class="prose prose-sm max-w-none
            prose-headings:text-gray-800 prose-headings:font-semibold
            prose-p:text-gray-700 prose-p:my-1
            prose-code:text-primary prose-code:bg-blue-50 prose-code:px-1 prose-code:rounded
            prose-pre:bg-gray-800 prose-pre:text-gray-100 prose-pre:rounded-lg
            prose-a:text-primary prose-a:underline
            prose-table:text-sm
            prose-th:border prose-th:border-gray-300 prose-th:px-2 prose-th:py-1
            prose-td:border prose-td:border-gray-200 prose-td:px-2 prose-td:py-1">
            {@html renderMarkdown(block.text)}
          </div>
        {/if}

      {:else if block.type === 'tool_use'}
        {#if block.isLoading}
          <div class="flex items-center gap-2 my-2 text-sm text-gray-500">
            <div class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-400 border-t-transparent"></div>
            <span>Calling {block.name}...</span>
          </div>
        {/if}

      {:else if block.type === 'tool_result'}
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
    {/each}

    {#if showCursor}
      <span class="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-0.5 align-text-bottom"></span>
    {/if}
  </div>
</div>
