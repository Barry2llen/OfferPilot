import { apiUrl } from "./client";
import { openSse, type SseEvent, type SseRequestOptions } from "./sse";

export const analysisApi = {
  events: (options: SseRequestOptions = {}): AsyncIterable<SseEvent> =>
    openSse({
      url: apiUrl("/analysis/events"),
      method: "GET",
      signal: options.signal,
    }),
};
