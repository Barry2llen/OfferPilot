import { describe, expect, it } from "vitest";
import { shouldWarnForSmallerContextWindow } from "./model-context-warning";

function model(context_window_tokens: number) {
  return { context_window_tokens };
}

describe("shouldWarnForSmallerContextWindow", () => {
  it("warns only when an existing thread switches to a smaller window", () => {
    expect(
      shouldWarnForSmallerContextWindow(true, model(128_000), model(32_000)),
    ).toBe(true);
  });

  it("does not warn without an existing thread or when the window is not smaller", () => {
    expect(
      shouldWarnForSmallerContextWindow(false, model(128_000), model(32_000)),
    ).toBe(false);
    expect(
      shouldWarnForSmallerContextWindow(true, model(32_000), model(128_000)),
    ).toBe(false);
    expect(
      shouldWarnForSmallerContextWindow(true, model(32_000), model(32_000)),
    ).toBe(false);
  });
});
