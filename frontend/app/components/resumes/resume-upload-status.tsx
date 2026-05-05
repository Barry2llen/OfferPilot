"use client";

import Link from "next/link";
import { useResumeUpload } from "@/app/lib/context/resume-upload-context";
import Button from "@/app/components/ui/button";

export default function ResumeUploadStatus() {
  const { task, running, dismissTask } = useResumeUpload();

  if (!task) return null;

  const failed = task.status === "error";
  const completed = task.status === "success";
  const title = failed
    ? "简历解析失败"
    : completed
      ? "简历解析完成"
      : "简历解析中";

  return (
    <div className="fixed bottom-4 left-4 z-[90] w-[min(360px,calc(100vw-2rem))] rounded-xl border border-border-default bg-white p-4 shadow-elevated">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 truncate text-xs text-text-muted">{task.fileName}</p>
        </div>
        {!running && (
          <button
            type="button"
            onClick={dismissTask}
            className="rounded-lg p-1 text-text-muted hover:bg-surface-secondary hover:text-text-primary"
            aria-label="关闭简历解析状态"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-secondary">
        <div
          className={`h-full transition-all ${
            failed ? "bg-error-text" : completed ? "bg-success-text" : "bg-info-text"
          }`}
          style={{ width: `${Math.round(task.progress * 100)}%` }}
        />
      </div>

      <p className="mt-2 text-xs text-text-secondary">{task.message}</p>
      {task.modelError && (
        <p className="mt-1 text-xs text-warning-text">{task.modelError}</p>
      )}
      {task.error && (
        <p className="mt-1 text-xs text-error-text">{task.error}</p>
      )}

      {task.resumeId && !running && (
        <div className="mt-3 flex justify-end">
          <Link href={`/resumes/${task.resumeId}`}>
            <Button variant="secondary" size="sm">
              查看简历
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}
