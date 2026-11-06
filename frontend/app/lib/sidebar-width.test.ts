// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import {
  clampSidebarWidth,
  readSidebarWidth,
  SIDEBAR_DEFAULT_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_WIDTH_KEY,
  writeSidebarWidth,
} from "./sidebar-width";

afterEach(() => window.localStorage.clear());

it("clamps widths to the allowed range", () => {
  expect(clampSidebarWidth(10)).toBe(SIDEBAR_MIN_WIDTH);
  expect(clampSidebarWidth(9999)).toBe(SIDEBAR_MAX_WIDTH);
  expect(clampSidebarWidth(250.6)).toBe(251);
  expect(clampSidebarWidth(Number.NaN)).toBe(SIDEBAR_DEFAULT_WIDTH);
});

it("persists the clamped width and falls back to the default", () => {
  expect(readSidebarWidth()).toBe(SIDEBAR_DEFAULT_WIDTH);
  writeSidebarWidth(1000);
  expect(window.localStorage.getItem(SIDEBAR_WIDTH_KEY)).toBe(String(SIDEBAR_MAX_WIDTH));
  expect(readSidebarWidth()).toBe(SIDEBAR_MAX_WIDTH);
  window.localStorage.setItem(SIDEBAR_WIDTH_KEY, "not-a-number");
  expect(readSidebarWidth()).toBe(SIDEBAR_DEFAULT_WIDTH);
});
