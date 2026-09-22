import { describe, expect, it } from "vitest";
import {
  beginChat,
  clearCommittedMessages,
  createChatState,
  mapChatHistory,
  reduceChatEof,
  reduceChatEvent,
  reduceChatTransportError,
} from "./adapter";
import type { ChatStreamLabels } from "./types";

const labels: ChatStreamLabels = {
  toolError: "工具失败",
  streamError: "流式失败",
  incompleteStream: "流式失败",
  agentInterrupted: "Agent 已中断",
};

function event(event: string, data: Record<string, unknown> = {}) {
  return { event, data };
}

describe("chat stream adapter", () => {
  it("ignores invalid IDs and duplicate or conflicting terminal tool events", () => {
    let state = beginChat(createChatState(), "hello", undefined);
    const invalid = reduceChatEvent(
      state,
      event("tool_start", { tool_name: "work", tool_call_id: 12 }),
      labels,
    ).state;
    expect(invalid.toolCalls).toEqual([]);
    state = reduceChatEvent(
      state,
      event("tool_start", { tool_name: "work", tool_call_id: "one" }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("tool_end", {
        tool_name: "work",
        tool_call_id: "one",
        output: "done",
      }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("tool_end", {
        tool_name: "work",
        tool_call_id: "one",
        output: "done",
      }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("tool_error", {
        tool_name: "work",
        tool_call_id: "one",
        detail: "late",
      }),
      labels,
    ).state;
    expect(state.toolCalls).toHaveLength(1);
    expect(state.toolCalls[0].status).toBe("success");
    expect(
      state.liveMessages.filter((message) => message.role === "tool"),
    ).toHaveLength(1);
  });
  it("reduces tokens, tool lifecycle, and final into committed messages", () => {
    let state = beginChat(createChatState(), "请搜索", undefined);
    const result = reduceChatEvent(
      state,
      event("thread", { thread_id: "thread-1" }),
      labels,
    );
    state = result.state;
    expect(result.effects).toEqual([
      { type: "accepted" },
      { type: "thread_updated", threadId: "thread-1" },
    ]);

    state = reduceChatEvent(
      state,
      event("token", { content: "答案" }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("tool_start", { tool_name: "search", input: { q: "OfferPilot" } }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("tool_end", {
        tool_name: "search",
        output: { url: "https://example.com" },
      }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("final", { content: "" }),
      labels,
    ).state;

    expect(state.terminal).toBe(true);
    expect(state.isStreaming).toBe(false);
    expect(
      state.messages.map((message) => [message.role, message.toolName]),
    ).toEqual([
      ["user", undefined],
      ["assistant", undefined],
      ["tool", "search"],
    ]);
    expect(state.messages[1].content).toBe("答案");
    expect(state.messages[2].toolStatus).toBe("success");
  });

  it("pairs concurrent same-name tools by ID without restarting on input events", () => {
    let state = beginChat(createChatState(), "hello", undefined);
    for (const id of ["a", "b"])
      state = reduceChatEvent(
        state,
        event("tool_start", { tool_name: "query", tool_call_id: id }),
        labels,
      ).state;
    state = reduceChatEvent(
      state,
      event("input_required", { request_id: "request-b", tool_call_id: "b" }),
      labels,
    ).state;
    expect(state.terminal).toBe(false);
    for (const id of ["b", "a"])
      state = reduceChatEvent(
        state,
        event("tool_end", { tool_name: "query", tool_call_id: id, output: id }),
        labels,
      ).state;
    expect(
      state.liveMessages
        .filter((item) => item.role === "tool")
        .map((item) => [item.toolCallId, item.toolOutput]),
    ).toEqual([
      ["a", "a"],
      ["b", "b"],
    ]);
  });

  it("turns an incomplete EOF or transport error into an error and removes an unaccepted draft", () => {
    const state = beginChat(createChatState(), "草稿", undefined);
    const eof = reduceChatEof(state, labels);
    expect(eof.state.streamError).toBe("流式失败");
    expect(eof.state.messages).toEqual([]);

    const transport = reduceChatTransportError(state, "网络断开");
    expect(transport.state.streamError).toBe("网络断开");
    expect(transport.state.agentStatus).toBe("error");
  });

  it("tracks compaction lifecycle without adding a chat message", () => {
    const initial = beginChat(createChatState(), "整理上下文", undefined);
    const started = reduceChatEvent(
      initial,
      event("context_compaction", { phase: "started" }),
      labels,
    );

    expect(started.state.contextCompactionStatus).toBe("running");
    expect(started.state.agentStatus).toBe("compacting");
    expect(started.state.messages).toHaveLength(1);
    expect(started.effects).toContainEqual({
      type: "agent_status",
      value: "compacting",
    });

    const completed = reduceChatEvent(
      started.state,
      event("context_compaction", { phase: "completed" }),
      labels,
    );
    expect(completed.state.contextCompactionStatus).toBe("completed");
    expect(completed.state.contextCompacted).toBe(true);
    expect(completed.state.agentStatus).toBe("generating");

    const continued = beginChat(completed.state, "继续", undefined);
    expect(continued.contextCompactionStatus).toBe("completed");
    expect(continued.contextCompacted).toBe(true);
  });

  it("restores completed compaction from history and clears it for a new thread", () => {
    const history = mapChatHistory(
      [{ role: "user", type: "human", content: "历史消息" }],
      createChatState(),
      undefined,
      true,
    );

    expect(history.state.contextCompactionStatus).toBe("completed");
    expect(history.state.contextCompacted).toBe(true);
    expect(history.state.messages).toHaveLength(1);

    const newThread = clearCommittedMessages(history.state);
    expect(newThread.contextCompactionStatus).toBe("idle");
    expect(newThread.contextCompacted).toBe(false);
    expect(newThread.messages).toEqual([]);
  });

  it("moves the header to error state when compaction fails", () => {
    const started = reduceChatEvent(
      beginChat(createChatState(), "整理上下文", undefined),
      event("context_compaction", { phase: "started" }),
      labels,
    ).state;
    const failed = reduceChatEvent(
      started,
      event("context_compaction", { phase: "failed" }),
      labels,
    );

    expect(failed.state.contextCompactionStatus).toBe("failed");
    expect(failed.state.agentStatus).toBe("error");
    expect(failed.effects).toContainEqual({
      type: "agent_status",
      value: "error",
    });
  });
});
