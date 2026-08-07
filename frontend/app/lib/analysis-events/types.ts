export type AnalysisResourceType = "resume" | "job_description";

export type AnalysisEventName =
  | "resume"
  | "job_description"
  | "progress"
  | "model_error"
  | "final"
  | "error"
  | string;

export interface AnalysisEvent {
  event: AnalysisEventName;
  data: Record<string, unknown>;
}

export interface AnalysisTaskSnapshot {
  resourceType: AnalysisResourceType;
  resourceId: number;
  status: "unparsed" | "processing" | "parsed" | "failed";
  progress: number;
  message: string | null;
  modelError: string | null;
  error: string | null;
  lastEvent: AnalysisEventName;
}

export function analysisTaskKey(
  resourceType: AnalysisResourceType,
  resourceId: number,
): string {
  return `${resourceType}:${resourceId}`;
}
