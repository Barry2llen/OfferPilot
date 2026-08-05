import { apiRequest, apiUrl } from "./client";
import { openSse, type SseEvent, type SseRequestOptions } from "./sse";
import type {
  JobDescriptionAnalysisDetail,
  JobDescriptionAnalysisListItem,
} from "./types";

export const jobDescriptionsApi = {
  list: () => apiRequest<JobDescriptionAnalysisListItem[]>("/job-descriptions"),

  get: (id: number) =>
    apiRequest<JobDescriptionAnalysisDetail>(`/job-descriptions/${id}`),

  analyze: (
    input: JobDescriptionAnalyzeInput,
    options: SseRequestOptions = {},
  ): AsyncIterable<SseEvent> => {
    const formData = new FormData();
    formData.append("selection_id", String(input.selectionId));
    if (input.jdText.trim()) {
      formData.append("jd_text", input.jdText.trim());
    }
    if (input.sourceUrl.trim()) {
      formData.append("source_url", input.sourceUrl.trim());
    }
    input.files.forEach((file) => formData.append("files[]", file));
    input.fileIds.forEach((fileId) => formData.append("file_ids[]", fileId));
    return openSse({
      url: apiUrl("/job-descriptions"),
      method: "POST",
      body: formData,
      signal: options.signal,
    });
  },

  delete: (id: number) =>
    apiRequest<void>(`/job-descriptions/${id}`, { method: "DELETE" }),
};

export interface JobDescriptionAnalyzeInput {
  selectionId: number;
  jdText: string;
  sourceUrl: string;
  files: File[];
  fileIds: string[];
}

export const JD_IMAGE_ACCEPT = ".png,.jpg,.jpeg";

export function isSupportedJdImage(file: File): boolean {
  const ext = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  return [".png", ".jpg", ".jpeg"].includes(ext);
}
