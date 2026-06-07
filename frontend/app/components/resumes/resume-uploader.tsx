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
  variant?: "hero" | "inline";
}

export default function ResumeUploader({
  onUploaded,
  uploadFile = resumesApi.upload,
  variant = "inline",
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
  const isHero = variant === "hero";

  const modelControls = (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 ${
        isHero ? "absolute right-5 top-5 z-20" : "mb-5"
      }`}
    >
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
          className={buttonClassName({
            variant: "secondary",
            size: "sm",
            className: isHero ? "bg-white/90 shadow-sm" : "",
          })}
        >
          模型配置
        </Link>
      )}
    </div>
  );

  const uploadBody = (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`relative text-center transition-all duration-300 ${
        isHero
          ? "min-h-[220px] rounded-[20px] border border-dashed border-[#bfc5dc] bg-white px-5 py-10 shadow-brand-glow hover:border-primary-600 sm:min-h-[232px] sm:px-8"
          : "overflow-hidden rounded-2xl px-6 py-10"
      } ${dragging ? "border-primary-600 bg-primary-200/20" : ""}`}
    >
      {isHero && modelControls}
      {running && task && (
        <div
          className={`absolute inset-0 z-10 flex flex-col items-center justify-center bg-white/85 px-6 backdrop-blur-sm transition-all duration-300 ${
            isHero ? "rounded-[20px]" : "rounded-2xl"
          }`}
        >
          <p className="mb-4 text-sm font-medium text-text-primary">
            正在处理「{task.fileName}」
          </p>
          <div className="mb-3 h-2 w-full max-w-xs overflow-hidden rounded-full bg-surface-secondary shadow-inner">
            <div
              className={`h-full transition-all duration-300 ${
                task.error ? "bg-error-text" : "bg-primary-500"
              }`}
              style={{ width: `${Math.round(task.progress * 100)}%` }}
            />
          </div>
          {task.message && (
            <p className="text-xs text-text-secondary animate-pulse">
              {task.message}
            </p>
          )}
          {task.modelError && (
            <p className="mt-1 text-xs text-warning-text">{task.modelError}</p>
          )}
          {task.error && (
            <p className="mt-1 text-xs text-error-text">{task.error}</p>
          )}
        </div>
      )}

      <div
        className={`mx-auto mb-6 flex items-center justify-center rounded-full bg-[#dce1ff] text-primary-700 transition-transform duration-300 ${
          isHero ? "h-12 w-12" : "h-12 w-12"
        } ${dragging ? "scale-110" : ""}`}
      >
        <UploadCloudIcon className={isHero ? "h-6 w-6" : "h-6 w-6"} />
      </div>
      <p
        className={`font-display font-medium text-text-primary ${
          isHero ? "text-base sm:text-lg" : "text-base"
        }`}
      >
        {isHero ? "拖拽简历文件到此处" : "拖拽简历文件到此处，或点击选择"}
      </p>
      <p
        className={`mt-2 text-text-muted ${
          isHero ? "text-xs" : "text-xs"
        }`}
      >
        支持 PDF、DOCX、PNG、JPG、JPEG，上传后会自动解析
      </p>
      <input
        ref={fileInputRef}
        type="file"
        accept={SUPPORTED_EXTENSIONS}
        onChange={onFileChange}
        className="hidden"
      />
      <Button
        className={isHero ? "mt-6 shadow-brand-glow" : "mt-5"}
        variant={isHero ? "primary" : "secondary"}
        size="sm"
        pill={isHero}
        disabled={disabled}
        onClick={() => fileInputRef.current?.click()}
      >
        {running ? "处理中..." : "选择文件"}
      </Button>
    </div>
  );

  if (isHero) {
    return (
      <section>
        {uploadBody}
      </section>
    );
  }

  return (
    <Card shadow="none" radius="lg" padding="lg" className="border-dashed">
      {modelControls}
      {uploadBody}
    </Card>
  );
}

function UploadCloudIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M7 16.5a4.5 4.5 0 0 1 .65-8.95A5.75 5.75 0 0 1 18.6 9.7 3.75 3.75 0 0 1 18 17H8"
      />
      <path strokeLinecap="round" strokeLinejoin="round" d="m12 11-3 3m3-3 3 3m-3-3v9" />
    </svg>
  );
}
