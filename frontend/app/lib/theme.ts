import { useSyncExternalStore } from "react";
export type ThemeMode = "light" | "dark" | "system";
const key = "offerpilot.theme";
const event = "offerpilot-theme-change";
let sessionMode: ThemeMode | null = null;
export function getTheme(): ThemeMode {
  if (sessionMode) return sessionMode;
  try { const value = localStorage.getItem(key); return value === "light" || value === "dark" ? value : "system"; }
  catch { return "system"; }
}
function applyTheme() {
  const mode = getTheme();
  const dark = mode === "dark" || (mode === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#121212" : "#ffffff");
}
export function setTheme(mode: ThemeMode) {
  sessionMode = mode;
  try { localStorage.setItem(key, mode); } catch { /* retain this session's preference */ }
  applyTheme();
  window.dispatchEvent(new Event(event));
}
export function initializeTheme() {
  applyTheme();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  window.addEventListener("storage", () => { sessionMode = null; applyTheme(); });
}
export function useTheme() {
  const mode = useSyncExternalStore((notify) => {
    window.addEventListener(event, notify);
    window.addEventListener("storage", notify);
    return () => { window.removeEventListener(event, notify); window.removeEventListener("storage", notify); };
  }, getTheme, () => "system" as ThemeMode);
  return [mode, setTheme] as const;
}
