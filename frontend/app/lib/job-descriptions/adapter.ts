import type { JobDescriptionAnalysisListItem } from "@/app/lib/api/types";
import type {
  JobDescriptionReducerResult,
  JobDescriptionStreamEffect,
  JobDescriptionStreamEvent,
  JobDescriptionStreamLabels,
  JobDescriptionStreamState,
  JobDescriptionTask,
} from "./types";

export function createJobDescriptionState(
  task: JobDescriptionTask,
): JobDescriptionStreamState {
  return { task, accepted: false, terminal: false };
}

function extractAnalysis(
  data: Record<string, unknown>,
): JobDescriptionAnalysisListItem | undefined {
  const value = data.job_description;
  if (value && typeof value === "object") {
    return value as JobDescriptionAnalysisListItem;
  }
  return undefined;
}

function clampProgress(value: unknown, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(0, Math.min(value, 1));
}

function emptyTask(): JobDescriptionTask {
  return {
    status: "running",
    progress: 0,
    message: "",
    modelError: null,
    error: null,
    analysisId: null,
  };
}

export function reduceJobDescriptionEvent(
  state: JobDescriptionStreamState,
  event: JobDescriptionStreamEvent,
  labels: JobDescriptionStreamLabels,
): JobDescriptionReducerResult {
  const effects: JobDescriptionStreamEffect[] = state.accepted ? [] : [{ type: "accepted" }];
  let next: JobDescriptionStreamState = { ...state, accepted: true };

  switch (event.event) {
    case "job_description": {
      const detail = extractAnalysis(event.data);
      next = {
        ...next,
        task: {
          ...next.task,
          progress: 0.05,
          message: labels.createdMessage,
          analysisId: detail?.id ?? next.task.analysisId,
        },
      };
      break;
    }
    case "progress": {
      next = {
        ...next,
        task: {
          ...next.task,
          progress: clampProgress(event.data.progress, next.task.progress),
          message:
            typeof event.data.message === "string"
              ? event.data.message
              : labels.progressMessage,
        },
      };
      break;
    }
    case "model_error": {
      next = {
        ...next,
        task: {
          ...next.task,
          modelError:
            typeof event.data.detail === "string"
              ? event.data.detail
              : labels.modelRetryMessage,
        },
      };
      break;
    }
    case "final": {
      const detail = extractAnalysis(event.data);
      next = {
        ...next,
        task: {
          ...next.task,
          status: "success",
          progress: 1,
          message: labels.completeMessage,
          analysisId: detail?.id ?? next.task.analysisId,
        },
        terminal: true,
      };
      effects.push({ type: "notify", level: "success", message: labels.completeMessage });
      effects.push({ type: "refetch" }, { type: "reset_input" });
      break;
    }
    case "error": {
      const detail =
        typeof event.data.detail === "string"
          ? event.data.detail
          : labels.failedMessage;
      next = {
        ...next,
        task: {
          ...next.task,
          status: "error",
          message: labels.failedMessage,
          error: detail,
          analysisId:
            typeof event.data.analysis_id === "number"
              ? event.data.analysis_id
              : next.task.analysisId,
        },
        terminal: true,
      };
      effects.push({ type: "notify", level: "error", message: detail });
      effects.push({ type: "refetch" });
      break;
    }
  }

  return { state: next, effects };
}

export function reduceJobDescriptionTransportError(
  state: JobDescriptionStreamState,
  message: string,
  labels: JobDescriptionStreamLabels,
): JobDescriptionReducerResult {
  return {
    state: {
      ...state,
      task: {
        ...state.task,
        status: "error",
        message: labels.submitFailedMessage,
        error: message,
      },
      terminal: true,
    },
    effects: [{ type: "notify", level: "error", message }],
  };
}

export function reduceJobDescriptionEof(
  state: JobDescriptionStreamState,
  labels: JobDescriptionStreamLabels,
): JobDescriptionReducerResult {
  if (state.terminal) return { state, effects: [] };
  return reduceJobDescriptionTransportError(state, labels.submitFailedMessage, labels);
}

export { emptyTask };
