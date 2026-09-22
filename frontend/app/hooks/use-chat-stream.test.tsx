// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AppProvider,
  useAppActions,
  useAppContext,
} from "@/app/lib/context/app-context";
import { useChatStream } from "./use-chat-stream";
import { aiChatApi } from "@/app/lib/api/ai";
import { ApiError } from "@/app/lib/api/client";
import i18n from "@/app/lib/i18n";
import type { ChatRun } from "@/app/lib/api/types";

vi.mock("@/app/lib/api/ai", () => ({
  aiChatApi: {
    listRuns: vi.fn(),
    getHistory: vi.fn(),
    runEvents: vi.fn(),
    createRun: vi.fn(),
    answerInput: vi.fn(),
    cancelRun: vi.fn(),
  },
}));

const run: ChatRun = {
  run_id: "r",
  thread_id: "t",
  status: "waiting_input",
  sequence: 1,
  prompt: "hello",
  selection_id: 1,
  message_id: "human",
  detail: null,
  pending_inputs: [],
  last_event_id: 1,
  requires_image_input: false,
  resolved_attachments: [
    {
      file_id: "file",
      original_filename: "resume.pdf",
      media_type: "application/pdf",
      injection_mode: "text",
    },
  ],
};
const history = {
  thread_id: "t",
  title: "test",
  message_count: 1,
  last_message_preview: "old",
  updated_at: "",
  attachment_count: 0,
  requires_image_input: false,
  context_compacted: false,
  messages: [{ id: "old", role: "user", type: "human", content: "old" }],
};

