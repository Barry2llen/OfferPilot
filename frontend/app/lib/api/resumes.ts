import { apiRequest, apiUrl, ApiError } from "./client";
import type { ResumeListItem, ResumeDetail, ResumeStreamEvent } from "./types";

export const resumesApi = {
  list: () => apiRequest<ResumeListItem[]>("/resumes"),

  get: (id: number) => apiRequest<ResumeDetail>(`/resumes/${id}`),

  upload: (
    file: File,
    selectionId: number,
    onEvent: (event: ResumeStreamEvent) => void,
    onError?: (error: Error) => void,
    signal?: AbortSignal
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("selection_id", String(selectionId));
    return streamSSEForm(
      apiUrl("/resumes/files"),
      "POST",
      formData,
      onEvent,
      onError,
      signal
    );
  },

  replace: (
    id: number,
    file: File,
    selectionId: number,
    onEvent: (event: ResumeStreamEvent) => void,
    onError?: (error: Error) => void,
    signal?: AbortSignal
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("selection_id", String(selectionId));
    return streamSSEForm(
      apiUrl(`/resumes/${id}/file`),
      "PUT",
      formData,
      onEvent,
      onError,
      signal
    );
  },

  delete: (id: number) =>
    apiRequest<void>(`/resumes/${id}`, { method: "DELETE" }),

  previewUrl: (id: number) => apiUrl(`/resumes/${id}/file`),

  previewBlob: async (id: number) => {
    const res = await fetch(apiUrl(`/resumes/${id}/file`));
    if (!res.ok) throw new ApiError(res.status, "Failed to load preview");
    return res.blob();
  },
};

export const SUPPORTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpg",
  "image/jpeg",
];

export const SUPPORTED_EXTENSIONS = ".pdf,.docx,.png,.jpg,.jpeg";

export function isSupportedFile(file: File): boolean {
  const ext = "." + file.name.split(".").pop()?.toLowerCase();
  return (
    SUPPORTED_EXTENSIONS.split(",").includes(ext) ||
    SUPPORTED_TYPES.includes(file.type)
  );
}

async function streamSSEForm(
  url: string,
  method: "POST" | "PUT",
  body: FormData,
  onEvent: (event: ResumeStreamEvent) => void,
  onError?: (error: Error) => void,
  signal?: AbortSignal
): Promise<void> {
  try {
    const response = await fetch(url, {
      method,
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
              event: eventKind as ResumeStreamEvent["event"],
              type: eventKind as ResumeStreamEvent["type"],
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
