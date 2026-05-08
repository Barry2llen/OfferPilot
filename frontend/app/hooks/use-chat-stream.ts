"use client";

import { useState, useRef, useCallback } from "react";
import { aiChatApi } from "@/app/lib/api/ai";
import { useAppActions } from "@/app/lib/context/app-context";
import type {
  SSEEvent,
  AIChatHistoryMessage,
} from "@/app/lib/api/types";

export interface ToolCallEntry {
  name: string;
  input?: Record<string, unknown>;
  output?: unknown;
  error?: string;
  status: "running" | "success" | "error";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  reasoning?: string;
  reasoningDurationMs?: number;
  toolCallId?: string;
  toolName?: string;
  toolStatus?: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: unknown;
  toolError?: string;
}

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
  return messages.map((message) => ({ ...message }));
}

function shouldDisplayHistoryMessage(message: ChatMessage): boolean {
  if (message.role !== "assistant") {
    return true;
  }

  return Boolean(message.content.trim() || message.reasoning?.trim());
}

export function useChatStream() {
  const { setThreadId, setAgentStatus, bumpChatHistoryVersion } =
    useAppActions();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [liveMessages, setLiveMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [streamingReasoning, setStreamingReasoning] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolCallEntry[]>([]);
  const [interrupt, setInterrupt] = useState<{
    interruptId: string;
    message: string;
  } | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const pendingTokenRef = useRef("");
  const rafIdRef = useRef<number | null>(null);
  const messageIdRef = useRef(0);

  const createMessageId = useCallback((role: ChatMessage["role"]) => {
    messageIdRef.current += 1;
    return `${role}-${messageIdRef.current}`;
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
    setMessages([]);
  }, []);

  const startChat = useCallback(
    async (
      selectionId: number,
      prompt: string,
      threadId?: string | null,
      command?: { type: "prompt" | "continue" | "retry"; prompt?: string | null }
    ) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      clearStreamingState();
      setStreamError(null);
      setIsStreaming(true);
      setAgentStatus("generating");

      if (!command || command.type === "prompt") {
        setMessages((prev) => [
          ...prev,
          { id: createMessageId("user"), role: "user", content: prompt },
        ]);
      }

      let accumulatedText = "";
      let accumulatedReasoning = "";
      const currentToolCalls: ToolCallEntry[] = [];
      let currentLiveMessages: ChatMessage[] = [];
      let currentAssistantIndex: number | null = null;
      let visibleAssistantText = "";

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

      try {
        await aiChatApi.streamChat(
          {
            selection_id: selectionId,
            prompt: command ? (command.prompt ?? null) : prompt,
            thread_id: threadId ?? null,
            command: command ?? null,
          },
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
                break;
              }

              case "token": {
                const token = extractTextContent(
                  event.data.content ?? event.data.token ?? ""
                );
                accumulatedText += token;
                if (token) {
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
                currentToolCalls.push(entry);
                setToolCalls([...currentToolCalls]);
                currentLiveMessages.push(toolCallToMessage(entry, createMessageId("tool")));
                publishLiveMessages();
                break;
              }

              case "tool_end": {
                const name = (event.data.tool_name as string) || "unknown_tool";
                const output = event.data.output;
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
                  "Tool error";
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
                cancelPendingTokenFrame();
                setAgentStatus("interrupted");
                setInterrupt({
                  interruptId: (event.data.id as string) || "",
                  message: extractTextContent(event.data.message) || "Agent interrupted",
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
                const completedLiveMessages = cloneMessages(currentLiveMessages);
                if (completedLiveMessages.length > 0) {
                  setMessages((prev) => [...prev, ...completedLiveMessages]);
                }
                currentLiveMessages = [];
                currentAssistantIndex = null;
                setLiveMessages([]);
                setStreamingText("");
                setStreamingReasoning("");
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
                  "Stream error";
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
            setStreamError(error.message);
            setAgentStatus("error");
            setIsStreaming(false);
          },
          controller.signal
        );

        if (!controller.signal.aborted) {
          setIsStreaming(false);
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          if (rafIdRef.current !== null) {
            cancelAnimationFrame(rafIdRef.current);
            rafIdRef.current = null;
          }
          pendingTokenRef.current = "";
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
      createMessageId,
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

  const loadHistory = useCallback(
    (historyMessages: AIChatHistoryMessage[]) => {
      const msgs: ChatMessage[] = historyMessages
        .map((m) => ({
          id: createMessageId((m.role as ChatMessage["role"]) || "assistant"),
          role: m.role as ChatMessage["role"],
          content: formatDisplayContent(m.content),
          reasoning: typeof m.reasoning === "string" ? m.reasoning : undefined,
          reasoningDurationMs: parseDurationMs(m.reasoning_duration_ms),
          toolCallId: m.tool_call_id ?? undefined,
          toolName: m.name ?? undefined,
          toolStatus: m.status ?? undefined,
          toolOutput: m.role === "tool" ? m.content : undefined,
        }))
        .filter(shouldDisplayHistoryMessage);
      setMessages(msgs);
      clearStreamingState();
    },
    [clearStreamingState, createMessageId]
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
    loadHistory,
    clearMessages,
    resetStreamingState: clearStreamingState,
  };
}
