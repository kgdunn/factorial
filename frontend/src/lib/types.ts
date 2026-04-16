// ---------------------------------------------------------------------------
// User / Auth types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  background: string | null;
  created_at: string | null;
}

// ---------------------------------------------------------------------------
// SSE types
// ---------------------------------------------------------------------------

/** SSE event types matching the backend protocol. */
export type SSEEventType =
  | 'conversation_id'
  | 'token'
  | 'tool_start'
  | 'tool_result'
  | 'done'
  | 'error'
  | 'experiment_created';

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
  onExperimentCreated?(data: ExperimentCreatedEvent): void;
}

// ---------------------------------------------------------------------------
// Experiment types
// ---------------------------------------------------------------------------

export type ExperimentStatus = 'draft' | 'active' | 'completed' | 'archived';

export interface ExperimentCreatedEvent {
  experiment_id: string;
  name: string;
  design_type: string;
}

export interface ExperimentSummary {
  id: string;
  name: string;
  status: ExperimentStatus;
  design_type: string | null;
  n_runs: number | null;
  n_factors: number | null;
  conversation_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExperimentDetail extends ExperimentSummary {
  factors: Record<string, unknown>[] | null;
  design_data: Record<string, unknown> | null;
  results_data: Record<string, unknown>[] | null;
}

export interface ExperimentListResponse {
  experiments: ExperimentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ResultsResponse {
  experiment_id: string;
  results_data: Record<string, unknown>[] | null;
  n_results_entered: number;
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

// ---------------------------------------------------------------------------
// Shareable experiment links
// ---------------------------------------------------------------------------

export type ExportFormat = 'pdf' | 'xlsx' | 'csv' | 'md';

export interface ShareLink {
  id: string;
  token: string;
  url: string;
  allow_results: boolean;
  expires_at: string | null;
  revoked_at: string | null;
  view_count: number;
  created_at: string;
}

export interface ShareLinkListResponse {
  shares: ShareLink[];
}

export interface ShareLinkCreatePayload {
  expires_at?: string | null;
  never_expire?: boolean;
  allow_results?: boolean;
}

export interface PublicExperimentView {
  id: string;
  name: string;
  design_type: string | null;
  n_runs: number | null;
  n_factors: number | null;
  factors: Record<string, unknown>[] | null;
  design_data: Record<string, unknown> | null;
  results_data: Record<string, unknown>[] | null;
  owner_display_name: string | null;
  view_count: number;
  expires_at: string | null;
  created_at: string;
  allow_results: boolean;
  token: string;
}
