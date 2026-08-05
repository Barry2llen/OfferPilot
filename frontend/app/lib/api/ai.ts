import { apiRequest, apiUrl } from "./client";
import { openSse, type SseEvent, type SseRequestOptions } from "./sse";
import type {
  AIChatHistoryListResponse,
  AIChatHistoryDetailResponse,
  AIChatResponse,
  AIChatStreamRequest,
} from "./types";

export const aiChatApi = {
  listChats: (limit = 20, offset = 0) =>
    apiRequest<AIChatHistoryListResponse>(
      `/ai/chats?limit=${limit}&offset=${offset}`
    ),

  getHistory: (threadId: string) =>
    apiRequest<AIChatHistoryDetailResponse>(
      `/ai/chats/${threadId}/history`
    ),

  deleteChat: (threadId: string) =>
    apiRequest<void>(`/ai/chats/${threadId}`, { method: "DELETE" }),

  chat: (selectionId: number, prompt: string, threadId?: string) =>
    apiRequest<AIChatResponse>("/ai/chat", {
      method: "POST",
      body: JSON.stringify({
        selection_id: selectionId,
        prompt,
        thread_id: threadId ?? null,
      }),
    }),

  streamChat: (
    body: AIChatStreamRequest | FormData,
    options: SseRequestOptions = {},
  ): AsyncIterable<SseEvent> => {
    return openSse({
      url: apiUrl("/ai/chat/stream"),
      method: "POST",
      body,
      signal: options.signal,
    });
  },
};
