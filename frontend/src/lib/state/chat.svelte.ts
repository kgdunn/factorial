/**
 * Chat state management using Svelte 5 runes (class-based pattern).
 *
 * Usage in components:
 *   import { chatState } from '$lib/state/chat.svelte';
 *   chatState.messages   // reactive
 *   chatState.sendMessage('hello')
 */

import { fetchConversationMessages } from '$lib/api/experiments';
import { resumeChatStream, streamChat } from '$lib/api/sse';
import type {
  ChatMessage,
  ContentBlock,
  SSECallbacks,
  ToolUseBlock,
} from '$lib/types';
import { experimentsState } from '$lib/state/experiments.svelte';

function generateId(): string {
  return crypto.randomUUID();
}

/**
 * How many auto-reconnect attempts to make against the resume endpoint
 * after the primary stream drops before giving up and surfacing an
 * error. Kept low so a genuinely-gone backend doesn't spin forever.
 */
const MAX_RESUME_ATTEMPTS = 3;

/** Base delay in ms for exponential backoff between resume attempts. */
const RESUME_BACKOFF_MS = 500;

class ChatState {
  messages = $state<ChatMessage[]>([]);
  isStreaming = $state(false);
  conversationId = $state<string | null>(null);
  error = $state<string | null>(null);
  /** User-visible "stream was cut short" flag; cleared on retry/new message. */
  wasInterrupted = $state(false);

  private abortController: AbortController | null = null;
  private lastUserMessage: string | null = null;
  /** Last SSE event id observed, used as ``Last-Event-ID`` on resume. */
  private lastEventId: string | null = null;
  /** Guards against multiple overlapping reconnect attempts. */
  private resumeAttempts = 0;

  /** Send a user message and start streaming the assistant response. */
  sendMessage(text: string): void {
    const trimmed = text.trim();
    if (!trimmed || this.isStreaming) return;

    this.lastUserMessage = trimmed;
    this.error = null;
    this.wasInterrupted = false;
    this.lastEventId = null;
    this.resumeAttempts = 0;

    // Add user message
    this.messages.push({
      id: generateId(),
      role: 'user',
      content: [{ type: 'text', text: trimmed }],
      timestamp: new Date(),
    });

    // Add empty assistant message to be filled by streaming
    const assistantMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: [],
      timestamp: new Date(),
    };
    this.messages.push(assistantMsg);

