import type { ResumeDetail } from "@/app/lib/api/types";

export type ResumeStreamEventName =
  | "resume"
  | "progress"
  | "model_error"
  | "final"
  | "error"
  | string;

export interface ResumeStreamEvent {
  event: ResumeStreamEventName;
  data: Record<string, unknown>;
}

export type ResumeUploadStatus = "idle" | "running" | "success" | "error";

export interface ResumeUploadTask {
  id: string;
  fileName: string;
  status: ResumeUploadStatus;
  progress: number;
  message: string;
  modelError: string | null;
  error: string | null;
  resumeId: number | null;
  detail: ResumeDetail | null;
}

export interface ResumeStreamLabels {
  initialMessage: string;
  savedMessage: string;
  parsingMessage: string;
  modelRetryMessage: string;
  modelFailedMessage: string;
  completeMessage: string;
  successMessage: string;
  failedMessage: string;
  parseFailedMessage: string;
  uploadFailedMessage: string;
}

export type ResumeStreamEffect =
  | { type: "accepted" }
  | { type: "notify"; level: "success" | "error"; message: string }
  | { type: "completed"; detail?: ResumeDetail };

export interface ResumeStreamState {
  task: ResumeUploadTask;
  accepted: boolean;
  terminal: boolean;
}

export interface ResumeReducerResult {
  state: ResumeStreamState;
  effects: ResumeStreamEffect[];
}
