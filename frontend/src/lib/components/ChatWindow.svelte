<script lang="ts">
  import { chatState } from '$lib/state/chat.svelte';
  import { experimentsState } from '$lib/state/experiments.svelte';
  import MessageBubble from './MessageBubble.svelte';
  import Btn from './brand/Btn.svelte';
  import DetailLevelControl from './brand/DetailLevelControl.svelte';
  import VoiceInputButton from './brand/VoiceInputButton.svelte';

  let messageList: HTMLDivElement | undefined = $state();
  let inputEl: HTMLTextAreaElement | undefined = $state();
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
    // Subscribe to the last message's content so streaming token updates
    // re-trigger the effect, not just the arrival of a new message.
    const lastMsg = chatState.messages[len - 1];
    if (lastMsg) {
      for (const block of lastMsg.content) {
        if (block.type === 'text') {
          void block.text.length;
        } else if (block.type === 'tool_use') {
          void block.isLoading;
        }
      }
    }
    if (len > 0 && !userScrolledUp && messageList) {
      requestAnimationFrame(() => {
        messageList?.scrollTo({
          top: messageList.scrollHeight,
          // Smooth scroll fights with rapid token updates; only animate
          // when the stream is idle (e.g. after a new message is sent).
          behavior: streaming ? 'auto' : 'smooth',
        });
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
    if (e.key !== 'Enter') return;
    // Ctrl/Cmd + Enter inserts a newline. Manual splice instead of relying
    // on the browser default — Chrome and Firefox don't insert one for
    // Ctrl+Enter inside a <textarea>, only for Shift+Enter and bare Enter.
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const ta = e.currentTarget as HTMLTextAreaElement;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      inputText = inputText.slice(0, start) + '\n' + inputText.slice(end);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 1;
      });
      return;
    }
    // Shift+Enter falls through to the textarea's default newline behavior.
    if (e.shiftKey) return;
    // Touch-primary devices (phones, most tablets): the on-screen Enter key
    // is the only way to break a line, so let it insert a newline instead
    // of submitting. The Send button stays available for submit.
    if (typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches) {
      return;
    }
    e.preventDefault();
    handleSend();
  }

  // Auto-grow the textarea up to its CSS max-height; re-runs on every
  // keystroke (including paste) and after handleSend clears the field.
  $effect(() => {
    void inputText;
    if (!inputEl) return;
    inputEl.style.height = 'auto';
    inputEl.style.height = `${inputEl.scrollHeight}px`;
  });

  function handlePromptClick(prompt: string) {
    inputText = prompt;
    handleSend();
  }
</script>

<div class="flex h-full flex-col bg-paper">
  <div
    bind:this={messageList}
    class="flex-1 overflow-y-auto px-5 py-5 sm:px-9 sm:py-7"
    onscroll={handleScroll}
  >
    {#if chatState.messages.length === 0}
      <div class="flex h-full flex-col items-center justify-center text-center">
        <div class="mb-9 max-w-xl">
          <div class="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-faint">
            new experiment · blank
          </div>
          <h2 class="mt-2 font-serif italic text-[28px] leading-tight text-ink sm:text-[34px] md:text-[40px]">
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
        {#if chatState.byokUsed}
          <div
            class="mb-2 inline-flex w-fit items-center gap-1.5 self-start rounded-full border border-rule-soft bg-paper-2 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-soft"
            title="This conversation uses your own Anthropic API key — no platform markup applied."
          >
            <span aria-hidden="true">⌁</span>
            <span>using your own key</span>
          </div>
        {/if}
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
      class="mx-5 mb-2 flex items-center justify-between rounded-xl border border-[#EBD9C7] bg-clay-tint px-4 py-2.5 font-sans text-sm text-clay-ink sm:mx-9"
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
      class="mx-5 mb-2 flex items-center justify-between rounded-xl border border-[color:var(--color-negative)]/30 bg-[#FBECE8] px-4 py-2.5 font-sans text-sm text-[color:var(--color-negative)] sm:mx-9"
    >
      <span>{chatState.error}</span>
      <Btn variant="clay" size="sm" onclick={() => chatState.retryLastMessage()}>Retry</Btn>
    </div>
  {/if}

  <div class="border-t border-rule bg-paper px-5 pt-4 pb-[calc(1.25rem+env(safe-area-inset-bottom))] sm:px-9">
    <div class="mx-auto mb-2 flex max-w-3xl justify-end">
      <DetailLevelControl
        value={chatState.detailLevel}
        onchange={(level) => chatState.setDetailLevel(level)}
        disabled={chatState.isStreaming}
      />
    </div>
    <div
      class="mx-auto flex max-w-3xl items-end gap-3 rounded-xl border border-rule-soft bg-paper-2 px-4 py-3.5"
    >
      <textarea
        bind:this={inputEl}
        rows={1}
        class="flex-1 resize-none border-none bg-transparent p-0 font-sans text-sm leading-6 text-ink outline-none placeholder:text-ink-faint max-h-[50dvh]"
        placeholder="Ask the agent anything — &quot;why resolution V?&quot;, &quot;swap to Box-Behnken&quot;, &quot;add a block for shift&quot;."
        bind:value={inputText}
        onkeydown={handleKeydown}
        disabled={chatState.isStreaming}
      ></textarea>
      <VoiceInputButton
        onTranscript={(t) => {
          inputText = inputText ? inputText.trimEnd() + ' ' + t : t;
        }}
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
