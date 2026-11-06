import { useEffect, useState, type CSSProperties } from "react";
import { MotionConfig } from "motion/react";
import Sidebar from "./sidebar";
import WindowControls from "./window-controls";
import { HistorySlotContext } from "@/app/lib/context/layout-context";
import { readSidebarWidth, writeSidebarWidth } from "@/app/lib/sidebar-width";
export default function AppShell({ children }: { children: React.ReactNode }) {
  const [slot, setSlot] = useState<HTMLDivElement | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(readSidebarWidth);
  useEffect(() => {
    const viewport = window.visualViewport;
    const update = () => document.documentElement.style.setProperty("--app-height", `${viewport?.height ?? window.innerHeight}px`);
    update();
    viewport?.addEventListener("resize", update);
    return () => viewport?.removeEventListener("resize", update);
  }, []);
  return <MotionConfig reducedMotion="user"><div className="app-shell" style={{ "--sidebar-width": `${sidebarWidth}px` } as CSSProperties}>
    <Sidebar historyRef={setSlot} width={sidebarWidth} onWidthChange={setSidebarWidth} onWidthCommit={writeSidebarWidth} />
    <HistorySlotContext value={slot}><main className="app-main">{children}</main></HistorySlotContext>
    <WindowControls />
  </div></MotionConfig>;
}
