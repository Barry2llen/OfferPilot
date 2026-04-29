// ─── Provider Enum ───
export type Provider =
  | "OpenAI"
  | "Google"
  | "Anthropic"
  | "DeepSeek"
  | "OpenAI Compatible";

// ─── Resumes ───
export interface ResumeListItem {
  id: number;
  file_path: string | null;
  upload_time: string;
  original_filename: string | null;
  media_type: string | null;
  has_file: boolean;
  preview_url: string | null;
}

export interface ResumeDetail {
  id: number;
  file_path: string | null;
  upload_time: string;
  original_filename: string | null;
  media_type: string | null;
  has_file: boolean;
  preview_url: string | null;
}

// ─── Model Providers ───
export interface ModelProviderResponse {
  provider: Provider | string;
  name: string;
  base_url: string | null;
  has_api_key: boolean;
}

export interface ModelProviderCreate {
  provider: Provider;
  name: string;
  base_url?: string | null;
  api_key?: string | null;
}

export interface ModelProviderUpdate {
  provider?: Provider | null;
  base_url?: string | null;
  api_key?: string | null;
}

// ─── Model Selections ───
export interface ModelSelectionResponse {
  id: number;
  provider: ModelProviderResponse;
  model_name: string;
  supports_image_input: boolean;
}

export interface ModelSelectionCreate {
  provider_name: string;
  model_name: string;
  supports_image_input?: boolean;
}

export interface ModelSelectionUpdate {
  provider_name?: string | null;
  model_name?: string | null;
  supports_image_input?: boolean | null;
}

// ─── AI Chat ───
export interface AIChatHistorySummary {
  thread_id: string;
  title: string;
  last_message_preview: string;
  message_count: number;
  updated_at: string;
}

export interface AIChatHistoryListResponse {
  items: AIChatHistorySummary[];
  limit: number;
  offset: number;
}

export interface AIChatHistoryMessage {
  role: string;
  type: string;
  content: string | unknown;
  name?: string | null;
  tool_call_id?: string | null;
  status?: string | null;
}

export interface AIChatHistoryDetailResponse {
  thread_id: string;
  title: string;
  last_message_preview: string;
  message_count: number;
  updated_at: string;
  messages: AIChatHistoryMessage[];
}

export interface AIChatRequest {
  selection_id: number;
  prompt: string;
  thread_id?: string | null;
}

export interface AIChatResponse {
  thread_id: string;
  content: string | unknown[];
}

export interface AIChatCommand {
  type: "prompt" | "continue" | "retry";
  prompt?: string | null;
}

export interface AIChatStreamRequest {
  selection_id: number;
  prompt?: string | null;
  thread_id?: string | null;
  command?: AIChatCommand | null;
}

// ─── SSH Events ───
export type SSEEventType =
  | "thread"
  | "token"
  | "reasoning"
  | "tool_start"
  | "tool_end"
  | "tool_error"
  | "interrupt"
  | "final"
  | "error";

export interface SSEEvent {
  event?: SSEEventType;
  data: Record<string, unknown>;
  type?: SSEEventType;
}

export interface SSETokenData {
  content: string;
}

export interface SSEToolCallData {
  tool_name: string;
  input?: Record<string, unknown>;
  output?: unknown;
  detail?: string;
}

export interface SSEInterruptData {
  id?: string;
  type?: string;
  message: string;
}

// ─── Agent Status ───
export type AgentStatus =
  | "idle"
  | "generating"
  | "tool_calling"
  | "interrupted"
  | "error";

// ─── Validation Error ───
export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}
