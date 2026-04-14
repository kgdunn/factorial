/** SSE event types matching the backend protocol. */
export type SSEEventType =
  | 'conversation_id'
  | 'token'
  | 'tool_start'
  | 'tool_result'
  | 'done'
  | 'error';

// ---------------------------------------------------------------------------
// Content blocks (discriminated union)
// ---------------------------------------------------------------------------

export interface TextBlock {
  type: 'text';
  text: string;
}

export interface ToolUseBlock {
  type: 'tool_use';
  id: string;
  name: string;
  input: Record<string, unknown>;
  isLoading: boolean;
}

export interface ToolResultBlock {
  type: 'tool_result';
  toolUseId: string;
  toolName: string;
  output: Record<string, unknown>;
  isError: boolean;
}

export type ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock;

// ---------------------------------------------------------------------------
// Chat message
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: ContentBlock[];
  timestamp: Date;
}

// ---------------------------------------------------------------------------
// SSE callbacks
// ---------------------------------------------------------------------------

export interface SSECallbacks {
  onConversationId(id: string): void;
  onToken(text: string): void;
  onToolStart(tool: string, input: Record<string, unknown>): void;
  onToolResult(tool: string, output: Record<string, unknown>): void;
  onDone(): void;
  onError(message: string): void;
}

// ---------------------------------------------------------------------------
// visualize_doe output shape
// ---------------------------------------------------------------------------

export interface VisualizeDoeOutput {
  plot_type: string;
  title: string;
  data: Record<string, unknown>;
  plotly: Record<string, unknown> | null;
  echarts: Record<string, unknown> | null;
}
