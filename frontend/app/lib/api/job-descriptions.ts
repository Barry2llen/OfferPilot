import { apiRequest, apiUrl } from "./client";
import type {
  JobDescriptionAnalysisDetail,
  JobDescriptionAnalysisListItem,
  JobDescriptionStreamEvent,
} from "./types";

export const jobDescriptionsApi = {
  list: () => apiRequest<JobDescriptionAnalysisListItem[]>("/job-descriptions"),

  get: (id: number) =>
    apiRequest<JobDescriptionAnalysisDetail>(`/job-descriptions/${id}`),

  analyze: (
    input: JobDescriptionAnalyzeInput,
    onEvent: (event: JobDescriptionStreamEvent) => void,
    onError?: (error: Error) => void,
    signal?: AbortSignal
  ) => {
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
    return streamSSEForm(
      apiUrl("/job-descriptions"),
      formData,
      onEvent,
      onError,
      signal
    );
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

async function streamSSEForm(
  url: string,
  body: FormData,
  onEvent: (event: JobDescriptionStreamEvent) => void,
  onError?: (error: Error) => void,
  signal?: AbortSignal
): Promise<void> {
  try {
    const response = await fetch(url, {
      method: "POST",
      body,
      signal,
    });

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const err = await response.json();
        detail = err.detail || detail;
      } catch {
        // use statusText
      }
      throw new Error(detail);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";
    let currentEventKind = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        if (trimmed.startsWith("event:")) {
          currentEventKind = trimmed.slice(6).trim();
        } else if (trimmed.startsWith("data:")) {
          const jsonStr = trimmed.slice(5).trim();
          if (!jsonStr) continue;
          try {
            const data = JSON.parse(jsonStr);
            const eventKind = currentEventKind || data.type;
            onEvent({
              event: eventKind as JobDescriptionStreamEvent["event"],
              type: eventKind as JobDescriptionStreamEvent["type"],
              data,
            });
            currentEventKind = "";
          } catch {
            // skip malformed chunks
          }
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") return;
    onError?.(err instanceof Error ? err : new Error(String(err)));
  }
}
