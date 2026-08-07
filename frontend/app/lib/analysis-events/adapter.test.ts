import { describe, expect, it } from "vitest";
import { reduceAnalysisEvent, updateAnalysisTaskMap } from "./adapter";

function event(eventName: string, data: Record<string, unknown> = {}) {
  return { event: eventName, data };
}

describe("analysis event adapter", () => {
  it("reduces resume lifecycle and model retry events", () => {
    let task = reduceAnalysisEvent(
      undefined,
      event("resume", {
        resume: { id: 4, parse_status: "processing" },
      }),
    );
    task = reduceAnalysisEvent(
      task,
      event("model_error", {
        resume_id: 4,
        detail: "rate limited",
      }),
    );
    task = reduceAnalysisEvent(
      task,
      event("progress", {
        resume_id: 4,
        progress: 0.7,
        message: "extracting",
      }),
    );

    expect(task).toMatchObject({
      resourceType: "resume",
      resourceId: 4,
      status: "processing",
      progress: 0.7,
      message: "extracting",
      modelError: null,
    });

    const completed = reduceAnalysisEvent(
      task,
      event("final", {
        resume: { id: 4, parse_status: "parsed" },
      }),
    );
    expect(completed).toMatchObject({
      status: "parsed",
      progress: 1,
      error: null,
    });
  });

  it("updates the shared task map for JD failures", () => {
    const result = updateAnalysisTaskMap(
      {},
      event("error", {
        analysis_id: 9,
        detail: "分析失败",
        status: "failed",
      }),
    );

    expect(result.task).toMatchObject({
      resourceType: "job_description",
      resourceId: 9,
      status: "failed",
      error: "分析失败",
    });
    expect(result.tasks["job_description:9"]).toEqual(result.task);
  });
});
