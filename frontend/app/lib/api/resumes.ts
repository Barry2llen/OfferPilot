import { apiRequest, apiUrl, ApiError, localeHeaders } from "./client";
import i18n from "@/app/lib/i18n";
import { openSse, type SseEvent, type SseRequestOptions } from "./sse";
import type { ResumeListItem, ResumeDetail } from "./types";

export const resumesApi = {
  list: () => apiRequest<ResumeListItem[]>("/resumes"),

  get: (id: number) => apiRequest<ResumeDetail>(`/resumes/${id}`),

  upload: (
    file: File,
    selectionId: number,
    options: SseRequestOptions = {},
  ): AsyncIterable<SseEvent> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("selection_id", String(selectionId));
    return openSse({
      url: apiUrl("/resumes/files"),
      method: "POST",
      body: formData,
      signal: options.signal,
    });
  },

  replace: (
    id: number,
    file: File,
    selectionId: number,
    options: SseRequestOptions = {},
  ): AsyncIterable<SseEvent> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("selection_id", String(selectionId));
    return openSse({
      url: apiUrl(`/resumes/${id}/file`),
      method: "PUT",
      body: formData,
      signal: options.signal,
    });
  },

  delete: (id: number) =>
    apiRequest<void>(`/resumes/${id}`, { method: "DELETE" }),

  previewUrl: (id: number) => apiUrl(`/resumes/${id}/file`),

  previewBlob: async (id: number) => {
    const res = await fetch(apiUrl(`/resumes/${id}/file`), {
      cache: "no-store",
      headers: {
        Accept: "application/octet-stream",
        ...localeHeaders(),
      },
    });
    if (!res.ok) throw new ApiError(res.status, i18n.t("errors.loadPreviewFailed"));
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

const WORD_MEDIA_TYPES = ["wordprocessingml", "msword"];
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "gif"]);

/**
 * Short, human-readable format label. MIME types such as
 * `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
 * must never be rendered verbatim because they break compact layouts.
 */
export function resumeMediaLabel(
  type: string | null,
  filename?: string | null,
): string {
  const mediaType = type?.toLowerCase() ?? "";
  const extension = filename?.includes(".")
    ? filename.split(".").pop()?.toLowerCase() ?? ""
    : "";
  if (mediaType.includes("pdf") || extension === "pdf") return "PDF";
  if (
    WORD_MEDIA_TYPES.some((token) => mediaType.includes(token)) ||
    extension === "docx" ||
    extension === "doc"
  ) {
    return extension === "doc" ? "DOC" : "DOCX";
  }
  if (mediaType.startsWith("image/") || IMAGE_EXTENSIONS.has(extension)) {
    return i18n.t("attachments.image");
  }
  if (extension && extension.length <= 5) return extension.toUpperCase();
  const subtype = mediaType.split("/").pop()?.split(/[.+;]/)[0];
  return subtype && subtype.length <= 8
    ? subtype.toUpperCase()
    : i18n.t("common.unknown");
}
