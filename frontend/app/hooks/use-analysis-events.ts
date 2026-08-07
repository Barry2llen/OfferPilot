import { useEffect, useRef } from "react";
import { analysisApi } from "@/app/lib/api/analysis";
import type { AnalysisEvent } from "@/app/lib/analysis-events/types";

function wait(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}

export function useAnalysisEvents(
  onEvent: (event: AnalysisEvent) => void,
): void {
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    const controller = new AbortController();

    const subscribe = async () => {
      while (!controller.signal.aborted) {
        try {
          for await (const event of analysisApi.events({
            signal: controller.signal,
          })) {
            if (controller.signal.aborted) return;
            onEventRef.current(event as AnalysisEvent);
          }
        } catch {
          if (controller.signal.aborted) return;
        }

        if (!controller.signal.aborted) {
          await wait(1000, controller.signal);
        }
      }
    };

    void subscribe();
    return () => controller.abort();
  }, []);
}
