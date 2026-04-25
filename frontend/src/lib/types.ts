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
  | 'experiment_created'
  | 'interrupted';

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
  onConversationId(id: string, turnId?: string): void;
  onToken(text: string): void;
  onToolStart(tool: string, input: Record<string, unknown>): void;
  onToolResult(tool: string, output: Record<string, unknown>): void;
  onDone(): void;
  onError(message: string): void;
  onExperimentCreated?(data: ExperimentCreatedEvent): void;
  /**
   * Emitted by the resume endpoint when the underlying turn did not
   * reach a terminal (done/error) event — e.g. the server container
   * restarted mid-stream. The client should surface a "stream was
   * interrupted — retry?" state instead of waiting forever.
   */
  onInterrupted?(message: string): void;
  /**
   * Called once per SSE event that carries an ``id:`` field so the
   * client can track the last-seen event id for reconnect.
   */
  onEventId?(eventId: string): void;
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
  evaluation_data: Record<string, unknown> | null;
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
// DOE upload flow (mirrors ``backend/src/app/schemas/uploads.py``)
// ---------------------------------------------------------------------------

export type FactorType = 'continuous' | 'categorical' | 'mixture';
export type ResponseGoal = 'maximize' | 'minimize' | 'target';
export type UploadOrientation = 'rows' | 'columns';
export type UploadStatus = 'needs_clarification' | 'parsed';

export interface UploadFactor {
  name: string;
  type: FactorType;
  low: number | null;
  high: number | null;
  levels: unknown[] | null;
  units: string | null;
}

export interface UploadResponseSpec {
  name: string;
  goal: ResponseGoal | null;
  units: string | null;
}

export interface ClarifyingQuestion {
  id: string;
  question: string;
  options: string[] | null;
  column_ref: string | null;
}

export interface ParsedDesignPayload {
  orientation: UploadOrientation;
  factors: UploadFactor[];
  responses: UploadResponseSpec[];
  design_actual: Record<string, unknown>[];
  results_data: Record<string, unknown>[];
}

export interface UploadParseResponse {
  upload_id: string;
  status: UploadStatus;
  parsed: ParsedDesignPayload | null;
  questions: ClarifyingQuestion[] | null;
  raw_preview: unknown[][];
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

// Mirrors ``ExportFormat`` in ``backend/src/app/schemas/exports.py``.
// ``pdf`` / ``xlsx`` / ``csv`` / ``md`` are static report formats.
// ``py`` / ``ipynb`` / ``md_code`` / ``zip`` are the reproducible-code
// formats (zip is the full bundle with code + data + README); they
// require owner auth — the public share API refuses them with 403.
export type ExportFormat =
  | 'pdf'
  | 'xlsx'
  | 'csv'
  | 'md'
  | 'py'
  | 'ipynb'
  | 'md_code'
  | 'zip';

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
  evaluation_data: Record<string, unknown> | null;
  owner_display_name: string | null;
  view_count: number;
  expires_at: string | null;
  created_at: string;
  allow_results: boolean;
  token: string;
}