function mount() {
  return renderHook(
    () => ({
      chat: useChatStream(),
      actions: useAppActions(),
      app: useAppContext().state,
    }),
    { wrapper: AppProvider },
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  localStorage.setItem(
    "offerpilot.chat.selection",
    JSON.stringify({ thread: "t", model: 1 }),
  );
  vi.mocked(aiChatApi.listRuns).mockResolvedValue([run]);
  vi.mocked(aiChatApi.getHistory).mockResolvedValue(history);
  vi.mocked(aiChatApi.runEvents).mockImplementation(
    async function* (_rid, _after, signal, onOpen) {
      onOpen?.();
      yield {
        event: "snapshot",
        data: {
          run_id: "r",
          thread_id: "t",
          event_id: 1,
          status: "waiting_input",
          events: [],
          pending_inputs: [],
        },
      };
      await new Promise<void>((resolve) =>
        signal.addEventListener("abort", () => resolve(), { once: true }),
      );
    },
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("run subscription lifecycle", () => {
  it("does not advance the cursor or erase messages for malformed snapshots and input events", async () => {
    vi.mocked(aiChatApi.runEvents).mockImplementation(
      async function* (_rid, _after, signal) {
        const ids = { run_id: "r", thread_id: "t" };
        yield {
          event: "token",
          data: { ...ids, event_id: 2, content: "before" },
        };
        yield {
          event: "snapshot",
          data: {
            ...ids,
            event_id: 100,
            status: "running",
            events: {},
            pending_inputs: [],
          },
        };
        yield {
          event: "input_required",
          data: { ...ids, event_id: 101, type: "query" },
        };
        yield {
          event: "token",
          data: { ...ids, event_id: 3, content: "after" },
        };
        await new Promise<void>((resolve) =>
          signal.addEventListener("abort", () => resolve(), { once: true }),
        );
      },
    );
    const { result } = mount();
    await waitFor(() =>
      expect(result.current.chat.streamingText).toBe("beforeafter"),
    );
    expect(result.current.chat.pendingInputs).toEqual([]);
  });
  it("finishes reconnecting when a terminal run was evicted and has watermark zero", async () => {
    let connections = 0;
    vi.mocked(aiChatApi.runEvents).mockImplementation(async function* () {
      connections += 1;
      if (connections === 1) {
        yield {
          event: "snapshot",
          data: {
            run_id: "r",
            thread_id: "t",
            event_id: 5,
            status: "running",
            events: [],
            pending_inputs: [],
          },
        };
      } else {
        vi.mocked(aiChatApi.listRuns).mockResolvedValue([
          { ...run, status: "completed", last_event_id: 0 },
        ]);
        yield {
          event: "snapshot",
          data: {
            run_id: "r",
            thread_id: "t",
            event_id: 0,
            status: "completed",
            pending_inputs: [],
            events: [],
          },
        };
      }
    });
    const { result } = mount();
    await waitFor(
      () => expect(result.current.chat.connectionState).toBe("idle"),
      { timeout: 3000 },
    );
    await waitFor(
      () => expect(result.current.chat.runs[0]?.status).toBe("completed"),
      { timeout: 3000 },
    );
    expect(connections).toBe(2);
    expect(result.current.chat.messages[0]?.content).toBe("old");
  });
  it("keeps the subscription on same-thread selection and language change, restores attachments", async () => {
    const { result } = mount();
    await waitFor(() => expect(aiChatApi.runEvents).toHaveBeenCalledTimes(1));
    await act(async () => {
      result.current.actions.setThreadId("t");
      await i18n.changeLanguage("en-US");
    });
    expect(aiChatApi.runEvents).toHaveBeenCalledTimes(1);
    expect(
      result.current.chat.messages.find(
        (message) => message.content === "hello",
      )?.attachments?.[0].fileId,
    ).toBe("file");
  });

  it("retries failed history reads instead of committing empty history", async () => {
    vi.mocked(aiChatApi.listRuns).mockResolvedValue([]);
    vi.mocked(aiChatApi.getHistory).mockRejectedValueOnce(
      new ApiError(500, "temporary"),
    );
    const { result } = mount();
    await waitFor(() =>
      expect(result.current.chat.streamError).toBe("temporary"),
    );
    await waitFor(
      () => expect(result.current.chat.messages[0]?.content).toBe("old"),
      { timeout: 3000 },
    );
    expect(aiChatApi.getHistory).toHaveBeenCalledTimes(2);
    expect(result.current.chat.historyLoading).toBe(false);
  });

  it("clears only a confirmed missing conversation", async () => {
    vi.mocked(aiChatApi.listRuns).mockResolvedValue([]);
    vi.mocked(aiChatApi.getHistory).mockRejectedValue(
      new ApiError(404, "missing"),
    );
    const { result } = mount();
    await waitFor(() => expect(result.current.app.currentThreadId).toBeNull());
    expect(result.current.chat.connectionState).toBe("idle");
  });

  it("confirms creation independently of a failed list refresh", async () => {
    const { result } = mount();
    await waitFor(() => expect(aiChatApi.runEvents).toHaveBeenCalledTimes(1));
    vi.mocked(aiChatApi.listRuns).mockRejectedValue(
      new Error("refresh unavailable"),
    );
    vi.mocked(aiChatApi.createRun).mockResolvedValue({
      ...run,
      run_id: "queued",
      status: "queued",
      sequence: 2,
    });
    const accepted = vi.fn();
    await act(async () => {
      await result.current.chat.startChat(1, "hello", "t", undefined, {
        onAccepted: accepted,
      });
    });
    expect(accepted).toHaveBeenCalledTimes(1);
    expect(
      result.current.chat.runs.some((item) => item.run_id === "queued"),
    ).toBe(true);
    expect(result.current.chat.streamError).toBeNull();
    expect(result.current.chat.submitting).toBe(false);
  });

  it("reuses the key when creation response is lost", async () => {
    const { result } = mount();
    await waitFor(() => expect(aiChatApi.runEvents).toHaveBeenCalledTimes(1));
    vi.mocked(aiChatApi.createRun)
      .mockRejectedValueOnce(new Error("lost response"))
      .mockResolvedValue(run);
    await act(async () => {
      await result.current.chat.startChat(1, "hello", "t");
    });
    await act(async () => {
      await result.current.chat.startChat(1, "hello", "t");
    });
    const calls = vi.mocked(aiChatApi.createRun).mock.calls;
    expect(calls[0][1]).toBe(calls[1][1]);
  });

  it("survives storage write failures", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    const { result } = mount();
    await act(async () => {
      result.current.actions.setModelSelection(3);
    });
    expect(result.current.app.currentModelSelection).toBe(3);
  });
});

it("does not reconnect or schedule a delay after the old subscription is aborted", async () => {
  const { result } = mount();
  await waitFor(() => expect(aiChatApi.runEvents).toHaveBeenCalledTimes(1));
  const timers = vi.spyOn(globalThis, "setTimeout");
  await act(async () => {
    result.current.actions.setThreadId(null);
  });
  expect(result.current.chat.connectionState).toBe("idle");
  expect(timers.mock.calls.some((call) => call[1] === 1000)).toBe(false);
  expect(aiChatApi.runEvents).toHaveBeenCalledTimes(1);
  expect(aiChatApi.cancelRun).not.toHaveBeenCalled();
});

it("reuses an unconfirmed command key only for the same command", async () => {
  const { result } = mount();
  await waitFor(() => expect(aiChatApi.runEvents).toHaveBeenCalledTimes(1));
  vi.mocked(aiChatApi.createRun).mockRejectedValue(new Error("lost response"));
  for (const prompt of ["first", "first", "second"]) {
    await act(async () => {
      await result.current.chat.startChat(1, "", "t", {
        type: "prompt",
        prompt,
      });
    });
  }
  const calls = vi.mocked(aiChatApi.createRun).mock.calls;
  expect(calls[0][1]).toBe(calls[1][1]);
  expect(calls[2][1]).not.toBe(calls[1][1]);
});
