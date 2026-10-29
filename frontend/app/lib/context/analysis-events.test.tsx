// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { analysisApi } from "@/app/lib/api/analysis";
import type { AnalysisEvent } from "@/app/lib/analysis-events/types";
import { AppProvider, useAppContext } from "./app-context";

vi.mock("@/app/lib/api/analysis", () => ({ analysisApi: { events: vi.fn() } }));
afterEach(cleanup);

describe("global analysis subscription", () => {
  it("replaces snapshots and refreshes records on reconnect without changing chat selection", async () => {
    let deliver: ((event: AnalysisEvent) => void) | undefined;
    let stopped = false;
    const events: AnalysisEvent[] = [];
    vi.mocked(analysisApi.events).mockImplementation(async function* (options) {
      const onAbort = () => { stopped = true; deliver?.({ event: "closed", data: {} }); };
      options?.signal?.addEventListener("abort", onAbort, { once: true });
      try {
        while (!options?.signal?.aborted) {
          const event = events.shift() ?? await new Promise<AnalysisEvent>((resolve) => { deliver = resolve; });
          if (!options?.signal?.aborted) yield event;
        }
      } finally {
        options?.signal?.removeEventListener("abort", onAbort);
      }
    });
    const { result, unmount } = renderHook(() => useAppContext(), { wrapper: AppProvider });
    await waitFor(() => expect(deliver).toBeTypeOf("function"));
    const send = async (event: AnalysisEvent) => { await act(async () => { deliver?.(event); }); };
    await send({ event: "snapshot", data: { tasks: [{ resource_type: "resume", resource_id: 1, job_id: "old", event_id: 50, status: "processing", progress: 0.5 }] } });
    const version = result.current.state.analysisEventVersions.resume;
    await send({ event: "progress", data: { resource_type: "resume", resource_id: 1, job_id: "old", event_id: 51, progress: 0.6 } });
    expect(result.current.state.analysisTasks["resume:1"].progress).toBe(0.6);
    expect(result.current.state.analysisEventVersions.resume).toBe(version);
    await send({ event: "snapshot", data: { event_id: 1, tasks: [] } });
    expect(result.current.state.analysisTasks).toEqual({});
    expect(result.current.state.analysisEventVersions.resume).toBe(version + 1);
    expect(analysisApi.events).toHaveBeenCalledTimes(1);
    unmount();
    expect(stopped).toBe(true);
  });
});
