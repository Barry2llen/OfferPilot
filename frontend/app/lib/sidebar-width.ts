export const SIDEBAR_WIDTH_KEY = "offerpilot.sidebar.width";
export const SIDEBAR_DEFAULT_WIDTH = 232;
export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 360;

export function clampSidebarWidth(width: number): number {
  if (!Number.isFinite(width)) return SIDEBAR_DEFAULT_WIDTH;
  return Math.round(Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width)));
}

export function readSidebarWidth(): number {
  try {
    const stored = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
    return stored === null ? SIDEBAR_DEFAULT_WIDTH : clampSidebarWidth(Number(stored));
  } catch {
    return SIDEBAR_DEFAULT_WIDTH;
  }
}

export function writeSidebarWidth(width: number): void {
  try {
    window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(clampSidebarWidth(width)));
  } catch {
    // Storage can be unavailable (private mode); the width still applies for this session.
  }
}
