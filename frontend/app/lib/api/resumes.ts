import { apiRequest, apiUrl, ApiError } from "./client";
import type { ResumeListItem, ResumeDetail } from "./types";

export const resumesApi = {
  list: () => apiRequest<ResumeListItem[]>("/resumes"),

  get: (id: number) => apiRequest<ResumeDetail>(`/resumes/${id}`),

  upload: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<ResumeDetail>("/resumes/files", {
      method: "POST",
      body: formData,
    });
  },

  replace: (id: number, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<ResumeDetail>(`/resumes/${id}/file`, {
      method: "PUT",
      body: formData,
    });
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
