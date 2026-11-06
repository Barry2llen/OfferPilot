import { useEffect, useRef, type RefObject } from "react";

/**
 * Closes a popover when the pointer goes down outside `ref` or Escape is pressed.
 * The latest `onDismiss` is always used, so callers can pass inline callbacks.
 */
export function useDismiss(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
  onDismiss: (reason: "outside" | "escape") => void,
) {
  const callback = useRef(onDismiss);
  useEffect(() => {
    callback.current = onDismiss;
  });

  useEffect(() => {
    if (!active) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) callback.current("outside");
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") callback.current("escape");
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [active, ref]);
}

/** Decides whether a popover should open upward based on the room left below its anchor. */
export function shouldOpenUpward(anchor: HTMLElement | null, menuHeight: number): boolean {
  if (!anchor) return false;
  const rect = anchor.getBoundingClientRect();
  const viewport = window.visualViewport?.height ?? window.innerHeight;
  const below = viewport - rect.bottom;
  return below < menuHeight + 16 && rect.top > below;
}
