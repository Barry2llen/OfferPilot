import { describe, expect, it } from "vitest";
import {
  beginChat,
  createChatState,
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

    state = reduceChatEvent(state, event("token", { content: "答案" }), labels).state;
    state = reduceChatEvent(
      state,
      event("tool_start", { tool_name: "search", input: { q: "OfferPilot" } }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("tool_end", { tool_name: "search", output: { url: "https://example.com" } }),
      labels,
    ).state;
    state = reduceChatEvent(state, event("final", { content: "" }), labels).state;

    expect(state.terminal).toBe(true);
    expect(state.isStreaming).toBe(false);
    expect(state.messages.map((message) => [message.role, message.toolName])).toEqual([
      ["user", undefined],
      ["assistant", undefined],
      ["tool", "search"],
    ]);
    expect(state.messages[1].content).toBe("答案");
    expect(state.messages[2].toolStatus).toBe("success");
  });

  it("merges query interrupts into the running query tool and supports retry", () => {
    let state = beginChat(createChatState(), "问题", undefined);
    state = reduceChatEvent(
      state,
      event("tool_start", { tool_name: "query", input: { question: "旧问题" } }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("interrupt", {
        id: "interrupt-1",
        type: "query",
        message: "请选择",
        question: "新问题",
        firstChoice: "A",
      }),
      labels,
    ).state;

    expect(state.interrupt).toMatchObject({
      interruptId: "interrupt-1",
      type: "query",
      question: "新问题",
    });
    expect(state.messages.at(-1)).toMatchObject({
      role: "tool",
      toolName: "query",
      toolStatus: "running",
      toolInput: { question: "新问题", firstChoice: "A" },
    });

    const retryState = beginChat(state, "", { type: "retry" });
    expect(retryState.userMessageId).toBeNull();
    expect(retryState.messages).toHaveLength(state.messages.length);
    const errorState = reduceChatEvent(
      retryState,
      event("error", { detail: "重试失败" }),
      labels,
    ).state;
    expect(errorState.streamError).toBe("重试失败");
    expect(errorState.terminal).toBe(true);
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
});
