"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { resumesApi } from "@/app/lib/api/resumes";
import { useToast } from "@/app/components/ui/toast";
import type { ResumeDetail, ResumeStreamEvent } from "@/app/lib/api/types";

type ResumeUploadStatus = "idle" | "running" | "success" | "error";

interface ResumeUploadTask {
  id: string;
  fileName: string;
  status: ResumeUploadStatus;
  progress: number;
  message: string;
  modelError: string | null;
  error: string | null;
  resumeId: number | null;
  detail: ResumeDetail | null;
}

interface StartResumeUploadOptions {
  file: File;
  selectionId: number;
  uploadFile?: typeof resumesApi.upload;
  onCompleted?: (detail?: ResumeDetail) => void;
}

interface ResumeUploadContextValue {
  task: ResumeUploadTask | null;
  running: boolean;
  startUpload: (options: StartResumeUploadOptions) => Promise<void>;
  dismissTask: () => void;
}

const ResumeUploadContext = createContext<ResumeUploadContextValue | null>(null);

function extractResume(data: Record<string, unknown>): ResumeDetail | undefined {
  const resume = data.resume;
  if (resume && typeof resume === "object") {
    return resume as ResumeDetail;
  }
  return undefined;
}

function getTaskId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function ResumeUploadProvider({ children }: { children: ReactNode }) {
  const [task, setTask] = useState<ResumeUploadTask | null>(null);
  const runningRef = useRef(false);
  const { addToast } = useToast();

  const running = task?.status === "running";

  const updateTask = useCallback(
    (taskId: string, updater: (current: ResumeUploadTask) => ResumeUploadTask) => {
      setTask((current) => {
        if (!current || current.id !== taskId) return current;
        return updater(current);
      });
    },
    []
  );

  const startUpload = useCallback(
    async ({
      file,
      selectionId,
      uploadFile = resumesApi.upload,
      onCompleted,
    }: StartResumeUploadOptions) => {
      if (runningRef.current) {
        addToast("已有简历正在上传或解析，请等待完成", "warning");
        return;
      }

      const taskId = getTaskId();
      runningRef.current = true;
      setTask({
        id: taskId,
        fileName: file.name,
        status: "running",
        progress: 0,
        message: `正在上传「${file.name}」`,
        modelError: null,
        error: null,
        resumeId: null,
        detail: null,
      });

      const handleStreamEvent = (event: ResumeStreamEvent) => {
        const kind = event.event || event.type;

        switch (kind) {
          case "resume": {
            const detail = extractResume(event.data);
            updateTask(taskId, (current) => ({
              ...current,
              progress: 0.05,
              message: "文件已保存，开始解析",
              resumeId: detail?.id ?? current.resumeId,
              detail: detail ?? current.detail,
            }));
            break;
          }
          case "progress": {
            const progress =
              typeof event.data.progress === "number"
                ? event.data.progress
                : 0;
            updateTask(taskId, (current) => ({
              ...current,
              progress: Math.max(0, Math.min(progress, 1)),
              message:
                typeof event.data.message === "string"
                  ? event.data.message
                  : "正在解析简历",
            }));
            break;
          }
          case "model_error": {
            const attempt = event.data.attempt;
            const maxAttempts = event.data.max_attempts;
            const detail =
              typeof event.data.detail === "string"
                ? event.data.detail
                : "模型调用失败，正在重试";
            updateTask(taskId, (current) => ({
              ...current,
              modelError: `模型调用失败${
                attempt && maxAttempts ? ` (${attempt}/${maxAttempts})` : ""
              }: ${detail}`,
            }));
            break;
          }
          case "final": {
            const detail = extractResume(event.data);
            updateTask(taskId, (current) => ({
              ...current,
              status: "success",
              progress: 1,
              message: "解析完成",
              detail: detail ?? current.detail,
              resumeId: detail?.id ?? current.resumeId,
            }));
            runningRef.current = false;
            addToast("简历已上传并解析完成", "success");
            onCompleted?.(detail);
            break;
          }
          case "error": {
            const detail =
              typeof event.data.detail === "string"
                ? event.data.detail
                : "简历解析失败";
            updateTask(taskId, (current) => ({
              ...current,
              status: "error",
              message: "解析失败",
              error: detail,
              resumeId:
                typeof event.data.resume_id === "number"
                  ? event.data.resume_id
                  : current.resumeId,
            }));
            runningRef.current = false;
            addToast(detail, "error");
            onCompleted?.();
            break;
          }
        }
      };

      try {
        await uploadFile(file, selectionId, handleStreamEvent, (error) => {
          updateTask(taskId, (current) => ({
            ...current,
            status: "error",
            message: "上传或解析失败",
            error: error.message,
          }));
          runningRef.current = false;
          addToast(error.message, "error");
          onCompleted?.();
        });
      } finally {
        runningRef.current = false;
      }
    },
    [addToast, updateTask]
  );

  const dismissTask = useCallback(() => {
    if (runningRef.current) return;
    setTask(null);
  }, []);

  const value = useMemo(
    () => ({
      task,
      running,
      startUpload,
      dismissTask,
    }),
    [dismissTask, running, startUpload, task]
  );

  return (
    <ResumeUploadContext.Provider value={value}>
      {children}
    </ResumeUploadContext.Provider>
  );
}

export function useResumeUpload() {
  const ctx = useContext(ResumeUploadContext);
  if (!ctx) {
    throw new Error("useResumeUpload must be used within ResumeUploadProvider");
  }
  return ctx;
}
