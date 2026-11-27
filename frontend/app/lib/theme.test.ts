// @vitest-environment jsdom
import { beforeEach, afterEach, expect, it, vi } from "vitest";

beforeEach(() => { vi.resetModules(); localStorage.clear(); document.head.innerHTML = '<meta name="theme-color" content="#ffffff">'; });
afterEach(() => vi.restoreAllMocks());

it("persists explicit theme choices and synchronizes native titlebar metadata", async () => {
  const { setTheme, getTheme } = await import("./theme");
  setTheme("dark");
  expect(getTheme()).toBe("dark");
  expect(localStorage.getItem("offerpilot.theme")).toBe("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(document.querySelector('meta[name="theme-color"]')?.getAttribute("content")).toBe("#121212");
  setTheme("light");
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(document.querySelector('meta[name="theme-color"]')?.getAttribute("content")).toBe("#ffffff");
});

it("follows system appearance only while the system mode is selected", async () => {
  const original = window.matchMedia;
  let dark = true;
  let notify = () => {};
  window.matchMedia = vi.fn().mockImplementation(() => ({ get matches() { return dark; }, addEventListener: (_: string, callback: () => void) => { notify = callback; } }));
  try {
    const { initializeTheme, setTheme } = await import("./theme");
    initializeTheme();
    expect(document.documentElement.dataset.theme).toBe("dark");
    dark = false; notify();
    expect(document.documentElement.dataset.theme).toBe("light");
    setTheme("dark"); notify();
    expect(document.documentElement.dataset.theme).toBe("dark");
    setTheme("system");
    expect(document.documentElement.dataset.theme).toBe("light");
  } finally { window.matchMedia = original; }
});
