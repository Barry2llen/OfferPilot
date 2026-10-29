import { useEffect, useRef } from "react";
import { analysisApi } from "@/app/lib/api/analysis";
import type { AnalysisEvent } from "@/app/lib/analysis-events/types";
import { useTranslation } from "react-i18next";

function wait(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timer = window.setTimeout(finish, milliseconds);
    signal.addEventListener("abort", finish, { once: true });
    if (signal.aborted) finish();
  });
}

export function useAnalysisEvents(
  onEvent: (event: AnalysisEvent) => void,
): void {
  const onEventRef = useRef(onEvent);
  const { i18n } = useTranslation();
  const locale = i18n.resolvedLanguage;

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
  }, [locale]);
}
