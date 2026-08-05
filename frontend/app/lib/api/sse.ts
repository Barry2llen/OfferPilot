import i18n from "@/app/lib/i18n";
import { ApiError, localeHeaders } from "./client";

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

export type SseFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export interface SseRequestOptions {
  signal?: AbortSignal;
}

export interface OpenSseOptions extends SseRequestOptions {
  url: string;
  method?: "GET" | "POST" | "PUT" | "PATCH";
  body?: unknown;
  fetchImpl?: SseFetch;
  headers?: HeadersInit;
}

interface ParserState {
  eventName: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function createParserState(): ParserState {
  return { eventName: "" };
}

function parseDataLine(state: ParserState, dataText: string): SseEvent | undefined {
  const eventName = state.eventName;
  state.eventName = "";

  try {
    const data: unknown = JSON.parse(dataText);
    if (!isRecord(data)) return undefined;

    const fallbackType = typeof data.type === "string" ? data.type : "message";
    return { event: eventName || fallbackType, data };
  } catch {
    // A malformed event should not terminate a long-running stream.
    return undefined;
  }
}

function consumeLine(state: ParserState, rawLine: string): SseEvent | undefined {
  const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
  const trimmed = line.trim();

  if (!trimmed) {
    state.eventName = "";
    return undefined;
  }
  if (trimmed.startsWith(":")) return undefined;

  if (trimmed.startsWith("event:")) {
    state.eventName = trimmed.slice(6).trim();
    return undefined;
  }

  if (trimmed.startsWith("data:")) {
    const dataLine = trimmed.slice(5).trim();
    if (dataLine) return parseDataLine(state, dataLine);
    state.eventName = "";
  }

  return undefined;
}

function prepareBody(
  body: OpenSseOptions["body"],
): { body: BodyInit | undefined; isJson: boolean } {
  if (body === null || body === undefined) {
    return { body: undefined, isJson: false };
  }

  if (typeof FormData !== "undefined" && body instanceof FormData) {
    return { body, isJson: false };
  }

  if (typeof body === "string") {
    return { body, isJson: true };
  }

  return { body: JSON.stringify(body), isJson: true };
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof Error && error.name === "AbortError") ||
    (typeof error === "object" &&
      error !== null &&
      "name" in error &&
      error.name === "AbortError")
  );
}

async function readErrorDetail(response: Response): Promise<string> {
  let detail = response.statusText;
  try {
    const body: unknown = await response.json();
    if (isRecord(body) && typeof body.detail === "string" && body.detail) {
      detail = body.detail;
    }
  } catch {
    // Keep the HTTP status text when the error body is not JSON.
  }
  return detail || `HTTP ${response.status}`;
}

export async function* openSse(
  options: OpenSseOptions,
): AsyncIterable<SseEvent> {
  const { body, isJson } = prepareBody(options.body);
  const headers = new Headers(localeHeaders());
  if (options.headers) {
    const additionalHeaders = new Headers(options.headers);
    additionalHeaders.forEach((value, key) => headers.set(key, value));
  }
  headers.set("Accept", "text/event-stream");
  if (isJson && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;

  try {
    const fetchImpl = options.fetchImpl ?? fetch;
    const response = await fetchImpl(options.url, {
      method: options.method ?? "POST",
      headers,
      body,
      signal: options.signal,
      cache: "no-store",
    });

    if (!response.ok) {
      throw new ApiError(response.status, await readErrorDetail(response));
    }

    reader = response.body?.getReader();
    if (!reader) throw new Error(i18n.t("errors.noResponseBody"));

    const decoder = new TextDecoder();
    const state = createParserState();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex >= 0) {
        const line = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        const event = consumeLine(state, line);
        if (event) yield event;
        newlineIndex = buffer.indexOf("\n");
      }
    }

    buffer += decoder.decode();
    if (buffer) {
      const event = consumeLine(state, buffer);
      if (event) yield event;
    }

  } catch (error: unknown) {
    if (options.signal?.aborted || isAbortError(error)) return;
    throw error;
  } finally {
    reader?.releaseLock();
  }
}
