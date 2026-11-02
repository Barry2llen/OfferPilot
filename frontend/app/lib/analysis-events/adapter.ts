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
  if (typeof event.data.resource_id === "number" && Number.isSafeInteger(event.data.resource_id) && event.data.resource_id > 0) {
    return event.data.resource_id;
  }
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
  if (event.data.status === "processing" || event.data.status === "parsed" || event.data.status === "failed") return event.data.status;
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

  if (event.data.event_id !== undefined && (typeof event.data.event_id !== "number" || !Number.isSafeInteger(event.data.event_id) || event.data.event_id < 0)) return current;
  const eventId = typeof event.data.event_id === "number" ? event.data.event_id : undefined;
  const jobId = typeof event.data.job_id === "string" ? event.data.job_id : undefined;
  if (current?.eventId !== undefined && eventId !== undefined && eventId <= current.eventId) return current;
  const newJob = jobId !== undefined && current?.jobId !== undefined && jobId !== current.jobId;
  if (current && current.status !== "processing" && !newJob && !["resume", "job_description"].includes(event.event)) return current;

  const fallback: AnalysisTaskSnapshot = (!newJob ? current : undefined) ?? {
    resourceType,
    resourceId,
    jobId,
    eventId,
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
    jobId: jobId ?? fallback.jobId,
    eventId: eventId ?? fallback.eventId,
    status: statusForRecord(event, resourceType, fallback.status),
    lastEvent: event.event,
  };

  if (event.event === "snapshot") {
    next.progress = clampProgress(event.data.progress, 0);
    next.message = typeof event.data.message === "string" ? event.data.message : null;
    next.modelError = typeof event.data.model_error === "string" ? event.data.model_error : null;
    next.error = typeof event.data.error === "string" ? event.data.error : null;
  } else if (event.event === "resume" || event.event === "job_description") {
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
  if (nextTask === tasks[key]) return { tasks };
  return {
    tasks: { ...tasks, [key]: nextTask },
    task: nextTask,
  };
}
