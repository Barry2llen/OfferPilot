import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { aiChatApi } from "@/app/lib/api/ai";
import { chatFilesApi } from "@/app/lib/api/chat-files";
import { useAppActions } from "@/app/lib/context/app-context";
import type { AIChatCommand, AIChatHistoryMessage, QueryChoice } from "@/app/lib/api/types";
import {
  beginChat,
  buildStreamBody,
  clearCommittedMessages,
  createChatState,
  mapChatHistory,
  reduceChatAbort,
  reduceChatEof,
  reduceChatEvent,
  reduceChatTransportError,
  resetChatTransient,
} from "@/app/lib/chat/adapter";
import type {
  ChatInterrupt,
  ChatStartOptions,
  ChatStreamEffect,
  ChatStreamLabels,
  ChatStreamState,
} from "@/app/lib/chat/types";

export function useChatStream() {
  const { t } = useTranslation();
  const {
    setThreadId,
    setThreadRequiresImageInput,
    setAgentStatus,
    bumpChatHistoryVersion,
  } = useAppActions();
  const [state, setState] = useState<ChatStreamState>(() => createChatState());
  const stateRef = useRef(state);
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef(0);
  const rafIdRef = useRef<number | null>(null);

  const publish = useCallback((next: ChatStreamState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  const cancelPendingFrame = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  const scheduleTokenProjection = useCallback(() => {
    if (rafIdRef.current !== null) return;
    rafIdRef.current = requestAnimationFrame(() => {
      rafIdRef.current = null;
      publish(stateRef.current);
    });
  }, [publish]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      cancelPendingFrame();
    },
    [cancelPendingFrame],
  );

  const clearStreamingState = useCallback(() => {
    cancelPendingFrame();
    publish(resetChatTransient(stateRef.current));
  }, [cancelPendingFrame, publish]);

  const clearMessages = useCallback(() => {
    cancelPendingFrame();
    publish(clearCommittedMessages(stateRef.current));
  }, [cancelPendingFrame, publish]);

  const startChat = useCallback(
    async (
      selectionId: number,
      prompt: string,
      threadId?: string | null,
      command?: AIChatCommand,
      options?: ChatStartOptions,
    ) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const runId = runIdRef.current + 1;
      runIdRef.current = runId;

      const labels: ChatStreamLabels = {
        toolError: t("errors.toolError"),
        streamError: t("errors.streamError"),
        incompleteStream: t("errors.streamError"),
        agentInterrupted: t("errors.agentInterrupted"),
        rawAttachmentUrl: chatFilesApi.rawUrl,
      };
      const body = buildStreamBody(selectionId, prompt, threadId, command, options);
      publish(beginChat(stateRef.current, prompt, command, options));

      const isCurrentRun = () =>
        abortRef.current === controller && runIdRef.current === runId;

      const applyEffects = (effects: ChatStreamEffect[]) => {
        for (const effect of effects) {
          switch (effect.type) {
            case "accepted":
              options?.onAccepted?.();
              break;
            case "thread_updated":
              setThreadId(effect.threadId);
              break;
            case "requires_image_input":
              setThreadRequiresImageInput(effect.value);
              break;
            case "agent_status":
              setAgentStatus(effect.value);
              break;
            case "history_changed":
              bumpChatHistoryVersion();
              break;
          }
        }
      };

      const applyResult = (
        result: { state: ChatStreamState; effects: ChatStreamEffect[] },
        eventKind?: string,
      ) => {
        if (!isCurrentRun()) return;
        stateRef.current = result.state;
        applyEffects(result.effects);
        if (eventKind === "token") {
          scheduleTokenProjection();
        } else {
          cancelPendingFrame();
          publish(result.state);
        }
      };

      try {
        for await (const event of aiChatApi.streamChat(body, {
          signal: controller.signal,
        })) {
          if (!isCurrentRun() || controller.signal.aborted) return;
          applyResult(reduceChatEvent(stateRef.current, event, labels), event.event);
        }

        if (!isCurrentRun()) return;
        if (controller.signal.aborted) {
          applyResult(reduceChatAbort(stateRef.current));
          return;
        }
        applyResult(reduceChatEof(stateRef.current, labels));
      } catch (error: unknown) {
        if (!isCurrentRun() || controller.signal.aborted) {
          if (isCurrentRun() && controller.signal.aborted) {
            applyResult(reduceChatAbort(stateRef.current));
          }
          return;
        }
        const message = error instanceof Error ? error.message : String(error);
        applyResult(reduceChatTransportError(stateRef.current, message));
      }
    },
    [
      bumpChatHistoryVersion,
      cancelPendingFrame,
      publish,
      scheduleTokenProjection,
      setAgentStatus,
      setThreadId,
      setThreadRequiresImageInput,
      t,
    ],
  );

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    cancelPendingFrame();
    const result = reduceChatAbort(stateRef.current);
    publish(result.state);
    setAgentStatus("idle");
  }, [cancelPendingFrame, publish, setAgentStatus]);

  const retry = useCallback(
    (selectionId: number, threadId: string) => {
      clearStreamingState();
      void startChat(selectionId, "", threadId, { type: "retry" });
    },
    [clearStreamingState, startChat],
  );

  const answerQuery = useCallback(
    (
      selectionId: number,
      threadId: string,
      choice: QueryChoice,
      note?: string | null,
    ) => {
      clearStreamingState();
      void startChat(selectionId, "", threadId, {
        type: "query",
        choice,
        note: note?.trim() || null,
      });
    },
    [clearStreamingState, startChat],
  );

  const loadHistory = useCallback(
    (historyMessages: AIChatHistoryMessage[]) => {
      cancelPendingFrame();
      const result = mapChatHistory(
        historyMessages,
        stateRef.current,
        chatFilesApi.rawUrl,
      );
      publish(result.state);
    },
    [cancelPendingFrame, publish],
  );

  return {
    messages: state.messages,
    liveMessages: state.liveMessages,
    streamingText: state.streamingText,
    streamingReasoning: state.streamingReasoning,
    toolCalls: state.toolCalls,
    interrupt: state.interrupt as ChatInterrupt | null,
    streamError: state.streamError,
    isStreaming: state.isStreaming,
    startChat,
    stopStream,
    retry,
    answerQuery,
    loadHistory,
    clearMessages,
    resetStreamingState: clearStreamingState,
  };
}
