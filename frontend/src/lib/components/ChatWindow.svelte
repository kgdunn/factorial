<script lang="ts">
  import { chatState } from '$lib/state/chat.svelte';
  import MessageBubble from './MessageBubble.svelte';

  let messageList: HTMLDivElement | undefined = $state();
  let inputText = $state('');
  let userScrolledUp = $state(false);

  const SCROLL_THRESHOLD = 60;

  const SUGGESTED_PROMPTS = [
    'Create a 2^3 factorial design for optimizing a chemical reaction',
    'What is a response surface methodology?',
    'Help me analyze my experimental results with a Pareto chart',
  ];

  // Auto-scroll to bottom when new content arrives during streaming
  $effect(() => {
    // Access messages length and streaming state to establish dependency
    const len = chatState.messages.length;
    const streaming = chatState.isStreaming;
    if (len > 0 && !userScrolledUp && messageList) {
      // Use void to suppress unused variable warnings
      void streaming;
      requestAnimationFrame(() => {
        messageList?.scrollTo({ top: messageList.scrollHeight, behavior: 'smooth' });
      });
    }
  });

  function handleScroll() {
    if (!messageList) return;
    const { scrollTop, scrollHeight, clientHeight } = messageList;
    userScrolledUp = scrollHeight - scrollTop - clientHeight > SCROLL_THRESHOLD;
  }

  function handleSend() {
    const text = inputText.trim();
    if (!text || chatState.isStreaming) return;
    inputText = '';
    userScrolledUp = false;
    chatState.sendMessage(text);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handlePromptClick(prompt: string) {
    inputText = prompt;
    handleSend();
  }
</script>

<div class="flex h-full flex-col bg-white">
  <!-- Message list -->
  <div
    bind:this={messageList}
    class="flex-1 overflow-y-auto px-4 py-6"
    onscroll={handleScroll}
  >
    {#if chatState.messages.length === 0}
      <!-- Empty state -->
      <div class="flex h-full flex-col items-center justify-center text-center">
        <div class="mb-6">
          <h2 class="text-2xl font-semibold text-gray-800">Agentic DOE Assistant</h2>
          <p class="mt-2 text-gray-500">
            Design, analyse, and visualise experiments with AI guidance.
          </p>
        </div>
        <div class="grid w-full max-w-lg gap-3">
          {#each SUGGESTED_PROMPTS as prompt}
            <button
              class="rounded-lg border border-gray-200 px-4 py-3 text-left text-sm text-gray-600
                     hover:border-primary hover:bg-blue-50 hover:text-primary transition-colors"
              onclick={() => handlePromptClick(prompt)}
            >
              {prompt}
            </button>
          {/each}
        </div>
      </div>
    {:else}
      <div class="mx-auto max-w-3xl">
        {#each chatState.messages as message, i (message.id)}
          <MessageBubble
            {message}
            isLastAssistant={
              message.role === 'assistant' &&
              i === chatState.messages.length - 1
            }
            isStreaming={chatState.isStreaming}
          />
        {/each}
      </div>
    {/if}
  </div>

  <!-- Error banner -->
  {#if chatState.error}
    <div class="mx-4 mb-2 flex items-center justify-between rounded-lg bg-red-50 px-4 py-2 text-sm text-negative">
      <span>{chatState.error}</span>
      <button
        class="ml-4 rounded bg-negative px-3 py-1 text-xs font-medium text-white hover:bg-red-700"
        onclick={() => chatState.retryLastMessage()}
      >
        Retry
      </button>
    </div>
  {/if}

  <!-- Input area -->
  <div class="border-t border-gray-200 bg-white px-4 py-3">
    <div class="mx-auto flex max-w-3xl items-end gap-3">
      <textarea
        class="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm
               placeholder-gray-400 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary
               disabled:bg-gray-50 disabled:text-gray-400"
        rows="1"
        placeholder="Ask about experimental design..."
        bind:value={inputText}
        onkeydown={handleKeydown}
        disabled={chatState.isStreaming}
      ></textarea>

      {#if chatState.isStreaming}
        <button
          class="flex-shrink-0 rounded-lg bg-neutral px-4 py-2 text-sm font-medium text-white hover:bg-gray-600"
          onclick={() => chatState.cancelStream()}
        >
          Cancel
        </button>
      {:else}
        <button
          class="flex-shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white
                 hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed"
          onclick={handleSend}
          disabled={!inputText.trim()}
        >
          Send
        </button>
      {/if}
    </div>
  </div>
</div>
