import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { aiChatApi } from "@/app/lib/api/ai";
import { chatFilesApi } from "@/app/lib/api/chat-files";
import { useAppActions } from "@/app/lib/context/app-context";
import type {
  SSEEvent,
  AIChatHistoryMessage,
  ChatAttachmentRef,
  AIChatCommand,
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

type ChatMessagesUpdater =
  | ChatMessage[]
  | ((prev: ChatMessage[]) => ChatMessage[]);

function extractTextContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }

  if (Array.isArray(content)) {
    const parts = content.flatMap((item) => {
      if (typeof item === "string") {
        return [item];
      }
      if (
        item &&
        typeof item === "object" &&
        "text" in item &&
        typeof item.text === "string"
      ) {
        return [item.text];
      }
      return [];
    });

    return parts.join("");
  }

  return "";
}

function formatDisplayContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }

  const text = extractTextContent(content);
  if (text) {
    return text;
  }

  if (content == null) {
    return "";
  }

  if (Array.isArray(content) && content.length === 0) {
    return "";
  }

  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

function findLastRunningToolCallIndex(
  toolCalls: ToolCallEntry[],
  name: string
): number {
  for (let index = toolCalls.length - 1; index >= 0; index -= 1) {
    if (toolCalls[index].name === name && toolCalls[index].status === "running") {
      return index;
    }
  }

  return -1;
}

function findLastRunningToolMessageIndex(
  messages: ChatMessage[],
  name: string
): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (
      message.role === "tool" &&
      message.toolName === name &&
      message.toolStatus === "running"
    ) {
      return index;
    }
  }

  return -1;
}

function mergeQueryInterruptInput(
  input: Record<string, unknown> | undefined,
  eventData: Record<string, unknown>
): Record<string, unknown> {
  return {
    ...(input ?? {}),
    question:
      typeof eventData.question === "string"
        ? eventData.question
        : input?.question,
    firstChoice:
      typeof eventData.firstChoice === "string"
        ? eventData.firstChoice
        : input?.firstChoice,
    firstChoiceDescription:
      typeof eventData.firstChoiceDescription === "string"
        ? eventData.firstChoiceDescription
        : input?.firstChoiceDescription,
    secondChoice:
      typeof eventData.secondChoice === "string"
        ? eventData.secondChoice
        : input?.secondChoice,
    secondChoiceDescription:
      typeof eventData.secondChoiceDescription === "string"
        ? eventData.secondChoiceDescription
        : input?.secondChoiceDescription,
    thirdChoice:
      typeof eventData.thirdChoice === "string"
        ? eventData.thirdChoice
        : input?.thirdChoice,
    thirdChoiceDescription:
      typeof eventData.thirdChoiceDescription === "string"
        ? eventData.thirdChoiceDescription
        : input?.thirdChoiceDescription,
  };
}

function isQueryInterruptToolError(name: string, detail: string): boolean {
  return name === "query" && detail.includes("Interrupt(") && detail.includes("query");
}

function findLastAssistantMessageIndex(messages: ChatMessage[]): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") {
      return index;
    }
  }

  return -1;
}

function parseDurationMs(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return Math.round(value);
  }

  return undefined;
}

function toolCallToMessage(entry: ToolCallEntry, id: string): ChatMessage {
  return {
    id,
    role: "tool",
    content: formatDisplayContent(entry.output ?? entry.error ?? entry.input ?? ""),
    toolName: entry.name,
    toolStatus: entry.status,
    toolInput: entry.input,
    toolOutput: entry.output,
    toolError: entry.error,
  };
}

function cloneMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((message) => ({
    ...message,
    attachments: message.attachments ? [...message.attachments] : undefined,
  }));
}

function findLastRunningCommittedToolMessageIndex(
  messages: ChatMessage[],
  name: string
): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (
      message.role === "tool" &&
      message.toolName === name &&
      message.toolStatus === "running"
    ) {
      return index;
    }
  }

  return -1;
}

function shouldDisplayHistoryMessage(message: ChatMessage): boolean {
  if (message.role !== "assistant") {
    return true;
  }

  return Boolean(message.content.trim() || message.reasoning?.trim());
}

function normalizeAttachmentRef(
  attachment: ChatAttachmentRef
): ChatAttachmentItem {
  return {
    fileId: attachment.file_id,
    originalFilename: attachment.original_filename,
    mediaType: attachment.media_type,
    injectionMode: attachment.injection_mode,
    pending: false,
    rawUrl: chatFilesApi.rawUrl(attachment.file_id),
  };
}

