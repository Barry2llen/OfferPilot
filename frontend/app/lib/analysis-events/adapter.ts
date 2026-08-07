import type {
  AnalysisEvent,
  AnalysisResourceType,
  AnalysisTaskSnapshot,
} from "./types";
import { analysisTaskKey } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clampProgress(value: unknown, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(0, Math.min(value, 1));
}

function resourceTypeForEvent(
  event: AnalysisEvent,
): AnalysisResourceType | undefined {
  if (event.event === "job_description") return "job_description";
  if (event.event === "resume") return "resume";
  if (event.data.resource_type === "resume") return "resume";
  if (event.data.resource_type === "job_description") return "job_description";
  if (typeof event.data.resume_id === "number") return "resume";
  if (typeof event.data.analysis_id === "number") return "job_description";
  if (isRecord(event.data.resume)) return "resume";
  if (isRecord(event.data.job_description)) return "job_description";
  return undefined;
}

function resourceIdForEvent(
  event: AnalysisEvent,
  resourceType: AnalysisResourceType,
): number | undefined {
  const directId =
    resourceType === "resume" ? event.data.resume_id : event.data.analysis_id;
  if (typeof directId === "number") return directId;

  const recordKey = resourceType === "resume" ? "resume" : "job_description";
  const record = event.data[recordKey];
  if (isRecord(record) && typeof record.id === "number") return record.id;
  return undefined;
}

function statusForRecord(
  event: AnalysisEvent,
  resourceType: AnalysisResourceType,
  fallback: AnalysisTaskSnapshot["status"],
): AnalysisTaskSnapshot["status"] {
  const recordKey = resourceType === "resume" ? "resume" : "job_description";
  const record = event.data[recordKey];
  if (isRecord(record)) {
    const status = resourceType === "resume" ? record.parse_status : record.status;
    if (
      status === "unparsed" ||
      status === "processing" ||
      status === "parsed" ||
      status === "failed"
    ) {
      return status;
    }
  }

  if (event.event === "final") return "parsed";
  if (event.event === "error") return "failed";
  if (event.event === "progress" || event.event === "model_error") {
    return "processing";
  }
  return fallback;
}

export function reduceAnalysisEvent(
  current: AnalysisTaskSnapshot | undefined,
  event: AnalysisEvent,
): AnalysisTaskSnapshot | undefined {
  const resourceType = resourceTypeForEvent(event);
  if (!resourceType) return current;

  const resourceId = resourceIdForEvent(event, resourceType);
  if (resourceId === undefined) return current;

  const fallback: AnalysisTaskSnapshot = current ?? {
    resourceType,
    resourceId,
    status: "processing",
    progress: 0,
    message: null,
    modelError: null,
    error: null,
    lastEvent: event.event,
  };

  const next: AnalysisTaskSnapshot = {
    ...fallback,
    resourceType,
    resourceId,
    status: statusForRecord(event, resourceType, fallback.status),
    lastEvent: event.event,
  };

  if (event.event === "resume" || event.event === "job_description") {
    next.progress = Math.max(next.progress, 0.05);
  } else if (event.event === "progress") {
    next.progress = clampProgress(event.data.progress, next.progress);
    next.message =
      typeof event.data.message === "string" ? event.data.message : next.message;
    next.modelError = null;
  } else if (event.event === "model_error") {
    next.status = "processing";
    next.modelError =
      typeof event.data.detail === "string" ? event.data.detail : next.modelError;
  } else if (event.event === "final") {
    next.progress = 1;
    next.message = null;
    next.modelError = null;
    next.error = null;
  } else if (event.event === "error") {
    next.error =
      typeof event.data.detail === "string" ? event.data.detail : next.error;
    next.modelError = null;
  }

  return next;
}

export function updateAnalysisTaskMap(
  tasks: Record<string, AnalysisTaskSnapshot>,
  event: AnalysisEvent,
): { tasks: Record<string, AnalysisTaskSnapshot>; task?: AnalysisTaskSnapshot } {
  const task = reduceAnalysisEvent(undefined, event);
  if (!task) return { tasks };

  const key = analysisTaskKey(task.resourceType, task.resourceId);
  const nextTask = reduceAnalysisEvent(tasks[key], event);
  if (!nextTask) return { tasks };
  return {
    tasks: { ...tasks, [key]: nextTask },
    task: nextTask,
  };
}
