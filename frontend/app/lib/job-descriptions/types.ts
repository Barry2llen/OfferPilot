import type { JobDescriptionAnalysisListItem } from "@/app/lib/api/types";

export type JobDescriptionStreamEventName =
  | "job_description"
  | "progress"
  | "model_error"
  | "final"
  | "error"
  | string;

export interface JobDescriptionStreamEvent {
  event: JobDescriptionStreamEventName;
  data: Record<string, unknown>;
}

export interface JobDescriptionTask {
  status: "idle" | "running" | "success" | "error";
  progress: number;
  message: string;
  modelError: string | null;
  error: string | null;
  analysisId: number | null;
}

export interface JobDescriptionStreamLabels {
  createdMessage: string;
  progressMessage: string;
  modelRetryMessage: string;
  completeMessage: string;
  failedMessage: string;
  submitFailedMessage: string;
}

export type JobDescriptionStreamEffect =
  | { type: "accepted" }
  | { type: "notify"; level: "success" | "error"; message: string }
  | { type: "refetch" }
  | { type: "reset_input" };

export interface JobDescriptionStreamState {
  task: JobDescriptionTask;
  accepted: boolean;
  terminal: boolean;
}

export interface JobDescriptionReducerResult {
  state: JobDescriptionStreamState;
  effects: JobDescriptionStreamEffect[];
}

export type JobDescriptionResultItem = JobDescriptionAnalysisListItem;