    this.isStreaming = true;
    this.abortController = streamChat(
      trimmed,
      this.conversationId,
      this.buildCallbacks(),
    );
  }

  /** Cancel an in-progress stream. */
  cancelStream(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.isStreaming = false;
  }

  /** Retry the last user message. */
  retryLastMessage(): void {
    if (!this.lastUserMessage || this.isStreaming) return;

    // Remove the last assistant message (failed/incomplete)
    const last = this.messages[this.messages.length - 1];
    if (last?.role === 'assistant') {
      this.messages.pop();
    }
    // Remove the last user message (will be re-added by sendMessage)
    const prev = this.messages[this.messages.length - 1];
    if (prev?.role === 'user') {
      this.messages.pop();
    }

    this.error = null;
    this.wasInterrupted = false;
    this.sendMessage(this.lastUserMessage);
  }

  /** Clear conversation and start fresh. */
  clearConversation(): void {
    this.cancelStream();
    this.messages = [];
    this.conversationId = null;
    this.error = null;
    this.wasInterrupted = false;
    this.lastUserMessage = null;
    this.lastEventId = null;
    this.resumeAttempts = 0;
  }

  /** Load an existing conversation's messages (for "return to chat" flow). */
  async loadConversation(conversationId: string): Promise<void> {
    if (this.conversationId === conversationId && this.messages.length > 0) return;

    this.error = null;
    try {
      const resp = await fetchConversationMessages(conversationId);
      this.conversationId = resp.conversation_id;
      this.messages = resp.messages.map((m: ChatMessage) => ({
        ...m,
        timestamp: m.timestamp ? new Date(m.timestamp as unknown as string) : new Date(),
      }));
    } catch (err: unknown) {
      this.error = err instanceof Error ? err.message : 'Failed to load conversation';
    }
  }

  // -----------------------------------------------------------------------
  // Private helpers
  // -----------------------------------------------------------------------

  private get currentAssistantMessage(): ChatMessage | null {
    const last = this.messages[this.messages.length - 1];
    return last?.role === 'assistant' ? last : null;
  }

  private findLastToolUse(
    content: ContentBlock[],
    toolName: string,
  ): ToolUseBlock | null {
    for (let i = content.length - 1; i >= 0; i--) {
      const block = content[i];
      if (block.type === 'tool_use' && block.name === toolName && block.isLoading) {
        return block;
      }
    }
    return null;
  }

  /**
   * Build the callbacks object used for both the primary stream and
   * every resume attempt. Keeping it on an instance method (rather
   * than as a frozen object) means the closures always see the
   * up-to-date chat state.
   */
  private buildCallbacks(): SSECallbacks {
    return {
      onConversationId: (id: string) => {
        this.conversationId = id;
      },

      onEventId: (eventId: string) => {
        this.lastEventId = eventId;
      },

      onToken: (text: string) => {
        const msg = this.currentAssistantMessage;
        if (!msg) return;

        const lastBlock = msg.content[msg.content.length - 1];
        if (lastBlock && lastBlock.type === 'text') {
          lastBlock.text += text;
        } else {
          msg.content.push({ type: 'text', text });
        }
      },

      onToolStart: (tool: string, input: Record<string, unknown>) => {
        const msg = this.currentAssistantMessage;
        if (!msg) return;

        msg.content.push({
          type: 'tool_use',
          id: generateId(),
          name: tool,
          input,
          isLoading: true,
        });
      },

      onToolResult: (tool: string, output: Record<string, unknown>) => {
        const msg = this.currentAssistantMessage;
        if (!msg) return;

        const toolUseBlock = this.findLastToolUse(msg.content, tool);
        if (toolUseBlock) {
          toolUseBlock.isLoading = false;
        }

        msg.content.push({
          type: 'tool_result',
          toolUseId: toolUseBlock?.id ?? '',
          toolName: tool,
          output,
          isError: output.error !== undefined,
        });
      },

      onDone: () => {
        this.isStreaming = false;
        this.abortController = null;
        this.resumeAttempts = 0;
      },

      onError: (message: string) => {
        // Try to resume via the persisted event log before giving up —
        // a transient network blip or backend restart should survive.
        if (
          this.conversationId &&
          this.resumeAttempts < MAX_RESUME_ATTEMPTS &&
          !this.isDoneReached()
        ) {
          this.scheduleResume();
          return;
        }
        this.error = message;
        this.isStreaming = false;
        this.abortController = null;
      },

      onInterrupted: (message: string) => {
        // Resume replay finished without reaching ``done`` — the
        // original turn was cut short by a container restart or crash.
        // Stop the spinner and let the user retry cleanly.
        this.wasInterrupted = true;
        this.error = message;
        this.isStreaming = false;
        this.abortController = null;
        this.resumeAttempts = 0;
      },

      onExperimentCreated: (data) => {
        experimentsState.notifyCreated(data);
      },
    };
  }

  /**
   * Kick off a resume fetch against the backend after the primary
   * stream died. Uses exponential backoff and tracks attempts.
   */
  private scheduleResume(): void {
    this.resumeAttempts += 1;
    const delay = RESUME_BACKOFF_MS * 2 ** (this.resumeAttempts - 1);

    window.setTimeout(() => {
      if (!this.conversationId) {
        return;
      }
      this.abortController = resumeChatStream(
        this.conversationId,
        this.lastEventId,
        this.buildCallbacks(),
      );
    }, delay);
  }

  /**
   * Has the current turn already produced a terminal ``done``?
   * If so, an error from a dangling connection is spurious and we
   * shouldn't bother resuming.
   */
  private isDoneReached(): boolean {
    return !this.isStreaming;
  }
}

export const chatState = new ChatState();
