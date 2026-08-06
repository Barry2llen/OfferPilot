import { describe, expect, it } from "vitest";
import {
  createResumeUploadState,
  reduceResumeEof,
  reduceResumeEvent,
  reduceResumeTransportError,
} from "./adapter";
import type { ResumeStreamLabels, ResumeUploadTask } from "./types";

const labels: ResumeStreamLabels = {
  initialMessage: "上传中",
  savedMessage: "已保存",
  parsingMessage: "解析中",
  modelRetryMessage: "模型重试",
  modelFailedMessage: "模型失败",
  completeMessage: "完成",
  successMessage: "简历完成",
  failedMessage: "失败",
  parseFailedMessage: "简历解析失败",
  uploadFailedMessage: "上传失败",
};

const task: ResumeUploadTask = {
  id: "upload-1",
  fileName: "resume.pdf",
  status: "running",
  progress: 0,
  message: "上传中",
  modelError: null,
  error: null,
  resumeId: null,
  detail: null,
};

function event(event: string, data: Record<string, unknown> = {}) {
  return { event, data };
}

describe("resume stream adapter", () => {
  it("handles progress, model retry, final, and effect completion", () => {
    let state = createResumeUploadState(task);
    state = reduceResumeEvent(state, event("resume", { resume: { id: 7 } }), labels).state;
    state = reduceResumeEvent(
      state,
      event("progress", { progress: 0.7, message: "提取中" }),
      labels,
    ).state;
    const retry = reduceResumeEvent(
      state,
      event("model_error", { attempt: 1, max_attempts: 3, detail: "限流" }),
      labels,
    );
    state = retry.state;
    expect(state.task.modelError).toContain("(1/3)");

    const final = reduceResumeEvent(
      state,
      event("final", { resume: { id: 7, raw_text: "简历" } }),
      labels,
    );
    expect(final.state.task.status).toBe("success");
    expect(final.state.task.progress).toBe(1);
    expect(final.effects).toContainEqual({ type: "completed", detail: { id: 7, raw_text: "简历" } });
  });

  it("converts error and incomplete EOF into terminal error state", () => {
    const state = createResumeUploadState(task);
    const error = reduceResumeEvent(state, event("error", { detail: "解析失败" }), labels);
    expect(error.state.task).toMatchObject({ status: "error", error: "解析失败" });
    expect(reduceResumeEof(state, labels).state.task.error).toBe("上传失败");
    expect(reduceResumeTransportError(state, "HTTP 500", labels).state.task.status).toBe(
      "error",
    );
  });
});
