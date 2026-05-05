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
import { useResumeUpload } from "@/app/lib/context/resume-upload-context";
import { useToast } from "@/app/components/ui/toast";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import ModelSelectionPicker from "@/app/components/chat/model-selection-picker";
import type {
  ModelSelectionResponse,
  ResumeDetail,
} from "@/app/lib/api/types";

interface ResumeUploaderProps {
  onUploaded: (detail?: ResumeDetail) => void;
  uploadFile?: typeof resumesApi.upload;
}

export default function ResumeUploader({
  onUploaded,
  uploadFile = resumesApi.upload,
}: ResumeUploaderProps) {
  const [dragging, setDragging] = useState(false);
  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { addToast } = useToast();
  const { state } = useAppContext();
  const { setModelSelection } = useAppActions();
  const { task, running, startUpload } = useResumeUpload();
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

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

      await startUpload({
        file: f,
        selectionId: state.currentModelSelection,
        uploadFile,
        onCompleted: (detail) => {
          if (mountedRef.current) {
            onUploaded(detail);
          }
        },
      });
    },
    [
      addToast,
      onUploaded,
      state.currentModelSelection,
      startUpload,
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
  const disabled = running || hasNoModel || !state.currentModelSelection;

  return (
    <Card shadow="none" radius="lg" padding="lg" className="border-dashed">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <ModelSelectionPicker
          models={models}
          loading={modelsLoading}
          value={state.currentModelSelection}
          disabled={running}
          onChange={setModelSelection}
        />
        {hasNoModel && (
          <Link
            href="/settings/providers"
            className={buttonClassName({ variant: "secondary", size: "sm" })}
          >
            模型配置
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
          {running
            ? `正在处理「${task?.fileName}」`
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
          {running ? "处理中..." : "选择文件"}
        </Button>
      </div>

      {task && (
        <div className="mt-5 space-y-3">
          <div className="h-2 overflow-hidden rounded-full bg-surface-secondary">
            <div
              className={`h-full transition-all ${
                task.error ? "bg-error-text" : "bg-info-text"
              }`}
              style={{ width: `${Math.round(task.progress * 100)}%` }}
            />
          </div>
          {task.message && (
            <p className="text-xs text-text-secondary">{task.message}</p>
          )}
          {task.modelError && (
            <p className="text-xs text-warning-text">{task.modelError}</p>
          )}
          {task.error && (
            <p className="text-xs text-error-text">{task.error}</p>
          )}
        </div>
      )}
    </Card>
  );
}
