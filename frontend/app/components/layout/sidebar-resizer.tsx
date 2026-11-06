import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  clampSidebarWidth,
  SIDEBAR_DEFAULT_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
} from "@/app/lib/sidebar-width";

const KEYBOARD_STEP = 16;

/** Vertical window splitter on the sidebar's right edge; only shown with the full desktop sidebar. */
export default function SidebarResizer({ width, onChange, onCommit }: {
  width: number;
  onChange: (width: number) => void;
  onCommit: (width: number) => void;
}) {
  const { t } = useTranslation();
  const origin = useRef<{ x: number; width: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("is-resizing-sidebar", dragging);
    return () => document.documentElement.classList.remove("is-resizing-sidebar");
  }, [dragging]);

  const widthAt = (event: PointerEvent<HTMLDivElement>) =>
    origin.current ? clampSidebarWidth(origin.current.width + event.clientX - origin.current.x) : width;

  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (!origin.current) return;
    const next = widthAt(event);
    origin.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    onChange(next);
    onCommit(next);
  };

  const apply = (next: number) => {
    const clamped = clampSidebarWidth(next);
    onChange(clamped);
    onCommit(clamped);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = {
      ArrowLeft: width - KEYBOARD_STEP,
      ArrowRight: width + KEYBOARD_STEP,
      Home: SIDEBAR_MIN_WIDTH,
      End: SIDEBAR_MAX_WIDTH,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    apply(next);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={t("nav.resizeSidebar")}
      aria-valuemin={SIDEBAR_MIN_WIDTH}
      aria-valuemax={SIDEBAR_MAX_WIDTH}
      aria-valuenow={width}
      title={t("nav.resizeSidebarHint")}
      tabIndex={0}
      data-dragging={dragging}
      className="sidebar-resizer app-region-no-drag"
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        try {
          event.currentTarget.setPointerCapture(event.pointerId);
        } catch {
          // Capture can fail for synthetic or already-released pointers; dragging still works while over the handle.
        }
        origin.current = { x: event.clientX, width };
        setDragging(true);
      }}
      onPointerMove={(event) => {
        if (origin.current) onChange(widthAt(event));
      }}
      onPointerUp={finish}
      onPointerCancel={finish}
      onDoubleClick={() => apply(SIDEBAR_DEFAULT_WIDTH)}
      onKeyDown={handleKeyDown}
    />
  );
}
