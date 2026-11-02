import type { AnalysisResourceType } from "./types";

export function analysisDetailPath(
  resourceType: AnalysisResourceType,
  resourceId: number,
): string {
  return resourceType === "resume"
    ? `/resumes/${resourceId}`
    : `/job-descriptions/${resourceId}`;
}
