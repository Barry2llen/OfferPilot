"use client";

import { useState, useCallback, useRef } from "react";
import { resumesApi, isSupportedFile, SUPPORTED_EXTENSIONS } from "@/app/lib/api/resumes";
import { useToast } from "@/app/components/ui/toast";
import Button from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import type { ResumeDetail } from "@/app/lib/api/types";

interface ResumeUploaderProps {
  onUploaded: (detail: ResumeDetail) => void;
  uploadFile?: (file: File) => Promise<ResumeDetail>;
}

export default function ResumeUploader({
  onUploaded,
  uploadFile = resumesApi.upload,
}: ResumeUploaderProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { addToast } = useToast();

  const handleFile = useCallback(
    async (f: File) => {
      if (!isSupportedFile(f)) {
        addToast("不支持的文件格式，支持 PDF、DOCX、PNG、JPG、JPEG", "error");
        return;
      }
      setFile(f);
      setUploading(true);
      try {
        const detail = await uploadFile(f);
        addToast(`「${f.name}」上传成功`, "success");
        setFile(null);
        onUploaded(detail);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "上传失败";
        addToast(msg, "error");
      } finally {
        setUploading(false);
      }
    },
    [addToast, onUploaded, uploadFile]
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

  return (
    <Card shadow="none" radius="lg" padding="lg" className="border-dashed">
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
            ? `正在上传「${file?.name}」...`
            : "拖拽简历文件到此处，或点击选择"}
        </p>
        <p className="text-xs text-text-muted mb-4">
          支持 PDF、DOCX、PNG、JPG、JPEG 格式
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
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? "上传中..." : "选择文件"}
        </Button>
      </div>
    </Card>
  );
}
