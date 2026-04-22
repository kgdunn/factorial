<script lang="ts">
  import { chatState } from '$lib/state/chat.svelte';
  import { experimentsState } from '$lib/state/experiments.svelte';
  import MessageBubble from './MessageBubble.svelte';
  import Btn from './brand/Btn.svelte';
  import DetailLevelControl from './brand/DetailLevelControl.svelte';

  let messageList: HTMLDivElement | undefined = $state();
  let inputText = $state('');
  let userScrolledUp = $state(false);

  const SCROLL_THRESHOLD = 60;

  const SUGGESTED_PROMPTS = [
    'Yield vs T, feed, catalyst',
    'Binder formulation · 3 components',
    'Coating thickness · line 3',
    'Sensory panel · brine time × salt',
  ];

  $effect(() => {
    const len = chatState.messages.length;
    const streaming = chatState.isStreaming;
    if (len > 0 && !userScrolledUp && messageList) {
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

<div class="flex h-full flex-col bg-paper">
  <div
    bind:this={messageList}
    class="flex-1 overflow-y-auto px-9 py-7"
    onscroll={handleScroll}
  >
    {#if chatState.messages.length === 0}
      <div class="flex h-full flex-col items-center justify-center text-center">
        <div class="mb-9 max-w-xl">
          <div class="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
            new experiment · blank
          </div>
          <h2 class="mt-2 font-serif italic text-[40px] leading-tight text-ink">
            Describe the process you want to <em class="text-clay-ink">understand</em>.
          </h2>
          <p class="mt-4 font-sans text-[15px] leading-relaxed text-ink-soft">
            Name the response, the factors, and roughly how many runs you can
            afford. The agent will draft a plan and defend the choice.
          </p>
        </div>
        <div class="flex flex-wrap justify-center gap-2.5">
          {#each SUGGESTED_PROMPTS as prompt (prompt)}
            <button
              type="button"
              class="cursor-pointer rounded-full border border-rule-soft bg-paper px-3 py-1.5 font-sans text-xs text-ink-soft transition-colors hover:bg-paper-2"
              onclick={() => handlePromptClick(prompt)}
            >
              {prompt}
            </button>
          {/each}
        </div>
      </div>
    {:else}
      <div class="mx-auto flex max-w-3xl flex-col gap-2">
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

  {#if experimentsState.lastCreated}
    <div
      class="mx-9 mb-2 flex items-center justify-between rounded-xl border border-[#EBD9C7] bg-clay-tint px-4 py-2.5 font-sans text-sm text-clay-ink"
    >
      <span>
        <span class="font-mono text-[10px] uppercase tracking-[0.18em]">experiment saved</span>
        &nbsp;·&nbsp;<strong class="font-serif italic text-base text-ink">{experimentsState.lastCreated.name}</strong>
      </span>
      <div class="flex items-center gap-2">
        <Btn variant="primary" size="sm" href="/experiments/{experimentsState.lastCreated.experiment_id}">
          View
        </Btn>
        <button
          type="button"
          class="cursor-pointer font-mono text-[11px] text-ink-faint hover:text-ink"
          onclick={() => experimentsState.dismissNotification()}
        >
          dismiss
        </button>
      </div>
    </div>
  {/if}

  {#if chatState.error}
    <div
      class="mx-9 mb-2 flex items-center justify-between rounded-xl border border-[color:var(--color-negative)]/30 bg-[#FBECE8] px-4 py-2.5 font-sans text-sm text-[color:var(--color-negative)]"
    >
      <span>{chatState.error}</span>
      <Btn variant="clay" size="sm" onclick={() => chatState.retryLastMessage()}>Retry</Btn>
    </div>
  {/if}

  <div class="border-t border-rule bg-paper px-9 pb-5 pt-4">
    <div class="mx-auto mb-2 flex max-w-3xl justify-end">
      <DetailLevelControl
        value={chatState.detailLevel}
        onchange={(level) => chatState.setDetailLevel(level)}
        disabled={chatState.isStreaming}
      />
    </div>
    <div
      class="mx-auto flex max-w-3xl items-center gap-3 rounded-xl border border-rule-soft bg-paper-2 px-4 py-3.5"
    >
      <input
        class="flex-1 border-none bg-transparent font-sans text-sm text-ink outline-none placeholder:text-ink-faint"
        placeholder="Ask the agent anything — &quot;why resolution V?&quot;, &quot;swap to Box-Behnken&quot;, &quot;add a block for shift&quot;"
        bind:value={inputText}
        onkeydown={handleKeydown}
        disabled={chatState.isStreaming}
      />
      {#if chatState.isStreaming}
        <Btn variant="ghost" size="sm" onclick={() => chatState.cancelStream()}>Cancel</Btn>
      {:else}
        <Btn
          variant="primary"
          size="sm"
          icon="arrow"
          onclick={handleSend}
          disabled={!inputText.trim()}
        >
          Send
        </Btn>
      {/if}
    </div>
  </div>
</div>
