import { describe, expect, it } from "vitest";
import {
  createJobDescriptionState,
  reduceJobDescriptionEof,
  reduceJobDescriptionEvent,
  reduceJobDescriptionTransportError,
} from "./adapter";
import type { JobDescriptionStreamLabels, JobDescriptionTask } from "./types";

const labels: JobDescriptionStreamLabels = {
  createdMessage: "已创建",
  progressMessage: "分析中",
  modelRetryMessage: "模型重试",
  completeMessage: "完成",
  failedMessage: "分析失败",
  submitFailedMessage: "提交失败",
};

const task: JobDescriptionTask = {
  status: "running",
  progress: 0,
  message: "提交中",
  modelError: null,
  error: null,
  analysisId: null,
};

function event(event: string, data: Record<string, unknown> = {}) {
  return { event, data };
}

describe("job description stream adapter", () => {
  it("handles progress/model_error/final effects", () => {
    let state = createJobDescriptionState(task);
    state = reduceJobDescriptionEvent(
      state,
      event("job_description", { job_description: { id: 3 } }),
      labels,
    ).state;
    state = reduceJobDescriptionEvent(
      state,
      event("progress", { progress: 0.5, message: "抽取中" }),
      labels,
    ).state;
    state = reduceJobDescriptionEvent(
      state,
      event("model_error", { detail: "限流" }),
      labels,
    ).state;
    const final = reduceJobDescriptionEvent(
      state,
      event("final", { job_description: { id: 3 } }),
      labels,
    );

    expect(final.state.task).toMatchObject({ status: "success", progress: 1, analysisId: 3 });
    expect(final.effects).toContainEqual({ type: "refetch" });
    expect(final.effects).toContainEqual({ type: "reset_input" });
  });

  it("treats an error or EOF without final as terminal failure", () => {
    const state = createJobDescriptionState(task);
    const error = reduceJobDescriptionEvent(
      state,
      event("error", { detail: "分析失败" }),
      labels,
    );
    expect(error.state.task).toMatchObject({ status: "error", error: "分析失败" });
    expect(reduceJobDescriptionEof(state, labels).state.task.error).toBe("提交失败");
    expect(
      reduceJobDescriptionTransportError(state, "网络断开", labels).state.task.error,
    ).toBe("网络断开");
  });
});
