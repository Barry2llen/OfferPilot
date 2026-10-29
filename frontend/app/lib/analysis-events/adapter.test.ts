import { describe, expect, it } from "vitest";
import { reduceAnalysisEvent, updateAnalysisTaskMap } from "./adapter";

function event(eventName: string, data: Record<string, unknown> = {}) {
  return { event: eventName, data };
}

describe("analysis event adapter", () => {
  it("rejects old generations, duplicate events and progress after a terminal", () => {
    const identity = { resource_type: "resume", resource_id: 4 };
    const processing = reduceAnalysisEvent(undefined, event("resume", { ...identity, job_id: "new", event_id: 10 }));
    expect(reduceAnalysisEvent(processing, event("error", { ...identity, job_id: "old", event_id: 9 }))).toBe(processing);
    expect(reduceAnalysisEvent(processing, event("progress", { ...identity, job_id: "new", event_id: 10 }))).toBe(processing);
    const parsed = reduceAnalysisEvent(processing, event("final", { ...identity, job_id: "new", event_id: 11 }));
    expect(parsed?.status).toBe("parsed");
    expect(reduceAnalysisEvent(parsed, event("progress", { ...identity, job_id: "new", event_id: 12 }))).toBe(parsed);
    const next = reduceAnalysisEvent(parsed, event("resume", { ...identity, job_id: "next", event_id: 13 }));
    expect(next).toMatchObject({ status: "processing", progress: 0.05, error: null, jobId: "next" });
  });

  it("restores current progress and retry information from a snapshot", () => {
    const task = reduceAnalysisEvent(undefined, event("snapshot", {
      resource_type: "job_description", resource_id: 2, job_id: "job", event_id: 8,
      status: "processing", progress: 0.6, message: "Extracting", model_error: "Retrying",
    }));
    expect(task).toMatchObject({ resourceId: 2, progress: 0.6, modelError: "Retrying", status: "processing" });
  });
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
