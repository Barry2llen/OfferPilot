import { describe, expect, it } from "vitest";
import { ApiError } from "./client";
import { openSse, type SseFetch } from "./sse";

function responseFromChunks(
  chunks: Array<string | Uint8Array>,
  init: ResponseInit = {},
): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(
          typeof chunk === "string" ? new TextEncoder().encode(chunk) : chunk,
        );
      }
      controller.close();
    },
  });
  return new Response(stream, { status: 200, ...init });
}

async function collect(events: AsyncIterable<unknown>): Promise<unknown[]> {
  const result: unknown[] = [];
  for await (const event of events) result.push(event);
  return result;
}

describe("openSse", () => {
  it("parses CRLF, split UTF-8, and an EOF event without a newline", async () => {
    const payload = `event: progress\r\ndata: {"message":"解析中：简历"}\r\n\r\nevent: final\r\ndata: {"type":"final","content":"完成"}`;
    const encoded = new TextEncoder().encode(payload);
    const splitAt = encoded.findIndex((value, index) => value === 0x80 && index > 0);
    const fetchImpl: SseFetch = async () =>
      responseFromChunks([encoded.slice(0, splitAt), encoded.slice(splitAt)]);

    await expect(
      collect(
        openSse({
          url: "/stream",
          fetchImpl,
        }),
      ),
    ).resolves.toEqual([
      { event: "progress", data: { message: "解析中：简历" } },
      { event: "final", data: { type: "final", content: "完成" } },
    ]);
  });

  it("uses data.type as fallback and passes unknown events through", async () => {
    const fetchImpl: SseFetch = async () =>
      responseFromChunks([
        "data: {\"type\":\"custom\",\"value\":1}\n\n",
        "event: future\ndata: {\"value\":2}\n\n",
      ]);

    await expect(collect(openSse({ url: "/stream", fetchImpl }))).resolves.toEqual([
      { event: "custom", data: { type: "custom", value: 1 } },
      { event: "future", data: { value: 2 } },
    ]);
  });

  it("skips malformed JSON and continues parsing", async () => {
    const fetchImpl: SseFetch = async () =>
      responseFromChunks([
        "event: broken\ndata: {not-json}\n\n",
        "event: final\ndata: {\"ok\":true}\n\n",
      ]);

    await expect(collect(openSse({ url: "/stream", fetchImpl }))).resolves.toEqual([
      { event: "final", data: { ok: true } },
    ]);
  });

  it("serializes JSON bodies and leaves FormData untouched", async () => {
    const calls: RequestInit[] = [];
    const fetchImpl: SseFetch = async (_url, init) => {
      calls.push(init ?? {});
      return responseFromChunks([]);
    };

    await collect(
      openSse({
        url: "/json",
        body: { selection_id: 1 },
        fetchImpl,
      }),
    );
    const form = new FormData();
    form.append("file", "resume");
    await collect(openSse({ url: "/form", body: form, fetchImpl }));

    expect(calls[0].body).toBe('{"selection_id":1}');
    expect(new Headers(calls[0].headers).get("Content-Type")).toBe(
      "application/json",
    );
    expect(calls[1].body).toBe(form);
    expect(new Headers(calls[1].headers).get("Content-Type")).toBeNull();
    expect(new Headers(calls[0].headers).get("Accept")).toBe("text/event-stream");
  });

  it("throws ApiError for HTTP failures and errors when the body is absent", async () => {
    const failedFetch: SseFetch = async () =>
      new Response(JSON.stringify({ detail: "请求失败" }), {
        status: 422,
        statusText: "Unprocessable Entity",
      });
    await expect(collect(openSse({ url: "/failed", fetchImpl: failedFetch }))).rejects.toMatchObject(
      { name: "ApiError", status: 422, detail: "请求失败" } satisfies Partial<ApiError>,
    );

    const noBodyFetch: SseFetch = async () => new Response(null, { status: 200 });
    await expect(collect(openSse({ url: "/empty", fetchImpl: noBodyFetch }))).rejects.toThrow();
  });

  it("treats abort as normal completion", async () => {
    const controller = new AbortController();
    const fetchImpl: SseFetch = async (_url, init) => {
      await new Promise<never>((_, reject) => {
        const abort = () => reject(new DOMException("Aborted", "AbortError"));
        if (init?.signal?.aborted) abort();
        else init?.signal?.addEventListener("abort", abort, { once: true });
      });
      throw new Error("unreachable");
    };
    controller.abort();

    await expect(
      collect(openSse({ url: "/aborted", signal: controller.signal, fetchImpl })),
    ).resolves.toEqual([]);
  });
});