function parseAttachments(value: unknown): ChatAttachmentItem[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const attachment = item as Partial<ChatAttachmentRef>;
    if (
      typeof attachment.file_id !== "string" ||
      typeof attachment.original_filename !== "string" ||
      typeof attachment.injection_mode !== "string"
    ) {
      return [];
    }
    return [
      normalizeAttachmentRef({
        file_id: attachment.file_id,
        original_filename: attachment.original_filename,
        media_type:
          typeof attachment.media_type === "string" ? attachment.media_type : null,
        injection_mode: attachment.injection_mode,
      }),
    ];
  });
}

function mergeResolvedAttachments(
  current: ChatAttachmentItem[] | undefined,
  resolved: ChatAttachmentItem[]
): ChatAttachmentItem[] {
  if (!current || current.length === 0) {
    return resolved;
  }

  const remaining = [...resolved];
  const merged: ChatAttachmentItem[] = [];

  for (const item of current) {
    let matchIndex = -1;
    if (item.fileId && !item.pending) {
      matchIndex = remaining.findIndex((candidate) => candidate.fileId === item.fileId);
    }
    if (matchIndex < 0) {
      matchIndex = remaining.findIndex(
        (candidate) => candidate.originalFilename === item.originalFilename
      );
    }

    if (matchIndex >= 0) {
      merged.push(remaining.splice(matchIndex, 1)[0]);
    } else {
      merged.push(item);
    }
  }

  return [...merged, ...remaining];
}

function buildStreamBody(
  selectionId: number,
  prompt: string,
  threadId: string | null | undefined,
  command: AIChatCommand | undefined,
  options: ChatStartOptions | undefined
): FormData | {
  selection_id: number;
  prompt?: string | null;
  thread_id?: string | null;
  file_ids?: string[];
  command?: AIChatCommand | null;
} {
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
  if (command) {
    formData.append("command", JSON.stringify(command));
  }
  if (command?.prompt ?? prompt) {
    formData.append("prompt", command?.prompt ?? prompt);
  }
  if (threadId) {
    formData.append("thread_id", threadId);
  }
  for (const fileId of fileIds) {
    formData.append("file_ids", fileId);
  }
  for (const file of localFiles) {
    formData.append("files", file);
  }
  return formData;
}

