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
  ConnectionState,
  InputAnswer,
} from "@/app/lib/api/types";
import {
  beginChat,
  parseAttachments,
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

import { ApiError } from "@/app/lib/api/client";
import {
  createIdempotencyKey,
  eventSequence,
  isTerminal,
  isRunStatus,
  isProjectedEvent,
  mergeRuns,
  pendingInput,
} from "@/app/lib/chat/run-state";
const terminal = (run: ChatRun) => isTerminal(run.status);

export function useChatStream() {
  const { t } = useTranslation();
  const tRef = useRef(t);
  useEffect(() => {
    tRef.current = t;
  }, [t]);
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
  const runsRef = useRef<ChatRun[]>([]);
  const updateRuns = useCallback((incoming: ChatRun[]) => {
    runsRef.current = mergeRuns(runsRef.current, incoming);
    setRuns(runsRef.current);
    return runsRef.current;
  }, []);
  const [pendingInputs, setPendingInputs] = useState<PendingInput[]>([]);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("idle");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submitRef = useRef(false);
  const wakeRef = useRef<(() => void) | null>(null);
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

  useEffect(() => {
    threadRef.current = app.currentThreadId;
    const tid = app.currentThreadId;
    const controller = new AbortController();
    const current = () => !controller.signal.aborted;
    const labels = () => ({
      toolError: tRef.current("errors.toolError"),
      streamError: tRef.current("errors.streamError"),
      incompleteStream: tRef.current("errors.streamError"),
      agentInterrupted: tRef.current("errors.agentInterrupted"),
      rawAttachmentUrl: chatFilesApi.rawUrl,
    });
    const delay = (ms: number) =>
      new Promise<void>((resolve) => {
        const done = () => {
          if (wakeRef.current === done) wakeRef.current = null;
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", done);
          resolve();
        };
        const timer = setTimeout(done, ms);
        controller.signal.addEventListener("abort", done, { once: true });
        wakeRef.current = done;
      });
    const apply = (event: ChatStreamEvent) => {
      const result = reduceChatEvent(stateRef.current, event, labels());
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
      setHistoryLoading(true);
      try {
        const history = await aiChatApi.getHistory(tid!);
        if (!current()) return null;
        setThreadRequiresImageInput(history.requires_image_input);
        historyCompacted = history.context_compacted;
        setActionError(null);
        return history.messages;
      } catch (error) {
        if (!current()) return null;
        setActionError(error instanceof Error ? error.message : String(error));
        if (error instanceof ApiError && error.status === 404)
          setThreadId(null);
        return null;
      } finally {
        if (current()) setHistoryLoading(false);
      }
    };
    let fetching: Promise<ChatRun[]> | null = null;
    let subscribed = false;
    const refreshRuns = () => {
      if (fetching) return fetching;
      fetching = aiChatApi
        .listRuns(tid!)
        .then((items) => {
          return current() ? updateRuns(items) : items;
        })
        .finally(() => {
          fetching = null;
        });
      return fetching;
    };
    const monitor = async () => {
      setHistoryLoading(Boolean(tid));
      publish(createChatState());
      runsRef.current = [];
      setRuns([]);
      setPendingInputs([]);
      activeRef.current = null;
      if (!tid) {
        setConnectionState("idle");
        setHistoryLoading(false);
        return;
      }
      let previousRun = "";
      let idleHistoryLoaded = false;
      while (current()) {
        try {
          const list = await refreshRuns();
          if (!current()) return;
          const run = list.find((item) => !terminal(item));
          if (!run) {
            if (!idleHistoryLoaded) {
              const history = await load();
              if (!current()) return;
              if (history === null) {
                await delay(1500);
                continue;
              }
              if (runsRef.current.some((item) => !terminal(item))) continue;
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
          if (history === null) {
            await delay(1500);
            continue;
          }
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
          const reset = () =>
            publish(
              beginChat(base, run.prompt, undefined, {
                draftAttachments: parseAttachments(
                  run.resolved_attachments,
                  chatFilesApi.rawUrl,
                ),
              }),
            );
          reset();
          setPendingInputs(run.pending_inputs);
          subscribed = true;
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
                const id = eventSequence(event.data.event_id);
                if (
                  id === null ||
                  event.data.run_id !== run.run_id ||
                  event.data.thread_id !== tid
                )
                  continue;
                if (
                  event.event === "snapshot" &&
                  (!Array.isArray(event.data.events) ||
                    !event.data.events.every(
                      (item) =>
                        isProjectedEvent(item, run.run_id, tid) &&
                        Number(item.data.event_id) <= id,
                    ) ||
                    !Array.isArray(event.data.pending_inputs) ||
                    !event.data.pending_inputs.every((item) =>
                      pendingInput(item, run.run_id, tid),
                    ))
                ) {
                  setActionError(tRef.current("errors.streamError"));
                  continue;
                }
                // An evicted terminal run has no replay watermark. Keep the current
                // projection until history loads, but stop reconnecting to this run.
                if (
                  event.event === "snapshot" &&
                  isRunStatus(event.data.status) &&
                  isTerminal(event.data.status) &&
                  Array.isArray(event.data.events) &&
                  event.data.events.length === 0
                ) {
                  const known =
                    runsRef.current.find(
                      (item) => item.run_id === run.run_id,
                    ) ?? run;
                  updateRuns([
                    {
                      ...known,
                      status: event.data.status,
                      last_event_id: Math.max(after, id, known.last_event_id),
                    },
                  ]);
                  setPendingInputs([]);
                  ended = true;
                  after = Math.max(after, id);
                  continue;
                }
                if (id < after) continue;
                if (
                  (event.event === "snapshot" ||
                    event.event === "run_status") &&
                  !isRunStatus(event.data.status)
                )
                  continue;
                if (
                  ["tool_start", "tool_end", "tool_error"].includes(
                    event.event,
                  ) &&
                  (typeof event.data.tool_call_id !== "string" ||
                    !event.data.tool_call_id)
                )
                  continue;
                if (
                  event.event === "input_resolved" &&
                  typeof event.data.request_id !== "string"
                )
                  continue;
                if (event.event === "snapshot") {
                  const known =
                    runsRef.current.find(
                      (item) => item.run_id === run.run_id,
                    ) ?? run;
                  updateRuns([
                    {
                      ...known,
                      status: event.data.status as ChatRun["status"],
                      last_event_id: id,
                    },
                  ]);
                  reset();
                  for (const item of (event.data.events ??
                    []) as ChatStreamEvent[]) {
                    if (
                      item &&
                      typeof item.event === "string" &&
                      item.data &&
                      typeof item.data === "object"
                    )
                      apply(item);
                  }
                  setPendingInputs(
                    Array.isArray(event.data.pending_inputs)
                      ? event.data.pending_inputs.flatMap((item) => {
                          const valid = pendingInput(item, run.run_id, tid);
                          return valid ? [valid] : [];
                        })
                      : [],
                  );
                  if (event.data.status === "waiting_input")
                    setAgentStatus("waiting_input");
                  ended =
                    isRunStatus(event.data.status) &&
                    isTerminal(event.data.status);
                } else {
                  if (id <= after) continue;
                  if (event.event === "input_required") {
                    const input = pendingInput(event.data, run.run_id, tid);
                    if (!input) continue;
                    setPendingInputs((items) => [
                      ...items.filter(
                        (item) => item.request_id !== input.request_id,
                      ),
                      input,
                    ]);
                  } else if (event.event === "input_resolved")
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
                    ended =
                      isRunStatus(event.data.status) &&
                      isTerminal(event.data.status);
                    const known =
                      runsRef.current.find(
                        (item) => item.run_id === run.run_id,
                      ) ?? run;
                    updateRuns([
                      {
                        ...known,
                        status: event.data.status as ChatRun["status"],
                        last_event_id: id,
                      },
                    ]);
                  } else apply(event);
                }
                after = Math.max(after, id);
              }
              if (!ended) {
                setConnectionState("reconnecting");
                await delay(1000);
              }
            } catch (error) {
              if (!current()) return;
              if (error instanceof ApiError && error.status === 404) {
                await load();
                if (!current()) return;
                runsRef.current = runsRef.current.filter(
                  (item) => item.run_id !== run.run_id,
                );
                setRuns(runsRef.current);
                ended = true;
                continue;
              }
              setConnectionState("reconnecting");
              if (error instanceof Error) setActionError(error.message);
              await delay(1500);
            }
          }
          subscribed = false;
        } catch (error) {
          if (!current()) return;
          setHistoryLoading(false);
          setConnectionState("reconnecting");
          setActionError(
            error instanceof Error ? error.message : String(error),
          );
          await delay(1500);
        }
      }
    };
    void monitor();
    // Idle monitoring already refreshes; only poll here while SSE owns the loop.
    const poll = setInterval(() => {
      if (tid && subscribed && current()) void refreshRuns().catch(() => {});
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
    updateRuns,
    setThreadId,
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
      try {
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
            : createIdempotencyKey();
        retrySubmission.current = { signature, key };
        const run = await aiChatApi.createRun(
          buildStreamBody(selectionId, prompt, threadId, command, options),
          key,
        );
        retrySubmission.current = null;
        if (threadRef.current === (threadId ?? null)) {
          setThreadId(run.thread_id);
          updateRuns([run]);
          if (!activeRef.current) {
            publish(
              beginChat(stateRef.current, run.prompt, undefined, {
                draftAttachments: parseAttachments(
                  run.resolved_attachments,
                  chatFilesApi.rawUrl,
                ),
              }),
            );
          }
          wakeRef.current?.();
        }
        bumpChatHistoryVersion();
        // Creation is confirmed. A UI callback failure must never turn into a retry.
        try {
          options?.onAccepted?.();
        } catch (error) {
          setActionError(
            error instanceof Error ? error.message : String(error),
          );
        }
      } catch (error) {
        setActionError(error instanceof Error ? error.message : String(error));
      } finally {
        submitRef.current = false;
        setSubmitting(false);
      }
    },
    [setThreadId, bumpChatHistoryVersion, publish, updateRuns],
  );

  const answerInput = useCallback(
    async (input: PendingInput, answer: InputAnswer) => {
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
    historyLoading,
    startChat,
    stopStream,
    answerInput,
    cancelRun,
    cancelQueued,
    loadHistory,
    clearMessages,
  };
}
