import { useTranslation } from "react-i18next";
import type { AnalysisTaskSnapshot } from "@/app/lib/analysis-events/types";

interface AnalysisTaskStatusProps {
  task?: AnalysisTaskSnapshot;
}

export default function AnalysisTaskStatus({ task }: AnalysisTaskStatusProps) {
  const { t } = useTranslation();

  if (!task) return null;

  const progress = Math.round(Math.max(0, Math.min(task.progress, 1)) * 100);
  const failed = task.status === "failed";
  const message = failed
    ? task.error || task.modelError || t("chat.analysisFailed")
    : task.message ||
      (task.status === "parsed"
        ? t("chat.analysisComplete")
        : t("chat.analysisWorking"));

  return (
    <div className="mt-3 rounded-xl border border-border-light bg-surface-secondary/70 px-3 py-2.5">
      <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
        <span className={failed ? "text-error-text" : "text-text-secondary"}>
          {message}
        </span>
        <span className="shrink-0 font-mono text-text-muted">{progress}%</span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-white"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
      >
        <div
          className={`h-full rounded-full transition-[width] ${
            failed ? "bg-error-text" : "bg-primary-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>
      {task.modelError && (
        <p className="mt-1.5 text-xs text-warning-text">{task.modelError}</p>
      )}
      {task.error && task.error !== task.modelError && (
        <p className="mt-1.5 text-xs text-error-text">{task.error}</p>
      )}
    </div>
  );
}
