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
  | 'plan'
  | 'plan_update'
  | 'phase'
  | 'done'
  | 'error'
  | 'experiment_created'
  | 'interrupted';

// ---------------------------------------------------------------------------
// Live-plan / phase types
// ---------------------------------------------------------------------------

export type PlanStepStatus = 'pending' | 'in_progress' | 'completed' | 'skipped';

export interface PlanStep {
  text: string;
  status: PlanStepStatus;
  note?: string;
  /** ms timestamp captured client-side when the step first transitions to in_progress. */
  startedAt?: number;
  /** ms timestamp captured client-side when the step transitions to completed/skipped. */
  completedAt?: number;
}

export type PhaseName = 'thinking' | 'streaming' | 'calling_tool' | 'finalizing';

export interface PhaseState {
  phase: PhaseName;
  label?: string;
  tool?: string;
  turn?: number;
  maxTurns?: number;
  /** ms timestamp captured client-side when this phase started. */
  startedAt: number;
}

/** Wire payloads — match backend agent_loop.py emissions. */
export interface PlanEvent {
  plan_id: string;
  steps: string[];
}

export interface PlanUpdateItem {
  step_index: number;
  status: PlanStepStatus;
  note?: string;
}

export interface PlanUpdateEvent {
  plan_id: string;
  updates: PlanUpdateItem[];
}

export interface PhaseEvent {
  phase: PhaseName;
  label?: string;
  tool?: string;
  turn?: number;
  max_turns?: number;
}

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

export interface PlanBlock {
  type: 'plan';
  planId: string;
  steps: PlanStep[];
}

export type ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | PlanBlock;

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
  /** A new plan was recorded by the agent (record_plan tool call). */
  onPlan?(event: PlanEvent): void;
  /** One or more plan steps changed status (update_plan tool call). */
  onPlanUpdate?(event: PlanUpdateEvent): void;
  /** Coarse activity phase changed (always-on, independent of plan). */
  onPhase?(event: PhaseEvent): void;
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
