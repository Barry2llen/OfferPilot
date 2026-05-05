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
  role: "user" | "assistant" | "tool";
  content: string;
  reasoning?: string;
  toolCallId?: string;
  toolName?: string;
  toolStatus?: string;
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
  const text = extractTextContent(content);
  if (text) {
    return text;
  }

  if (content == null) {
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

export function useChatStream() {
  const { setThreadId, setAgentStatus, bumpChatHistoryVersion } =
    useAppActions();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
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

  const clearStreamingState = useCallback(() => {
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
        setMessages((prev) => [...prev, { role: "user", content: prompt }]);
      }

      let accumulatedText = "";
      let accumulatedReasoning = "";
      const currentToolCalls: ToolCallEntry[] = [];

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
                  bumpChatHistoryVersion();
                }
                break;
              }

              case "token": {
                const token = extractTextContent(
                  event.data.content ?? event.data.token ?? ""
                );
                accumulatedText += token;
                setStreamingText(accumulatedText);
                break;
              }

              case "reasoning": {
                const reasoning = extractTextContent(event.data.content);
                if (!reasoning) {
                  break;
                }
                accumulatedReasoning += reasoning;
                setStreamingReasoning(accumulatedReasoning);
                break;
              }

              case "tool_start": {
                setAgentStatus("tool_calling");
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
                setAgentStatus("generating");
                break;
              }

              case "interrupt": {
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
                const explicitFinalContent = formatDisplayContent(event.data.content);
                const finalContent =
                  explicitFinalContent || accumulatedText || accumulatedReasoning || "";
                const reasoningContent =
                  explicitFinalContent || accumulatedText
                    ? accumulatedReasoning || undefined
                    : undefined;
                if (finalContent) {
                  setMessages((prev) => [
                    ...prev,
                    {
                      role: "assistant",
                      content: finalContent,
                      reasoning: reasoningContent,
                    },
                  ]);
                }
                setStreamingText("");
                setStreamingReasoning("");
                setAgentStatus("idle");
                setIsStreaming(false);
                bumpChatHistoryVersion();
                break;
              }

              case "error": {
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
    ]
  );

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
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
      const msgs: ChatMessage[] = historyMessages.map((m) => ({
        role: m.role as ChatMessage["role"],
        content: formatDisplayContent(m.content),
        toolCallId: m.tool_call_id ?? undefined,
        toolName: m.name ?? undefined,
        toolStatus: m.status ?? undefined,
      }));
      setMessages(msgs);
      clearStreamingState();
    },
    [clearStreamingState]
  );

  return {
    messages,
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
