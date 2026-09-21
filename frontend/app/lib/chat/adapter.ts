import type {
  AIChatCommand,
  AIChatHistoryMessage,
  ChatAttachmentRef,
} from "@/app/lib/api/types";
import type {
  ChatAttachmentItem,
  ChatCommand,
  ChatHistoryMessage,
  ChatMessage,
  ChatStartOptions,
  ChatStreamEffect,
  ChatStreamEvent,
  ChatStreamLabels,
  ChatStreamRequest,
  ChatStreamState,
  ChatReducerResult,
  ToolCallEntry,
} from "./types";

export function extractTextContent(content: unknown): string {
  if (typeof content === "string") return content;

  if (Array.isArray(content)) {
    return content
      .flatMap((item) => {
        if (typeof item === "string") return [item];
        if (
          item &&
          typeof item === "object" &&
          "text" in item &&
          typeof item.text === "string"
        ) {
          return [item.text];
        }
        return [];
      })
      .join("");
  }

  return "";
}

export function formatDisplayContent(content: unknown): string {
  if (typeof content === "string") return content;

  const text = extractTextContent(content);
  if (text) return text;
  if (content == null) return "";
  if (Array.isArray(content) && content.length === 0) return "";

  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

export function parseDurationMs(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return Math.round(value);
  }
  return undefined;
}

export function cloneMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((message) => ({
    ...message,
    attachments: message.attachments ? [...message.attachments] : undefined,
  }));
}

function nextMessageId(
  state: ChatStreamState,
  role: ChatMessage["role"],
): { id: string; nextMessageId: number } {
  const nextMessageId = state.nextMessageId + 1;
  return { id: `${role}-${nextMessageId}`, nextMessageId };
}

export function createChatState(
  messages: ChatMessage[] = [],
  nextMessageId = 0,
): ChatStreamState {
  return {
    messages: cloneMessages(messages),
    liveMessages: [],
    streamingText: "",
    streamingReasoning: "",
    toolCalls: [],
    streamError: null,
    isStreaming: false,
    agentStatus: "idle",
    contextCompactionStatus: "idle",
    contextCompacted: false,
    accepted: false,
    terminal: false,
    userMessageId: null,
    currentAssistantIndex: null,
    accumulatedText: "",
    accumulatedReasoning: "",
    visibleAssistantText: "",
    nextMessageId,
  };
}

export function resetChatTransient(state: ChatStreamState): ChatStreamState {
  return {
    ...state,
    liveMessages: [],
    streamingText: "",
    streamingReasoning: "",
    toolCalls: [],
    streamError: null,
    isStreaming: false,
    agentStatus: "idle",
    accepted: false,
    terminal: false,
    userMessageId: null,
    currentAssistantIndex: null,
    accumulatedText: "",
    accumulatedReasoning: "",
    visibleAssistantText: "",
  };
}

export function beginChat(
  state: ChatStreamState,
  prompt: string,
  command: ChatCommand | undefined,
  options?: ChatStartOptions,
): ChatStreamState {
  let next = resetChatTransient(state);
  next = { ...next, isStreaming: true, agentStatus: "generating" };

  if (!command || command.type === "prompt") {
    const messageId = nextMessageId(next, "user");
    next = {
      ...next,
      nextMessageId: messageId.nextMessageId,
      userMessageId: messageId.id,
      messages: [
        ...next.messages,
        {
          id: messageId.id,
          role: "user",
          content: prompt,
          attachments: options?.draftAttachments
            ? [...options.draftAttachments]
            : undefined,
        },
      ],
    };
  }

  return {
    ...next,
  };
}

export function clearCommittedMessages(
  state: ChatStreamState,
): ChatStreamState {
  return {
    ...resetChatTransient(state),
    messages: [],
    contextCompactionStatus: "idle",
    contextCompacted: false,
  };
}

function findLastRunningToolCallIndex(
  toolCalls: ToolCallEntry[],
  name: string,
  toolCallId?: string,
): number {
  for (let index = toolCalls.length - 1; index >= 0; index -= 1) {
    if (
      toolCallId
        ? toolCalls[index].toolCallId === toolCallId
        : toolCalls[index].name === name &&
          toolCalls[index].status === "running"
    ) {
      return index;
    }
  }
  return -1;
}

