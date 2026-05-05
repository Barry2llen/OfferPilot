"use client";

import Link from "next/link";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  resumesApi,
  isSupportedFile,
  SUPPORTED_EXTENSIONS,
} from "@/app/lib/api/resumes";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAppActions, useAppContext } from "@/app/lib/context/app-context";
import { useToast } from "@/app/components/ui/toast";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import ModelSelectionPicker from "@/app/components/chat/model-selection-picker";
import type {
  ModelSelectionResponse,
  ResumeDetail,
  ResumeStreamEvent,
} from "@/app/lib/api/types";

interface ResumeUploaderProps {
  onUploaded: (detail?: ResumeDetail) => void;
  uploadFile?: typeof resumesApi.upload;
}

function extractResume(data: Record<string, unknown>): ResumeDetail | undefined {
  const resume = data.resume;
  if (resume && typeof resume === "object") {
    return resume as ResumeDetail;
  }
  return undefined;
}

export default function ResumeUploader({
  onUploaded,
  uploadFile = resumesApi.upload,
}: ResumeUploaderProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { addToast } = useToast();
  const { state } = useAppContext();
  const { setModelSelection } = useAppActions();

  useEffect(() => {
    let mounted = true;
    modelSelectionsApi
      .list()
      .then((data) => {
        if (!mounted) return;
        setModels(data);
        if (state.currentModelSelection === null && data.length > 0) {
          setModelSelection(data[0].id);
        }
      })
      .catch(() => {
        if (mounted) setModels([]);
      })
      .finally(() => {
        if (mounted) setModelsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [setModelSelection, state.currentModelSelection]);

  const resetProgress = () => {
    setProgress(0);
    setProgressMessage("");
    setParseError(null);
    setModelError(null);
  };

  const handleStreamEvent = useCallback(
    (event: ResumeStreamEvent) => {
      const kind = event.event || event.type;

      switch (kind) {
        case "resume": {
          setProgress(0.05);
          setProgressMessage("文件已保存，开始解析");
          break;
        }
        case "progress": {
          const nextProgress =
            typeof event.data.progress === "number" ? event.data.progress : 0;
          setProgress(Math.max(0, Math.min(nextProgress, 1)));
          setProgressMessage(
            typeof event.data.message === "string"
              ? event.data.message
              : "正在解析简历"
          );
          break;
        }
        case "model_error": {
          const attempt = event.data.attempt;
          const maxAttempts = event.data.max_attempts;
          const detail =
            typeof event.data.detail === "string"
              ? event.data.detail
              : "模型调用失败，正在重试";
          setModelError(
            `模型调用失败${attempt && maxAttempts ? ` (${attempt}/${maxAttempts})` : ""}: ${detail}`
          );
          break;
        }
        case "final": {
          const detail = extractResume(event.data);
          setProgress(1);
          setProgressMessage("解析完成");
          setFile(null);
          addToast("简历已上传并解析完成", "success");
          onUploaded(detail);
          break;
        }
        case "error": {
          const detail =
            typeof event.data.detail === "string"
              ? event.data.detail
              : "简历解析失败";
          setParseError(detail);
          setProgressMessage("解析失败");
          addToast(detail, "error");
          onUploaded();
          break;
        }
      }
    },
    [addToast, onUploaded]
  );

  const handleFile = useCallback(
    async (f: File) => {
      if (!isSupportedFile(f)) {
        addToast("不支持的文件格式，支持 PDF、DOCX、PNG、JPG、JPEG", "error");
        return;
      }

      if (!state.currentModelSelection) {
        addToast("请先选择用于解析简历的模型", "error");
        return;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setFile(f);
      setUploading(true);
      resetProgress();
      setProgressMessage(`正在上传「${f.name}」`);

      try {
        await uploadFile(
          f,
          state.currentModelSelection,
          handleStreamEvent,
          (error) => {
            setParseError(error.message);
            setProgressMessage("上传或解析失败");
            addToast(error.message, "error");
            onUploaded();
          },
          controller.signal
        );
      } finally {
        setUploading(false);
      }
    },
    [
      addToast,
      handleStreamEvent,
      onUploaded,
      state.currentModelSelection,
      uploadFile,
    ]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const hasNoModel = !modelsLoading && models.length === 0;
  const disabled = uploading || hasNoModel || !state.currentModelSelection;

  return (
    <Card shadow="none" radius="lg" padding="lg" className="border-dashed">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <ModelSelectionPicker
          models={models}
          loading={modelsLoading}
          value={state.currentModelSelection}
          disabled={uploading}
          onChange={setModelSelection}
        />
        {hasNoModel && (
          <Link
            href="/settings/providers"
            className={buttonClassName({ variant: "secondary", size: "sm" })}
          >
            配置模型
          </Link>
        )}
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`text-center py-10 px-6 rounded-2xl transition-colors ${
          dragging ? "bg-primary-200/30" : ""
        }`}
      >
        <div className="mb-4">
          <svg
            className="w-10 h-10 mx-auto text-text-muted"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>
        <p className="text-sm text-text-primary font-medium mb-1">
          {uploading
            ? `正在处理「${file?.name}」`
            : "拖拽简历文件到此处，或点击选择"}
        </p>
        <p className="text-xs text-text-muted mb-4">
          支持 PDF、DOCX、PNG、JPG、JPEG 格式，上传后会自动解析
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept={SUPPORTED_EXTENSIONS}
          onChange={onFileChange}
          className="hidden"
        />
        <Button
          variant="secondary"
          size="sm"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? "处理中..." : "选择文件"}
        </Button>
      </div>

      {(uploading || progressMessage || parseError || modelError) && (
        <div className="mt-5 space-y-3">
          <div className="h-2 overflow-hidden rounded-full bg-surface-secondary">
            <div
              className={`h-full transition-all ${
                parseError ? "bg-error-text" : "bg-info-text"
              }`}
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
          {progressMessage && (
            <p className="text-xs text-text-secondary">{progressMessage}</p>
          )}
          {modelError && (
            <p className="text-xs text-warning-text">{modelError}</p>
          )}
          {parseError && (
            <p className="text-xs text-error-text">{parseError}</p>
          )}
        </div>
      )}
    </Card>
  );
}
