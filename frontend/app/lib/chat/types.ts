import type {
  AIChatCommand,
  AIChatHistoryMessage,
  AIChatStreamRequest,
  AgentStatus,
  ChatAttachmentRef,
  QueryChoice,
} from "@/app/lib/api/types";

export interface ToolCallEntry {
  name: string;
  input?: Record<string, unknown>;
  output?: unknown;
  error?: string;
  status: "running" | "success" | "error";
}

export interface ChatAttachmentItem {
  fileId: string | null;
  originalFilename: string;
  mediaType?: string | null;
  injectionMode?: string | null;
  pending?: boolean;
  rawUrl?: string;
  previewUrl?: string;
  sizeBytes?: number;
}

export interface ChatStartOptions {
  localFiles?: File[];
  fileIds?: string[];
  draftAttachments?: ChatAttachmentItem[];
  onAccepted?: () => void;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  attachments?: ChatAttachmentItem[];
  reasoning?: string;
  reasoningDurationMs?: number;
  toolCallId?: string;
  toolName?: string;
  toolStatus?: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: unknown;
  toolError?: string;
}

export interface ChatInterrupt {
  interruptId: string;
  type: string;
  message: string;
  question?: string;
  firstChoice?: string;
  firstChoiceDescription?: string;
  secondChoice?: string;
  secondChoiceDescription?: string;
  thirdChoice?: string;
  thirdChoiceDescription?: string;
}

export interface ChatStreamEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface ChatStreamLabels {
  toolError: string;
  streamError: string;
  incompleteStream: string;
  agentInterrupted: string;
  rawAttachmentUrl?: (fileId: string) => string;
}

export interface ChatStreamState {
  messages: ChatMessage[];
  liveMessages: ChatMessage[];
  streamingText: string;
  streamingReasoning: string;
  toolCalls: ToolCallEntry[];
  interrupt: ChatInterrupt | null;
  streamError: string | null;
  isStreaming: boolean;
  agentStatus: AgentStatus;
  contextCompactionStatus: ContextCompactionStatus;
  contextCompacted: boolean;
  accepted: boolean;
  terminal: boolean;
  userMessageId: string | null;
  currentAssistantIndex: number | null;
  accumulatedText: string;
  accumulatedReasoning: string;
  visibleAssistantText: string;
  resumedQueryToolEntry: ToolCallEntry | null;
  pendingQueryResumeMerge: boolean;
  nextMessageId: number;
}

export type ContextCompactionStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed";

export type ChatStreamEffect =
  | { type: "accepted" }
  | { type: "thread_updated"; threadId: string }
  | { type: "requires_image_input"; value: boolean }
  | { type: "agent_status"; value: AgentStatus }
  | { type: "history_changed" };

export type ChatReducerResult = {
  state: ChatStreamState;
  effects: ChatStreamEffect[];
};

export type ChatCommand = AIChatCommand;
export type ChatQueryChoice = QueryChoice;
export type ChatStreamRequest = AIChatStreamRequest;
export type ChatHistoryMessage = AIChatHistoryMessage;
export type ChatAttachmentReference = ChatAttachmentRef;