function findLastRunningToolMessageIndex(
  messages: ChatMessage[],
  name: string,
  toolCallId?: string,
): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (
      message.role === "tool" &&
      (toolCallId
        ? message.toolCallId === toolCallId
        : message.toolName === name && message.toolStatus === "running")
    ) {
      return index;
    }
  }
  return -1;
}

function findLastAssistantMessageIndex(messages: ChatMessage[]): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") return index;
  }
  return -1;
}

function toolCallToMessage(entry: ToolCallEntry, id: string): ChatMessage {
  return {
    id,
    role: "tool",
    content: formatDisplayContent(
      entry.output ?? entry.error ?? entry.input ?? "",
    ),
    toolName: entry.name,
    toolCallId: entry.toolCallId,
    toolStatus: entry.status,
    toolInput: entry.input,
    toolOutput: entry.output,
    toolError: entry.error,
  };
}

function normalizeAttachmentRef(
  attachment: ChatAttachmentRef,
  rawUrl?: (fileId: string) => string,
): ChatAttachmentItem {
  return {
    fileId: attachment.file_id,
    originalFilename: attachment.original_filename,
    mediaType: attachment.media_type,
    injectionMode: attachment.injection_mode,
    pending: false,
    rawUrl: rawUrl?.(attachment.file_id),
  };
}

export function parseAttachments(
  value: unknown,
  rawUrl?: (fileId: string) => string,
): ChatAttachmentItem[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const attachment = item as Partial<ChatAttachmentRef>;
    if (
      typeof attachment.file_id !== "string" ||
      typeof attachment.original_filename !== "string" ||
      typeof attachment.injection_mode !== "string"
    ) {
      return [];
    }
    return [
      normalizeAttachmentRef(
        {
          file_id: attachment.file_id,
          original_filename: attachment.original_filename,
          media_type:
            typeof attachment.media_type === "string"
              ? attachment.media_type
              : null,
          injection_mode: attachment.injection_mode,
        },
        rawUrl,
      ),
    ];
  });
}

export function mergeResolvedAttachments(
  current: ChatAttachmentItem[] | undefined,
  resolved: ChatAttachmentItem[],
): ChatAttachmentItem[] {
  if (!current || current.length === 0) return resolved;

  const remaining = [...resolved];
  const merged: ChatAttachmentItem[] = [];
  for (const item of current) {
    let matchIndex = -1;
    if (item.fileId && !item.pending) {
      matchIndex = remaining.findIndex(
        (candidate) => candidate.fileId === item.fileId,
      );
    }
    if (matchIndex < 0) {
      matchIndex = remaining.findIndex(
        (candidate) => candidate.originalFilename === item.originalFilename,
      );
    }
    if (matchIndex >= 0) merged.push(remaining.splice(matchIndex, 1)[0]);
    else merged.push(item);
  }
  return [...merged, ...remaining];
}

export function buildStreamBody(
  selectionId: number,
  prompt: string,
  threadId: string | null | undefined,
  command: AIChatCommand | undefined,
  options: ChatStartOptions | undefined,
): FormData | ChatStreamRequest {
  const fileIds = options?.fileIds ?? [];
  const localFiles = options?.localFiles ?? [];

  if (fileIds.length === 0 && localFiles.length === 0) {
    return {
      selection_id: selectionId,
      prompt: command ? (command.prompt ?? null) : prompt,
      thread_id: threadId ?? null,
      file_ids: fileIds,
      command: command ?? null,
    };
  }

  const formData = new FormData();
  formData.append("selection_id", String(selectionId));
  if (command) formData.append("command", JSON.stringify(command));
  if (command?.prompt ?? prompt) {
    formData.append("prompt", command?.prompt ?? prompt);
  }
  if (threadId) formData.append("thread_id", threadId);
  for (const fileId of fileIds) formData.append("file_ids", fileId);
  for (const file of localFiles) formData.append("files", file);
  return formData;
}

function ensureAssistantMessage(state: ChatStreamState): {
  state: ChatStreamState;
  index: number;
} {
  if (
    state.currentAssistantIndex !== null &&
    state.liveMessages[state.currentAssistantIndex]?.role === "assistant"
  ) {
    return { state, index: state.currentAssistantIndex };
  }

  const messageId = nextMessageId(state, "assistant");
  const message: ChatMessage = {
    id: messageId.id,
    role: "assistant",
    content: "",
  };
  const index = state.liveMessages.length;
  return {
    state: {
      ...state,
      liveMessages: [...state.liveMessages, message],
      currentAssistantIndex: index,
      nextMessageId: messageId.nextMessageId,
    },
    index,
  };
}

