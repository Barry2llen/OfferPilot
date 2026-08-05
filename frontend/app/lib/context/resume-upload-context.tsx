import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { resumesApi } from "@/app/lib/api/resumes";
import { useToast } from "@/app/components/ui/toast";
import {
  createResumeUploadState,
  reduceResumeEof,
  reduceResumeEvent,
  reduceResumeTransportError,
} from "@/app/lib/resumes/adapter";
import type {
  ResumeStreamEffect,
  ResumeStreamLabels,
  ResumeUploadTask,
} from "@/app/lib/resumes/types";
import type { ResumeDetail } from "@/app/lib/api/types";

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
  const { t } = useTranslation();
  const abortRef = useRef<AbortController | null>(null);

  const running = task?.status === "running";

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

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
        addToast(t("upload.busy"), "warning");
        return;
      }

      const taskId = getTaskId();
      runningRef.current = true;
      const initialTask: ResumeUploadTask = {
        id: taskId,
        fileName: file.name,
        status: "running",
        progress: 0,
        message: t("upload.uploading", { name: file.name }),
        modelError: null,
        error: null,
        resumeId: null,
        detail: null,
      };
      setTask(initialTask);

      const labels: ResumeStreamLabels = {
        initialMessage: t("upload.uploading", { name: file.name }),
        savedMessage: t("upload.saved"),
        parsingMessage: t("upload.parsing"),
        modelRetryMessage: t("upload.modelRetry"),
        modelFailedMessage: t("upload.modelFailed"),
        completeMessage: t("upload.complete"),
        successMessage: t("upload.success"),
        failedMessage: t("upload.failed"),
        parseFailedMessage: t("upload.parseFailed"),
        uploadFailedMessage: t("upload.uploadFailed"),
      };
      let streamState = createResumeUploadState(initialTask);
      const controller = new AbortController();
      abortRef.current = controller;

      const applyResult = (result: {
        state: typeof streamState;
        effects: ResumeStreamEffect[];
      }) => {
        streamState = result.state;
        updateTask(taskId, () => streamState.task);
        for (const effect of result.effects) {
          switch (effect.type) {
            case "notify":
              addToast(effect.message, effect.level);
              break;
            case "completed":
              runningRef.current = false;
              onCompleted?.(effect.detail);
              break;
            case "accepted":
              break;
          }
        }
      };

      try {
        for await (const event of uploadFile(file, selectionId, {
          signal: controller.signal,
        })) {
          if (controller.signal.aborted) break;
          applyResult(
            reduceResumeEvent(streamState, event, labels),
          );
        }
        if (!controller.signal.aborted) {
          applyResult(reduceResumeEof(streamState, labels));
        }
      } catch (error: unknown) {
        if (!controller.signal.aborted) {
          applyResult(
            reduceResumeTransportError(
              streamState,
              error instanceof Error ? error.message : String(error),
              labels,
            ),
          );
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        runningRef.current = false;
      }
    },
    [addToast, t, updateTask]
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
