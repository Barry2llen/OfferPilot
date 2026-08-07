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

  it("tracks analysis tool progress, retry errors, and structured completion", () => {
    let state = beginChat(createChatState(), "分析简历", undefined);
    state = reduceChatEvent(
      state,
      event("tool_start", {
        tool_name: "analyze_resume",
        tool_call_id: "analysis-call",
        input: { resume_id: 3 },
      }),
      labels,
    ).state;
    state = reduceChatEvent(
      state,
      event("tool_progress", {
        tool_name: "analyze_resume",
        tool_call_id: "analysis-call",
        resource_type: "resume",
        resource_id: 3,
        event: "progress",
        progress: 0.5,
        message: "解析中",
      }),
      labels,
    ).state;

    expect(state.toolCalls[0]).toMatchObject({
      name: "analyze_resume",
      toolCallId: "analysis-call",
      status: "running",
      analysis: {
        resourceType: "resume",
        resourceId: 3,
        status: "processing",
        progress: 0.5,
        message: "解析中",
      },
    });

    state = reduceChatEvent(
      state,
      event("tool_end", {
        tool_name: "analyze_resume",
        tool_call_id: "analysis-call",
        output: {
          resource_type: "resume",
          resource_id: 3,
          status: "parsed",
          result: { raw_text: "完成" },
        },
      }),
      labels,
    ).state;

    expect(state.toolCalls[0]).toMatchObject({
      status: "success",
      analysis: { status: "parsed", progress: 1 },
    });

    let failed = beginChat(createChatState(), "分析岗位", undefined);
    failed = reduceChatEvent(
      failed,
      event("tool_start", { tool_name: "analyze_job_description" }),
      labels,
    ).state;
    failed = reduceChatEvent(
      failed,
      event("tool_error", {
        tool_name: "analyze_job_description",
        detail: "模型失败",
        output: {
          resource_type: "job_description",
          resource_id: 8,
          status: "failed",
          error: "模型失败",
        },
      }),
      labels,
    ).state;

    expect(failed.toolCalls[0]).toMatchObject({
      status: "error",
      error: "模型失败",
      analysis: {
        resourceType: "job_description",
        resourceId: 8,
        status: "failed",
      },
    });
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
    expect(failed.effects).toContainEqual({ type: "agent_status", value: "error" });
  });
});
