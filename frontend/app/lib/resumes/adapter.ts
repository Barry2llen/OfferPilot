import type { ResumeDetail } from "@/app/lib/api/types";
import type {
  ResumeReducerResult,
  ResumeStreamEffect,
  ResumeStreamEvent,
  ResumeStreamLabels,
  ResumeStreamState,
  ResumeUploadTask,
} from "./types";

export function createResumeUploadState(
  task: ResumeUploadTask,
): ResumeStreamState {
  return { task, accepted: false, terminal: false };
}

function extractResume(data: Record<string, unknown>): ResumeDetail | undefined {
  const resume = data.resume;
  if (resume && typeof resume === "object") return resume as ResumeDetail;
  return undefined;
}

function clampProgress(value: unknown, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(0, Math.min(value, 1));
}

export function reduceResumeEvent(
  state: ResumeStreamState,
  event: ResumeStreamEvent,
  labels: ResumeStreamLabels,
): ResumeReducerResult {
  const effects: ResumeStreamEffect[] = state.accepted ? [] : [{ type: "accepted" }];
  let next: ResumeStreamState = { ...state, accepted: true };

  switch (event.event) {
    case "resume": {
      const detail = extractResume(event.data);
      next = {
        ...next,
        task: {
          ...next.task,
          progress: 0.05,
          message: labels.savedMessage,
          resumeId: detail?.id ?? next.task.resumeId,
          detail: detail ?? next.task.detail,
        },
      };
      break;
    }
    case "progress": {
      next = {
        ...next,
        task: {
          ...next.task,
          progress: clampProgress(event.data.progress, 0),
          message:
            typeof event.data.message === "string"
              ? event.data.message
              : labels.parsingMessage,
        },
      };
      break;
    }
    case "model_error": {
      const attempt = event.data.attempt;
      const maxAttempts = event.data.max_attempts;
      const detail =
        typeof event.data.detail === "string"
          ? event.data.detail
          : labels.modelRetryMessage;
      next = {
        ...next,
        task: {
          ...next.task,
          modelError: `${labels.modelFailedMessage}${
            attempt && maxAttempts ? ` (${attempt}/${maxAttempts})` : ""
          }: ${detail}`,
        },
      };
      break;
    }
    case "final": {
      const detail = extractResume(event.data);
      const resolvedDetail = detail ?? next.task.detail ?? undefined;
      next = {
        ...next,
        task: {
          ...next.task,
          status: "success",
          progress: 1,
          message: labels.completeMessage,
          detail: resolvedDetail ?? null,
          resumeId: detail?.id ?? next.task.resumeId,
        },
        terminal: true,
      };
      effects.push({ type: "notify", level: "success", message: labels.successMessage });
      effects.push({ type: "completed", detail });
      break;
    }
    case "error": {
      const detail =
        typeof event.data.detail === "string"
          ? event.data.detail
          : labels.parseFailedMessage;
      next = {
        ...next,
        task: {
          ...next.task,
          status: "error",
          message: labels.failedMessage,
          error: detail,
          resumeId:
            typeof event.data.resume_id === "number"
              ? event.data.resume_id
              : next.task.resumeId,
        },
        terminal: true,
      };
      effects.push({ type: "notify", level: "error", message: detail });
      effects.push({ type: "completed" });
      break;
    }
  }

  return { state: next, effects };
}

export function reduceResumeTransportError(
  state: ResumeStreamState,
  message: string,
  labels: ResumeStreamLabels,
): ResumeReducerResult {
  const next = {
    ...state,
    task: {
      ...state.task,
      status: "error" as const,
      message: labels.uploadFailedMessage,
      error: message,
    },
    terminal: true,
  };
  return {
    state: next,
    effects: [
      { type: "notify", level: "error", message },
      { type: "completed" },
    ],
  };
}

export function reduceResumeEof(
  state: ResumeStreamState,
  labels: ResumeStreamLabels,
): ResumeReducerResult {
  if (state.terminal) return { state, effects: [] };
  return reduceResumeTransportError(state, labels.uploadFailedMessage, labels);
}