function endAssistantSegment(state: ChatStreamState): ChatStreamState {
  return {
    ...state,
    currentAssistantIndex: null,
    streamingText: "",
    streamingReasoning: "",
  };
}

function commitLiveMessages(state: ChatStreamState): ChatStreamState {
  const completed = cloneMessages(state.liveMessages);
  return {
    ...state,
    messages: completed.length
      ? [...state.messages, ...completed]
      : state.messages,
    liveMessages: [],
    currentAssistantIndex: null,
    streamingText: "",
    streamingReasoning: "",
  };
}

function updateRunningToolMessage(
  state: ChatStreamState,
  name: string,
  entry: ToolCallEntry,
): ChatStreamState {
  const index = findLastRunningToolMessageIndex(
    state.liveMessages,
    name,
    entry.toolCallId,
  );
  const liveMessages = [...state.liveMessages];
  if (index >= 0) {
    liveMessages[index] = toolCallToMessage(entry, liveMessages[index].id);
  } else {
    const messageId = nextMessageId(state, "tool");
    liveMessages.push(toolCallToMessage(entry, messageId.id));
    return {
      ...state,
      liveMessages,
      nextMessageId: messageId.nextMessageId,
    };
  }
  return { ...state, liveMessages };
}

function addAgentStatusEffect(
  effects: ChatStreamEffect[],
  value: ChatStreamState["agentStatus"],
): void {
  effects.push({ type: "agent_status", value });
}

