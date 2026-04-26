"use client";

import { useState, useRef, useCallback } from "react";
import { aiChatApi } from "@/app/lib/api/ai";
import { useAppActions } from "@/app/lib/context/app-context";
import type {
  SSEEvent,
  AIChatHistoryMessage,
  SSEToolCallData,
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
  toolCallId?: string;
  toolName?: string;
  toolStatus?: string;
}

export function useChatStream() {
  const { setThreadId, setAgentStatus } = useAppActions();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
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
    setToolCalls([]);
    setInterrupt(null);
    setStreamError(null);
    setIsStreaming(false);
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
                }
                break;
              }

              case "token": {
                const token =
                  (event.data.content as string) ||
                  (event.data.token as string) ||
                  "";
                accumulatedText += token;
                setStreamingText(accumulatedText);
                break;
              }

              case "tool_start": {
                setAgentStatus("tool_calling");
                const name =
                  (event.data.name as string) || "unknown_tool";
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
                const name =
                  (event.data.name as string) || "unknown_tool";
                const output = event.data.output;
                const idx = currentToolCalls.findIndex(
                  (t) => t.name === name && t.status === "running"
                );
                if (idx >= 0) {
                  currentToolCalls[idx] = {
                    ...currentToolCalls[idx],
                    output,
                    status: "success",
                  };
                  setToolCalls([...currentToolCalls]);
                }
                setAgentStatus("generating");
                break;
              }

              case "tool_error": {
                const name =
                  (event.data.name as string) || "unknown_tool";
                const errMsg = (event.data.error as string) || "Tool error";
                const idx = currentToolCalls.findIndex(
                  (t) => t.name === name && t.status === "running"
                );
                if (idx >= 0) {
                  currentToolCalls[idx] = {
                    ...currentToolCalls[idx],
                    error: errMsg,
                    status: "error",
                  };
                  setToolCalls([...currentToolCalls]);
                }
                setAgentStatus("generating");
                break;
              }

              case "interrupt": {
                setAgentStatus("interrupted");
                setInterrupt({
                  interruptId:
                    (event.data.interrupt_id as string) || "",
                  message:
                    (event.data.message as string) ||
                    "Agent interrupted",
                });
                break;
              }

              case "final": {
                const finalContent =
                  (event.data.content as string) ||
                  accumulatedText ||
                  "";
                setMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: finalContent },
                ]);
                setStreamingText("");
                setAgentStatus("idle");
                setIsStreaming(false);
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
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          setStreamError(err.message);
          setAgentStatus("error");
          setIsStreaming(false);
        }
      }
    },
    [clearStreamingState, setAgentStatus, setThreadId]
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
        content:
          typeof m.content === "string" ? m.content : JSON.stringify(m.content),
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
    toolCalls,
    interrupt,
    streamError,
    isStreaming,
    startChat,
    stopStream,
    retry,
    loadHistory,
    clearMessages: () => setMessages([]),
    setMessages,
  };
}