export function useChatStream() {
  const { t } = useTranslation();
  const {
    setThreadId,
    setThreadRequiresImageInput,
    setAgentStatus,
    bumpChatHistoryVersion,
  } = useAppActions();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [liveMessages, setLiveMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [streamingReasoning, setStreamingReasoning] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolCallEntry[]>([]);
  const [interrupt, setInterrupt] = useState<ChatInterrupt | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const pendingTokenRef = useRef("");
  const rafIdRef = useRef<number | null>(null);
  const messageIdRef = useRef(0);
  const messagesRef = useRef<ChatMessage[]>([]);

  const createMessageId = useCallback((role: ChatMessage["role"]) => {
    messageIdRef.current += 1;
    return `${role}-${messageIdRef.current}`;
  }, []);

  const setCommittedMessages = useCallback((updater: ChatMessagesUpdater) => {
    const next =
      typeof updater === "function" ? updater(messagesRef.current) : updater;
    messagesRef.current = next;
    setMessages(next);
  }, []);

  const clearStreamingState = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    pendingTokenRef.current = "";
    setLiveMessages([]);
    setStreamingText("");
    setStreamingReasoning("");
    setToolCalls([]);
    setInterrupt(null);
    setStreamError(null);
    setIsStreaming(false);
  }, []);

  const clearMessages = useCallback(() => {
    setCommittedMessages([]);
  }, [setCommittedMessages]);

  const startChat = useCallback(
    async (
      selectionId: number,
      prompt: string,
      threadId?: string | null,
      command?: AIChatCommand,
      options?: ChatStartOptions
    ) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      clearStreamingState();
      setStreamError(null);
      setIsStreaming(true);
      setAgentStatus("generating");

      let accumulatedText = "";
      let accumulatedReasoning = "";
      const currentToolCalls: ToolCallEntry[] = [];
      let currentLiveMessages: ChatMessage[] = [];
      let currentAssistantIndex: number | null = null;
      let visibleAssistantText = "";
      let userMessageId: string | null = null;
      let requestAccepted = false;
      let resumedQueryToolEntry: ToolCallEntry | null = null;
      let pendingQueryResumeMerge = command?.type === "query";

      const publishLiveMessages = () => {
        setLiveMessages([...currentLiveMessages]);
      };

      const cancelPendingTokenFrame = () => {
        if (rafIdRef.current !== null) {
          cancelAnimationFrame(rafIdRef.current);
          rafIdRef.current = null;
        }
        pendingTokenRef.current = "";
      };

      const flushTokenFrame = () => {
        if (rafIdRef.current !== null) {
          cancelAnimationFrame(rafIdRef.current);
          rafIdRef.current = null;
        }
        if (
          pendingTokenRef.current &&
          currentAssistantIndex !== null &&
          currentLiveMessages[currentAssistantIndex]?.role === "assistant"
        ) {
          setStreamingText(currentLiveMessages[currentAssistantIndex].content);
          publishLiveMessages();
        }
        pendingTokenRef.current = "";
      };

      const ensureAssistantMessage = () => {
        if (
          currentAssistantIndex === null ||
          currentLiveMessages[currentAssistantIndex]?.role !== "assistant"
        ) {
          currentLiveMessages.push({
            id: createMessageId("assistant"),
            role: "assistant",
            content: "",
          });
          currentAssistantIndex = currentLiveMessages.length - 1;
        }
        return currentAssistantIndex;
      };

      const endAssistantSegment = () => {
        flushTokenFrame();
        currentAssistantIndex = null;
        setStreamingText("");
        setStreamingReasoning("");
      };

      const commitLiveMessages = () => {
        flushTokenFrame();
        const completedLiveMessages = cloneMessages(currentLiveMessages);
        if (completedLiveMessages.length > 0) {
          setCommittedMessages((prev) => [...prev, ...completedLiveMessages]);
        }
        currentLiveMessages = [];
        currentAssistantIndex = null;
        setLiveMessages([]);
        setStreamingText("");
        setStreamingReasoning("");
      };

      const updateLastCommittedRunningToolMessage = (
        name: string,
        entry: ToolCallEntry
      ): boolean => {
        const index = findLastRunningCommittedToolMessageIndex(
          messagesRef.current,
          name
        );
        if (index < 0) {
          return false;
        }

        const next = [...messagesRef.current];
        next[index] = toolCallToMessage(entry, next[index].id);
        setCommittedMessages(next);
        return true;
      };

      const body = buildStreamBody(selectionId, prompt, threadId, command, options);
      const shouldCreateUserMessage = !command || command.type === "prompt";

      if (shouldCreateUserMessage) {
        const newUserMessageId = createMessageId("user");
        userMessageId = newUserMessageId;
        setCommittedMessages((prev) => [
          ...prev,
          {
            id: newUserMessageId,
            role: "user",
            content: prompt,
            attachments: options?.draftAttachments
              ? [...options.draftAttachments]
              : undefined,
          },
        ]);
      }

      const removeOptimisticUserMessage = () => {
        if (!userMessageId) {
          return;
        }
        setCommittedMessages((prev) =>
          prev.filter((message) => message.id !== userMessageId)
        );
      };

      try {
        await aiChatApi.streamChat(
          body,
          (event: SSEEvent) => {
            const kind = event.event || event.type;

            switch (kind) {
              case "thread": {
                const tid =
                  (event.data.thread_id as string) ||
                  (event.data as Record<string, unknown>).thread_id;
                if (typeof tid === "string") {
                  setThreadId(tid);
                }
                if (typeof event.data.requires_image_input === "boolean") {
                  setThreadRequiresImageInput(event.data.requires_image_input);
                }

                if (userMessageId) {
                  const resolvedAttachments = parseAttachments(
                    event.data.resolved_attachments
                  );
                  if (resolvedAttachments.length > 0) {
                    setCommittedMessages((prev) =>
                      prev.map((message) =>
                        message.id === userMessageId
                          ? {
                              ...message,
                              attachments: mergeResolvedAttachments(
                                message.attachments,
                                resolvedAttachments
                              ),
                            }
                          : message
                      )
                    );
                  }
                }
                break;
              }

              case "token": {
                const token = extractTextContent(
                  event.data.content ?? event.data.token ?? ""
                );
                accumulatedText += token;
                if (token) {
                  pendingQueryResumeMerge = false;
                  const assistantIndex = ensureAssistantMessage();
                  const assistantMessage = currentLiveMessages[assistantIndex];
                  assistantMessage.content += token;
                  visibleAssistantText += token;
                  pendingTokenRef.current += token;
                  if (rafIdRef.current === null) {
                    rafIdRef.current = requestAnimationFrame(() => {
                      rafIdRef.current = null;
                      if (pendingTokenRef.current) {
                        setStreamingText(assistantMessage.content);
                        publishLiveMessages();
                        pendingTokenRef.current = "";
                      }
                    });
                  }
                }
                break;
              }

              case "reasoning": {
                const reasoning = extractTextContent(event.data.content);
                if (!reasoning) {
                  break;
                }
                pendingQueryResumeMerge = false;
                flushTokenFrame();
                accumulatedReasoning += reasoning;
                const assistantIndex = ensureAssistantMessage();
                const assistantMessage = currentLiveMessages[assistantIndex];
                assistantMessage.reasoning = `${assistantMessage.reasoning ?? ""}${reasoning}`;
                setStreamingReasoning(assistantMessage.reasoning);
                publishLiveMessages();
                break;
              }

              case "reasoning_done": {
                const durationMs = parseDurationMs(event.data.duration_ms);
                if (durationMs === undefined) {
                  break;
                }
                const assistantIndex =
                  currentAssistantIndex ??
                  findLastAssistantMessageIndex(currentLiveMessages);
                const assistantMessage = currentLiveMessages[assistantIndex];
                if (
                  assistantIndex >= 0 &&
                  assistantMessage?.role === "assistant" &&
                  assistantMessage.reasoning?.trim()
                ) {
                  assistantMessage.reasoningDurationMs = durationMs;
                  publishLiveMessages();
                }
                break;
              }

              case "tool_start": {
                setAgentStatus("tool_calling");
                endAssistantSegment();
                const name = (event.data.tool_name as string) || "unknown_tool";
                const input = event.data.input as
                  | Record<string, unknown>
                  | undefined;
                const entry: ToolCallEntry = {
                  name,
                  input,
                  status: "running",
                };
                if (pendingQueryResumeMerge && name === "query") {
                  resumedQueryToolEntry = entry;
                  pendingQueryResumeMerge = false;
                  if (updateLastCommittedRunningToolMessage(name, entry)) {
                    setToolCalls([entry]);
                    break;
                  }
                  resumedQueryToolEntry = null;
                } else if (name !== "query") {
                  pendingQueryResumeMerge = false;
                }
                currentToolCalls.push(entry);
                setToolCalls([...currentToolCalls]);
                currentLiveMessages.push(toolCallToMessage(entry, createMessageId("tool")));
                publishLiveMessages();
                break;
              }

              case "tool_end": {
                const name = (event.data.tool_name as string) || "unknown_tool";
                const output = event.data.output;
                if (resumedQueryToolEntry && name === "query") {
                  resumedQueryToolEntry = {
                    ...resumedQueryToolEntry,
                    output,
                    status: "success",
                  };
                  updateLastCommittedRunningToolMessage(name, resumedQueryToolEntry);
                  setToolCalls([resumedQueryToolEntry]);
                  resumedQueryToolEntry = null;
                  endAssistantSegment();
                  setAgentStatus("generating");
                  break;
                }
                const idx = findLastRunningToolCallIndex(currentToolCalls, name);
                if (idx >= 0) {
                  currentToolCalls[idx] = {
                    ...currentToolCalls[idx],
                    output,
                    status: "success",
                  };
                } else {
                  currentToolCalls.push({
                    name,
                    output,
                    status: "success",
                  });
                }
                setToolCalls([...currentToolCalls]);
                const toolMessageIndex = findLastRunningToolMessageIndex(
                  currentLiveMessages,
                  name
                );
                const toolEntry =
                  idx >= 0
                    ? currentToolCalls[idx]
                    : currentToolCalls[currentToolCalls.length - 1];
                if (toolMessageIndex >= 0) {
                  currentLiveMessages[toolMessageIndex] = toolCallToMessage(
                    toolEntry,
                    currentLiveMessages[toolMessageIndex].id
                  );
                } else {
                  currentLiveMessages.push(
                    toolCallToMessage(toolEntry, createMessageId("tool"))
                  );
                }
                publishLiveMessages();
                endAssistantSegment();
                setAgentStatus("generating");
                break;
              }

              case "tool_error": {
                const name = (event.data.tool_name as string) || "unknown_tool";
                const errMsg =
                  extractTextContent(event.data.detail ?? event.data.error) ||
                  t("errors.toolError");
                if (isQueryInterruptToolError(name, errMsg)) {
                  break;
                }
                if (resumedQueryToolEntry && name === "query") {
                  resumedQueryToolEntry = {
                    ...resumedQueryToolEntry,
                    error: errMsg,
                    status: "error",
                  };
                  updateLastCommittedRunningToolMessage(name, resumedQueryToolEntry);
                  setToolCalls([resumedQueryToolEntry]);
                  resumedQueryToolEntry = null;
                  endAssistantSegment();
                  setAgentStatus("generating");
                  break;
                }
                const idx = findLastRunningToolCallIndex(currentToolCalls, name);
                if (idx >= 0) {
                  currentToolCalls[idx] = {
                    ...currentToolCalls[idx],
                    error: errMsg,
                    status: "error",
                  };
                } else {
                  currentToolCalls.push({
                    name,
                    error: errMsg,
                    status: "error",
                  });
                }
                setToolCalls([...currentToolCalls]);
                const toolMessageIndex = findLastRunningToolMessageIndex(
                  currentLiveMessages,
                  name
                );
                const toolEntry =
                  idx >= 0
                    ? currentToolCalls[idx]
                    : currentToolCalls[currentToolCalls.length - 1];
                if (toolMessageIndex >= 0) {
                  currentLiveMessages[toolMessageIndex] = toolCallToMessage(
                    toolEntry,
                    currentLiveMessages[toolMessageIndex].id
                  );
                } else {
                  currentLiveMessages.push(
                    toolCallToMessage(toolEntry, createMessageId("tool"))
                  );
                }
                publishLiveMessages();
                endAssistantSegment();
                setAgentStatus("generating");
                break;
              }

              case "interrupt": {
                flushTokenFrame();
                setAgentStatus("interrupted");
                const interruptType = (event.data.type as string) || "other";
                if (interruptType === "query") {
                  const queryCallIndex = findLastRunningToolCallIndex(
                    currentToolCalls,
                    "query"
                  );
                  if (queryCallIndex >= 0) {
                    currentToolCalls[queryCallIndex] = {
                      ...currentToolCalls[queryCallIndex],
                      input: mergeQueryInterruptInput(
                        currentToolCalls[queryCallIndex].input,
                        event.data
                      ),
                    };
                    setToolCalls([...currentToolCalls]);
                  }

                  const queryMessageIndex = findLastRunningToolMessageIndex(
                    currentLiveMessages,
                    "query"
                  );
                  if (queryMessageIndex >= 0) {
                    const message = currentLiveMessages[queryMessageIndex];
                    const input = mergeQueryInterruptInput(
                      message.toolInput,
                      event.data
                    );
                    currentLiveMessages[queryMessageIndex] = {
                      ...message,
                      content: formatDisplayContent(input),
                      toolInput: input,
                    };
                  }
                  commitLiveMessages();
                } else {
                  publishLiveMessages();
                }
                setInterrupt({
                  interruptId: (event.data.id as string) || "",
                  type: interruptType,
                  message:
                    extractTextContent(event.data.message) ||
                    t("errors.agentInterrupted"),
                  question:
                    typeof event.data.question === "string"
                      ? event.data.question
                      : undefined,
                  firstChoice:
                    typeof event.data.firstChoice === "string"
                      ? event.data.firstChoice
                      : undefined,
                  firstChoiceDescription:
                    typeof event.data.firstChoiceDescription === "string"
                      ? event.data.firstChoiceDescription
                      : undefined,
                  secondChoice:
                    typeof event.data.secondChoice === "string"
                      ? event.data.secondChoice
                      : undefined,
                  secondChoiceDescription:
                    typeof event.data.secondChoiceDescription === "string"
                      ? event.data.secondChoiceDescription
                      : undefined,
                  thirdChoice:
                    typeof event.data.thirdChoice === "string"
                      ? event.data.thirdChoice
                      : undefined,
                  thirdChoiceDescription:
                    typeof event.data.thirdChoiceDescription === "string"
                      ? event.data.thirdChoiceDescription
                      : undefined,
                });
                setIsStreaming(false);
                bumpChatHistoryVersion();
                break;
              }

              case "final": {
                flushTokenFrame();
                const explicitFinalContent = formatDisplayContent(event.data.content);
                const hasVisibleAssistantContent = currentLiveMessages.some(
                  (message) =>
                    message.role === "assistant" && Boolean(message.content.trim())
                );
                const finalContent =
                  explicitFinalContent ||
                  (hasVisibleAssistantContent ? "" : visibleAssistantText) ||
                  "";
                const reasoningContent =
                  explicitFinalContent || accumulatedText
                    ? accumulatedReasoning || undefined
                    : undefined;
                const lastLiveMessage =
                  currentLiveMessages[currentLiveMessages.length - 1];
                const lastMessageHasVisibleAssistantContent =
                  lastLiveMessage?.role === "assistant" &&
                  lastLiveMessage.content.trim();
                if (finalContent && !lastMessageHasVisibleAssistantContent) {
                  if (lastLiveMessage?.role === "assistant") {
                    lastLiveMessage.content = finalContent;
                    if (!lastLiveMessage.reasoning && reasoningContent) {
                      lastLiveMessage.reasoning = reasoningContent;
                    }
                  } else {
                    currentLiveMessages.push({
                      id: createMessageId("assistant"),
                      role: "assistant",
                      content: finalContent,
                      reasoning: reasoningContent,
                    });
                  }
                }
                commitLiveMessages();
                setToolCalls([]);
                setAgentStatus("idle");
                setIsStreaming(false);
                bumpChatHistoryVersion();
                break;
              }

              case "error": {
                cancelPendingTokenFrame();
                const errMsg =
                  (event.data.detail as string) ||
                  (event.data.message as string) ||
                  t("errors.streamError");
                setStreamError(errMsg);
                setAgentStatus("error");
                setIsStreaming(false);
                break;
              }
            }
          },
          (error: Error) => {
            if (rafIdRef.current !== null) {
              cancelAnimationFrame(rafIdRef.current);
              rafIdRef.current = null;
            }
            pendingTokenRef.current = "";
            if (!requestAccepted) {
              removeOptimisticUserMessage();
            }
            setStreamError(error.message);
            setAgentStatus("error");
            setIsStreaming(false);
          },
          controller.signal,
          () => {
            requestAccepted = true;
            options?.onAccepted?.();
          }
        );

        if (!controller.signal.aborted) {
          setIsStreaming(false);
        } else if (!requestAccepted) {
          removeOptimisticUserMessage();
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          if (rafIdRef.current !== null) {
            cancelAnimationFrame(rafIdRef.current);
            rafIdRef.current = null;
          }
          pendingTokenRef.current = "";
          if (!requestAccepted) {
            removeOptimisticUserMessage();
          }
          setStreamError(err.message);
          setAgentStatus("error");
          setIsStreaming(false);
        }
      }
    },
    [
      bumpChatHistoryVersion,
      clearStreamingState,
      setAgentStatus,
      setThreadId,
      setThreadRequiresImageInput,
      createMessageId,
      setCommittedMessages,
      t,
    ]
  );

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    pendingTokenRef.current = "";
    setIsStreaming(false);
    setAgentStatus("idle");
  }, [setAgentStatus]);

  const retry = useCallback(
    (selectionId: number, threadId: string) => {
      clearStreamingState();
      startChat(selectionId, "", threadId, { type: "retry" });
    },
    [clearStreamingState, startChat]
  );

  const answerQuery = useCallback(
    (
      selectionId: number,
      threadId: string,
      choice: QueryChoice,
      note?: string | null
    ) => {
      clearStreamingState();
      startChat(selectionId, "", threadId, {
        type: "query",
        choice,
        note: note?.trim() || null,
      });
    },
    [clearStreamingState, startChat]
  );

  const loadHistory = useCallback(
    (historyMessages: AIChatHistoryMessage[]) => {
      const msgs: ChatMessage[] = historyMessages
        .map((message) => ({
          id: createMessageId((message.role as ChatMessage["role"]) || "assistant"),
          role: message.role as ChatMessage["role"],
          content: formatDisplayContent(message.content),
          attachments: Array.isArray(message.attachments)
            ? message.attachments.map(normalizeAttachmentRef)
            : undefined,
          reasoning:
            typeof message.reasoning === "string" ? message.reasoning : undefined,
          reasoningDurationMs: parseDurationMs(message.reasoning_duration_ms),
          toolCallId: message.tool_call_id ?? undefined,
          toolName: message.name ?? undefined,
          toolStatus: message.status ?? undefined,
          toolOutput: message.role === "tool" ? message.content : undefined,
        }))
        .filter(shouldDisplayHistoryMessage);
      setCommittedMessages(msgs);
      clearStreamingState();
    },
    [clearStreamingState, createMessageId, setCommittedMessages]
  );

  return {
    messages,
    liveMessages,
    streamingText,
    streamingReasoning,
    toolCalls,
    interrupt,
    streamError,
    isStreaming,
    startChat,
    stopStream,
    retry,
    answerQuery,
    loadHistory,
    clearMessages,
    resetStreamingState: clearStreamingState,
  };
}