export function reduceChatEvent(
  state: ChatStreamState,
  event: ChatStreamEvent,
  labels: ChatStreamLabels,
): ChatReducerResult {
  const effects: ChatStreamEffect[] = state.accepted
    ? []
    : [{ type: "accepted" }];
  let next: ChatStreamState = { ...state, accepted: true };
  const data = event.data;

  switch (event.event) {
    case "thread": {
      if (typeof data.thread_id === "string") {
        effects.push({ type: "thread_updated", threadId: data.thread_id });
      }
      if (typeof data.requires_image_input === "boolean") {
        effects.push({
          type: "requires_image_input",
          value: data.requires_image_input,
        });
      }
      if (next.userMessageId) {
        const resolvedAttachments = parseAttachments(
          data.resolved_attachments,
          labels.rawAttachmentUrl,
        );
        if (resolvedAttachments.length > 0) {
          next = {
            ...next,
            messages: next.messages.map((message) =>
              message.id === next.userMessageId
                ? {
                    ...message,
                    attachments: mergeResolvedAttachments(
                      message.attachments,
                      resolvedAttachments,
                    ),
                  }
                : message,
            ),
          };
        }
      }
      break;
    }

    case "context_compaction": {
      const phase = data.phase;
      if (phase === "started") {
        next = {
          ...next,
          contextCompactionStatus: "running",
          streamError: null,
          agentStatus: "compacting",
        };
        addAgentStatusEffect(effects, "compacting");
      } else if (phase === "completed") {
        next = {
          ...next,
          contextCompactionStatus: "completed",
          contextCompacted: true,
          agentStatus: "generating",
        };
        addAgentStatusEffect(effects, "generating");
      } else if (phase === "failed") {
        next = {
          ...next,
          contextCompactionStatus: "failed",
          agentStatus: "error",
        };
        addAgentStatusEffect(effects, "error");
      }
      break;
    }

    case "token": {
      const token = extractTextContent(data.content ?? data.token ?? "");
      if (!token) break;
      const ensured = ensureAssistantMessage(next);
      const liveMessages = [...ensured.state.liveMessages];
      const assistantMessage = liveMessages[ensured.index];
      liveMessages[ensured.index] = {
        ...assistantMessage,
        content: assistantMessage.content + token,
      };
      next = {
        ...ensured.state,
        liveMessages,
        streamingText: liveMessages[ensured.index].content,
        accumulatedText: ensured.state.accumulatedText + token,
        visibleAssistantText: ensured.state.visibleAssistantText + token,
      };
      break;
    }

    case "reasoning": {
      const reasoning = extractTextContent(data.content);
      if (!reasoning) break;
      const ensured = ensureAssistantMessage(next);
      const liveMessages = [...ensured.state.liveMessages];
      const assistantMessage = liveMessages[ensured.index];
      const nextReasoning = `${assistantMessage.reasoning ?? ""}${reasoning}`;
      liveMessages[ensured.index] = {
        ...assistantMessage,
        reasoning: nextReasoning,
      };
      next = {
        ...ensured.state,
        liveMessages,
        streamingReasoning: nextReasoning,
        accumulatedReasoning: ensured.state.accumulatedReasoning + reasoning,
      };
      break;
    }

    case "reasoning_done": {
      const durationMs = parseDurationMs(data.duration_ms);
      if (durationMs === undefined) break;
      const assistantIndex =
        next.currentAssistantIndex ??
        findLastAssistantMessageIndex(next.liveMessages);
      const assistantMessage = next.liveMessages[assistantIndex];
      if (
        assistantIndex >= 0 &&
        assistantMessage?.role === "assistant" &&
        assistantMessage.reasoning?.trim()
      ) {
        const liveMessages = [...next.liveMessages];
        liveMessages[assistantIndex] = {
          ...assistantMessage,
          reasoningDurationMs: durationMs,
        };
        next = { ...next, liveMessages };
      }
      break;
    }

    case "tool_start": {
      addAgentStatusEffect(effects, "tool_calling");
      next = endAssistantSegment(next);
      const name =
        typeof data.tool_name === "string" ? data.tool_name : "unknown_tool";
      const input = data.input as Record<string, unknown> | undefined;
      const entry: ToolCallEntry = {
        name,
        input,
        status: "running",
        toolCallId:
          typeof data.tool_call_id === "string" ? data.tool_call_id : undefined,
      };

      const messageId = nextMessageId(next, "tool");
      next = {
        ...next,
        toolCalls: [...next.toolCalls, entry],
        liveMessages: [
          ...next.liveMessages,
          toolCallToMessage(entry, messageId.id),
        ],
        nextMessageId: messageId.nextMessageId,
      };
      break;
    }

    case "tool_end": {
      const name =
        typeof data.tool_name === "string" ? data.tool_name : "unknown_tool";
      const output = data.output;
      const index = findLastRunningToolCallIndex(
        next.toolCalls,
        name,
        data.tool_call_id as string | undefined,
      );
      const toolCalls = [...next.toolCalls];
      if (index >= 0) {
        toolCalls[index] = { ...toolCalls[index], output, status: "success" };
      } else {
        toolCalls.push({
          name,
          output,
          status: "success",
          toolCallId: data.tool_call_id as string | undefined,
        });
      }
      const entry =
        index >= 0 ? toolCalls[index] : toolCalls[toolCalls.length - 1];
      next = updateRunningToolMessage({ ...next, toolCalls }, name, entry);
      next = endAssistantSegment(next);
      addAgentStatusEffect(effects, "generating");
      break;
    }

    case "tool_error": {
      const name =
        typeof data.tool_name === "string" ? data.tool_name : "unknown_tool";
      const detail =
        extractTextContent(data.detail ?? data.error) || labels.toolError;

      const index = findLastRunningToolCallIndex(
        next.toolCalls,
        name,
        data.tool_call_id as string | undefined,
      );
      const toolCalls = [...next.toolCalls];
      if (index >= 0) {
        toolCalls[index] = {
          ...toolCalls[index],
          error: detail,
          status: "error",
        };
      } else {
        toolCalls.push({
          name,
          error: detail,
          status: "error",
          toolCallId: data.tool_call_id as string | undefined,
        });
      }
      const entry =
        index >= 0 ? toolCalls[index] : toolCalls[toolCalls.length - 1];
      next = updateRunningToolMessage({ ...next, toolCalls }, name, entry);
      next = endAssistantSegment(next);
      addAgentStatusEffect(effects, "generating");
      break;
    }

    case "final": {
      const explicitFinalContent = formatDisplayContent(data.content);
      const hasVisibleAssistantContent = next.liveMessages.some(
        (message) =>
          message.role === "assistant" && Boolean(message.content.trim()),
      );
      const finalContent =
        explicitFinalContent ||
        (hasVisibleAssistantContent ? "" : next.visibleAssistantText) ||
        "";
      const reasoningContent =
        explicitFinalContent || next.accumulatedText
          ? next.accumulatedReasoning || undefined
          : undefined;
      const lastLiveMessage = next.liveMessages[next.liveMessages.length - 1];
      const lastMessageHasVisibleAssistantContent =
        lastLiveMessage?.role === "assistant" &&
        Boolean(lastLiveMessage.content.trim());

      if (finalContent && !lastMessageHasVisibleAssistantContent) {
        if (lastLiveMessage?.role === "assistant") {
          const liveMessages = [...next.liveMessages];
          const index = liveMessages.length - 1;
          liveMessages[index] = {
            ...lastLiveMessage,
            content: finalContent,
            reasoning: lastLiveMessage.reasoning || reasoningContent,
          };
          next = { ...next, liveMessages };
        } else {
          const messageId = nextMessageId(next, "assistant");
          next = {
            ...next,
            liveMessages: [
              ...next.liveMessages,
              {
                id: messageId.id,
                role: "assistant",
                content: finalContent,
                reasoning: reasoningContent,
              },
            ],
            nextMessageId: messageId.nextMessageId,
          };
        }
      }

      next = commitLiveMessages(next);
      next = {
        ...next,
        toolCalls: [],
        isStreaming: false,
        terminal: true,
      };
      addAgentStatusEffect(effects, "idle");
      effects.push({ type: "history_changed" });
      break;
    }

    case "error": {
      const message =
        (typeof data.detail === "string" && data.detail) ||
        (typeof data.message === "string" && data.message) ||
        labels.streamError;
      next = {
        ...next,
        streamError: message,
        isStreaming: false,
        terminal: true,
      };
      addAgentStatusEffect(effects, "error");
      break;
    }
  }

  return { state: next, effects };
}

