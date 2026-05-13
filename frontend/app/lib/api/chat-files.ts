import { apiRequest, apiUrl } from "./client";
import type { ChatFileDetail, ChatFileListItem } from "./types";

export const chatFilesApi = {
  list: () => apiRequest<ChatFileListItem[]>("/ai/files"),

  get: (fileId: string) => apiRequest<ChatFileDetail>(`/ai/files/${fileId}`),

  rawUrl: (fileId: string) => apiUrl(`/ai/files/${fileId}/raw`),
};

export const CHAT_TEXT_EXTENSIONS = [
  ".txt",
  ".md",
  ".json",
  ".csv",
  ".yaml",
  ".yml",
  ".xml",
  ".html",
  ".htm",
  ".log",
  ".ini",
  ".conf",
  ".py",
  ".js",
  ".ts",
  ".tsx",
  ".jsx",
  ".java",
  ".go",
  ".rs",
  ".sh",
  ".sql",
];

export const CHAT_BINARY_EXTENSIONS = [
  ".pdf",
  ".docx",
  ".png",
  ".jpg",
  ".jpeg",
];

export const CHAT_ATTACHMENT_EXTENSIONS = [
  ...CHAT_TEXT_EXTENSIONS,
  ...CHAT_BINARY_EXTENSIONS,
];

export const CHAT_ATTACHMENT_ACCEPT = CHAT_ATTACHMENT_EXTENSIONS.join(",");

export function isSupportedChatAttachment(file: File): boolean {
  const ext = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  return CHAT_ATTACHMENT_EXTENSIONS.includes(ext);
}
