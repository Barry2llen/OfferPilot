import { useEffect, useState } from "react";
import { MotionConfig } from "motion/react";
import Sidebar from "./sidebar";
import { HistorySlotContext } from "@/app/lib/context/layout-context";
export default function AppShell({ children }: { children: React.ReactNode }) {
  const [slot, setSlot] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    const viewport = window.visualViewport;
    const update = () => document.documentElement.style.setProperty("--app-height", `${viewport?.height ?? window.innerHeight}px`);
    update();
    viewport?.addEventListener("resize", update);
    return () => viewport?.removeEventListener("resize", update);
  }, []);
  return <MotionConfig reducedMotion="user"><div className="app-shell">
    <Sidebar historyRef={setSlot} />
    <HistorySlotContext value={slot}><main className="app-main">{children}</main></HistorySlotContext>
  </div></MotionConfig>;
}