function removeUnacceptedUserMessage(state: ChatStreamState): ChatStreamState {
  if (!state.userMessageId || state.accepted) return state;
  return {
    ...state,
    messages: state.messages.filter(
      (message) => message.id !== state.userMessageId,
    ),
    userMessageId: null,
  };
}

export function reduceChatTransportError(
  state: ChatStreamState,
  message: string,
): ChatReducerResult {
  const next = removeUnacceptedUserMessage({
    ...state,
    streamError: message,
    isStreaming: false,
    terminal: true,
    agentStatus: "error",
  });
  return {
    state: next,
    effects: [{ type: "agent_status", value: "error" }],
  };
}

export function reduceChatEof(
  state: ChatStreamState,
  labels: ChatStreamLabels,
): ChatReducerResult {
  if (state.terminal)
    return { state: { ...state, isStreaming: false }, effects: [] };
  return reduceChatTransportError(state, labels.incompleteStream);
}

export function reduceChatAbort(state: ChatStreamState): ChatReducerResult {
  const contextCompactionStatus =
    state.contextCompactionStatus === "running"
      ? state.contextCompacted
        ? "completed"
        : "idle"
      : state.contextCompactionStatus;
  return {
    state: removeUnacceptedUserMessage({
      ...state,
      isStreaming: false,
      contextCompactionStatus,
      agentStatus: "idle",
    }),
    effects: [],
  };
}

function shouldDisplayHistoryMessage(message: ChatMessage): boolean {
  if (message.role !== "assistant") return true;
  return Boolean(message.content.trim() || message.reasoning?.trim());
}

export function mapChatHistory(
  historyMessages: AIChatHistoryMessage[] | ChatHistoryMessage[],
  state: ChatStreamState,
  rawUrl?: (fileId: string) => string,
  contextCompacted = false,
): ChatReducerResult {
  let next = resetChatTransient(state);
  const messages: ChatMessage[] = [];
  for (const message of historyMessages) {
    const messageId = nextMessageId(
      next,
      (message.role as ChatMessage["role"]) || "assistant",
    );
    next = { ...next, nextMessageId: messageId.nextMessageId };
    const mapped: ChatMessage = {
      id: messageId.id,
      role: message.role as ChatMessage["role"],
      content: formatDisplayContent(message.content),
      attachments: Array.isArray(message.attachments)
        ? message.attachments.map((attachment) =>
            normalizeAttachmentRef(attachment, rawUrl),
          )
        : undefined,
      reasoning:
        typeof message.reasoning === "string" ? message.reasoning : undefined,
      reasoningDurationMs: parseDurationMs(message.reasoning_duration_ms),
      toolCallId: message.tool_call_id ?? undefined,
      toolName: message.name ?? undefined,
      toolStatus: message.status ?? undefined,
      toolOutput: message.role === "tool" ? message.content : undefined,
    };
    if (shouldDisplayHistoryMessage(mapped)) messages.push(mapped);
  }
  return {
    state: {
      ...next,
      messages,
      contextCompactionStatus: contextCompacted ? "completed" : "idle",
      contextCompacted,
    },
    effects: [],
  };
}
