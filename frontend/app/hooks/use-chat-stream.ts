import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { aiChatApi } from "@/app/lib/api/ai";
import { chatFilesApi } from "@/app/lib/api/chat-files";
import { useAppActions, useAppContext } from "@/app/lib/context/app-context";
import type {
  AIChatCommand,
  AIChatHistoryMessage,
  ChatRun,
  PendingInput,
} from "@/app/lib/api/types";
import {
  beginChat,
  buildStreamBody,
  createChatState,
  mapChatHistory,
  reduceChatEvent,
} from "@/app/lib/chat/adapter";
import type {
  ChatStartOptions,
  ChatStreamEvent,
  ChatStreamState,
} from "@/app/lib/chat/types";

const terminal = (run: ChatRun) =>
  ["completed", "failed", "cancelled", "interrupted"].includes(run.status);

export function useChatStream() {
  const { t } = useTranslation();
  const { state: app } = useAppContext();
  const {
    setThreadId,
    setThreadRequiresImageInput,
    setAgentStatus,
    bumpChatHistoryVersion,
  } = useAppActions();
  const [state, setState] = useState(createChatState);
  const stateRef = useRef(state);
  const [runs, setRuns] = useState<ChatRun[]>([]);
  const [pendingInputs, setPendingInputs] = useState<PendingInput[]>([]);
  const [connectionState, setConnectionState] = useState<
    "connected" | "reconnecting" | "idle"
  >("idle");
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submitRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const rafRef = useRef<number | null>(null);
  const activeRef = useRef<ChatRun | null>(null);
  const threadRef = useRef(app.currentThreadId);
  const retrySubmission = useRef<{ signature: string; key: string } | null>(
    null,
  );

  const publish = useCallback((next: ChatStreamState, token = false) => {
    stateRef.current = next;
    if (rafRef.current !== null) {
      if (token) return;
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (token) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        setState(stateRef.current);
      });
    } else setState(next);
  }, []);

  const disconnect = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  useEffect(() => {
    threadRef.current = app.currentThreadId;
    const tid = app.currentThreadId;
    const controller = new AbortController();
    abortRef.current = controller;
    const current = () => !controller.signal.aborted;
    const labels = {
      toolError: t("errors.toolError"),
      streamError: t("errors.streamError"),
      incompleteStream: t("errors.streamError"),
      agentInterrupted: t("errors.agentInterrupted"),
      rawAttachmentUrl: chatFilesApi.rawUrl,
    };
    const delay = (ms: number) =>
      new Promise<void>((resolve) => {
        const done = () => {
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", done);
          resolve();
        };
        const timer = setTimeout(done, ms);
        controller.signal.addEventListener("abort", done, { once: true });
      });
    const apply = (event: ChatStreamEvent) => {
      const result = reduceChatEvent(stateRef.current, event, labels);
      publish(
        result.state,
        event.event === "token" || event.event === "reasoning",
      );
      for (const effect of result.effects) {
        if (effect.type === "requires_image_input")
          setThreadRequiresImageInput(effect.value);
        if (effect.type === "agent_status") setAgentStatus(effect.value);
      }
    };
    let historyCompacted = false;
    const load = async () => {
      try {
        const history = await aiChatApi.getHistory(tid!);
        if (!current()) return [];
        setThreadRequiresImageInput(history.requires_image_input);
        historyCompacted = history.context_compacted;
        return history.messages;
      } catch {
        return [];
      }
    };
    const monitor = async () => {
      publish(createChatState());
      setRuns([]);
      setPendingInputs([]);
      activeRef.current = null;
      if (!tid) {
        setConnectionState("idle");
        return;
      }
      let previousRun = "";
      let idleHistoryLoaded = false;
      while (current()) {
        try {
          const list = await aiChatApi.listRuns(tid);
          if (!current()) return;
          setRuns(list);
          const run = list.find((item) => !terminal(item));
          if (!run) {
            if (!idleHistoryLoaded) {
              const history = await load();
              if (!current()) return;
              publish(
                mapChatHistory(
                  history,
                  createChatState(),
                  chatFilesApi.rawUrl,
                  historyCompacted,
                ).state,
              );
              idleHistoryLoaded = true;
            }
            setPendingInputs([]);
            activeRef.current = null;
            setConnectionState("idle");
            setAgentStatus("idle");
            if (previousRun) {
              bumpChatHistoryVersion();
              previousRun = "";
            }
            await delay(1500);
            continue;
          }
          idleHistoryLoaded = false;
          activeRef.current = run;
          previousRun = run.run_id;
          const history = await load();
          if (!current()) return;
          const index = history.findIndex(
            (message) => message.id === run.message_id,
          );
          const baseHistory = index >= 0 ? history.slice(0, index) : history;
          const base = mapChatHistory(
            baseHistory,
            createChatState(),
            chatFilesApi.rawUrl,
            historyCompacted,
          ).state;
          const reset = () => publish(beginChat(base, run.prompt, undefined));
          reset();
          setPendingInputs(run.pending_inputs);
          let after = 0;
          let ended = false;
          while (current() && !ended) {
            try {
              setConnectionState(after ? "reconnecting" : "connected");
              for await (const event of aiChatApi.runEvents(
                run.run_id,
                after,
                controller.signal,
                () => {
                  if (current()) {
                    setConnectionState("connected");
                    setActionError(null);
                  }
                },
              )) {
                if (!current()) return;
                setConnectionState("connected");
                setActionError(null);
                const id = Number(event.data.event_id ?? 0);
                if (event.event === "snapshot") {
                  reset();
                  for (const item of (event.data.events ??
                    []) as ChatStreamEvent[])
                    apply(item);
                  setPendingInputs(
                    (event.data.pending_inputs ?? []) as PendingInput[],
                  );
                  if (event.data.status === "waiting_input")
                    setAgentStatus("waiting_input");
                  ended = [
                    "completed",
                    "failed",
                    "cancelled",
                    "interrupted",
                  ].includes(String(event.data.status));
                } else {
                  if (id <= after) continue;
                  if (event.event === "input_required")
                    setPendingInputs((items) => [
                      ...items.filter(
                        (item) => item.request_id !== event.data.request_id,
                      ),
                      event.data as unknown as PendingInput,
                    ]);
                  else if (event.event === "input_resolved")
                    setPendingInputs((items) =>
                      items.filter(
                        (item) => item.request_id !== event.data.request_id,
                      ),
                    );
                  else if (event.event === "run_status") {
                    if (event.data.status === "waiting_input")
                      setAgentStatus("waiting_input");
                    else if (event.data.status === "running")
                      setAgentStatus("generating");
                    ended = [
                      "completed",
                      "failed",
                      "cancelled",
                      "interrupted",
                    ].includes(String(event.data.status));
                    setRuns((items) =>
                      items.map((item) =>
                        item.run_id === run.run_id
                          ? {
                              ...item,
                              status: event.data.status as ChatRun["status"],
                            }
                          : item,
                      ),
                    );
                  } else apply(event);
                }
                after = id;
              }
              if (!ended) {
                setConnectionState("reconnecting");
                await delay(1000);
              }
            } catch (error) {
              if (!current()) return;
              setConnectionState("reconnecting");
              if (error instanceof Error) setActionError(error.message);
              await delay(1500);
            }
          }
        } catch (error) {
          if (!current()) return;
          setConnectionState("reconnecting");
          setActionError(
            error instanceof Error ? error.message : String(error),
          );
          await delay(1500);
        }
      }
    };
    void monitor();
    // Queue additions must become visible while a long-lived SSE stream is open.
    const poll = setInterval(() => {
      if (tid)
        void aiChatApi
          .listRuns(tid)
          .then((items) => {
            if (current()) setRuns(items);
          })
          .catch(() => {});
    }, 2000);
    return () => {
      controller.abort();
      clearInterval(poll);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [
    app.currentThreadId,
    publish,
    t,
    setAgentStatus,
    setThreadRequiresImageInput,
    bumpChatHistoryVersion,
  ]);

  const startChat = useCallback(
    async (
      selectionId: number,
      prompt: string,
      threadId?: string | null,
      command?: AIChatCommand,
      options?: ChatStartOptions,
    ) => {
      if (submitRef.current) return;
      submitRef.current = true;
      setSubmitting(true);
      setActionError(null);
      const signature = JSON.stringify([
        selectionId,
        prompt,
        threadId,
        options?.fileIds,
        options?.localFiles?.map((file) => [
          file.name,
          file.size,
          file.lastModified,
        ]),
      ]);
      const key =
        retrySubmission.current?.signature === signature
          ? retrySubmission.current.key
          : crypto.randomUUID();
      retrySubmission.current = { signature, key };
      try {
        const run = await aiChatApi.createRun(
          buildStreamBody(selectionId, prompt, threadId, command, options),
          key,
        );
        retrySubmission.current = null;
        options?.onAccepted?.();
        if (threadRef.current === (threadId ?? null)) {
          setThreadId(run.thread_id);
          setRuns(await aiChatApi.listRuns(run.thread_id));
        }
        bumpChatHistoryVersion();
      } catch (error) {
        setActionError(error instanceof Error ? error.message : String(error));
      } finally {
        submitRef.current = false;
        setSubmitting(false);
      }
    },
    [setThreadId, bumpChatHistoryVersion],
  );

  const answerInput = useCallback(
    async (input: PendingInput, answer: Record<string, unknown>) => {
      setActionError(null);
      try {
        await aiChatApi.answerInput(input.run_id, input.request_id, answer);
        setPendingInputs((items) =>
          items.filter((item) => item.request_id !== input.request_id),
        );
      } catch (error) {
        setActionError(error instanceof Error ? error.message : String(error));
        throw error;
      }
    },
    [],
  );
  const cancelRun = useCallback(async (runId: string) => {
    try {
      await aiChatApi.cancelRun(runId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }, []);
  const stopStream = useCallback(() => {
    if (activeRef.current) void cancelRun(activeRef.current.run_id);
  }, [cancelRun]);
  const cancelQueued = useCallback(async () => {
    for (const run of runs.filter((item) => item.status === "queued"))
      await cancelRun(run.run_id);
  }, [runs, cancelRun]);
  const clearMessages = useCallback(
    () => publish(createChatState()),
    [publish],
  );
  const loadHistory = useCallback(
    (messages: AIChatHistoryMessage[], compacted = false) => {
      publish(
        mapChatHistory(
          messages,
          createChatState(),
          chatFilesApi.rawUrl,
          compacted,
        ).state,
      );
    },
    [publish],
  );
  return {
    ...state,
    streamError: actionError ?? state.streamError,
    isStreaming: runs.some((run) => !terminal(run)),
    runs,
    pendingInputs,
    connectionState,
    submitting,
    startChat,
    stopStream,
    disconnect,
    answerInput,
    cancelRun,
    cancelQueued,
    loadHistory,
    clearMessages,
    resetStreamingState: clearMessages,
  };
}
