import { apiRequest, apiUrl } from "./client";
import type {
  AIChatHistoryListResponse,
  AIChatHistoryDetailResponse,
  AIChatResponse,
  AIChatStreamRequest,
  SSEEvent,
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
    body: AIChatStreamRequest,
    onEvent: (event: SSEEvent) => void,
    onError?: (error: Error) => void,
    signal?: AbortSignal
  ): Promise<void> => {
    const url = apiUrl("/ai/chat/stream");
    return streamSSE(url, body, onEvent, onError, signal);
  },
};

async function streamSSE(
  url: string,
  body: AIChatStreamRequest,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Error) => void,
  signal?: AbortSignal
): Promise<void> {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
            const event: SSEEvent = {
              event: (currentEventKind || data.type) as SSEEvent["event"],
              type: (currentEventKind || data.type) as SSEEvent["type"],
              data,
            };
            currentEventKind = "";
            onEvent(event);
          } catch {
            // skip malformed
          }
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") return;
    onError?.(err instanceof Error ? err : new Error(String(err)));
  }
}
