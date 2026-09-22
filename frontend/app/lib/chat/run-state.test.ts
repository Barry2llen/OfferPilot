import { describe, expect, it, vi } from "vitest";
import {
  createIdempotencyKey,
  eventSequence,
  mergeRuns,
  pendingInput,
} from "./run-state";
import type { ChatRun } from "@/app/lib/api/types";

describe("run protocol boundaries", () => {
  it("rejects malformed sequences and input ownership", () => {
    for (const value of [undefined, null, "2", NaN, Infinity, -1, 1.2])
      expect(eventSequence(value)).toBeNull();
    expect(eventSequence(0)).toBe(0);
    const input = {
      type: "query",
      request_id: "q",
      run_id: "r",
      thread_id: "t",
      tool_call_id: "tool",
    };
    expect(pendingInput(input, "r", "t")).toEqual(input);
    expect(pendingInput(input, "other", "t")).toBeNull();
    expect(pendingInput({ ...input, request_id: 123 }, "r", "t")).toBeNull();
  });

  it("never lets stale polls reverse terminal or newer SSE states", () => {
    const current = {
      run_id: "r",
      sequence: 1,
      status: "completed",
      last_event_id: 9,
    } as ChatRun;
    expect(
      mergeRuns(
        [current],
        [{ ...current, status: "running", last_event_id: 8 }],
      ),
    ).toEqual([current]);
    expect(
      mergeRuns(
        [current],
        [{ ...current, status: "running", last_event_id: 0 }],
      ),
    ).toEqual([current]);
  });

  it("generates keys without randomUUID", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: (bytes: Uint8Array) => bytes.fill(42),
    });
    try {
      expect(createIdempotencyKey()).toBe("2a".repeat(16));
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("accepts durable restart termination even though process event IDs reset", () => {
    const current = {
      run_id: "r",
      status: "waiting_input",
      last_event_id: 10,
    } as ChatRun;
    expect(
      mergeRuns(
        [current],
        [{ ...current, status: "interrupted", last_event_id: 0 }],
      )[0].status,
    ).toBe("interrupted");
  });
});
