"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import ChatAttachmentCard from "@/app/components/chat/chat-attachment-card";
import ModelSelectionPicker from "@/app/components/chat/model-selection-picker";
import { Skeleton } from "@/app/components/ui/skeleton";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { chatFilesApi } from "@/app/lib/api/chat-files";
import {
  JD_IMAGE_ACCEPT,
  isSupportedJdImage,
  jobDescriptionsApi,
} from "@/app/lib/api/job-descriptions";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAppActions, useAppContext } from "@/app/lib/context/app-context";
import { useToast } from "@/app/components/ui/toast";
import type {
  ChatFileListItem,
  JobDescriptionAnalysisListItem,
  JobDescriptionStreamEvent,
  ModelSelectionResponse,
} from "@/app/lib/api/types";

interface JdTask {
  status: "idle" | "running" | "success" | "error";
  progress: number;
  message: string;
  modelError: string | null;
  error: string | null;
  analysisId: number | null;
}

interface LocalJdImage {
  key: string;
  file: File;
  previewUrl: string;
}

function formatTime(value: string | null): string {
  if (!value) return "未完成";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusLabel(status: JobDescriptionAnalysisListItem["status"]): string {
  if (status === "parsed") return "已完成";
  if (status === "failed") return "失败";
  return "处理中";
}

function statusVariant(status: JobDescriptionAnalysisListItem["status"]) {
  if (status === "parsed") return "success";
  if (status === "failed") return "error";
  return "warning";
}

function extractAnalysis(data: Record<string, unknown>) {
  const value = data.job_description;
  if (value && typeof value === "object") {
    return value as JobDescriptionAnalysisListItem;
  }
  return undefined;
}

function isImageFile(file: ChatFileListItem): boolean {
  const mediaType = file.media_type?.toLowerCase() || "";
  return mediaType === "image/png" || mediaType === "image/jpeg";
}

export default function JobDescriptionsPage() {
  const fetchAnalyses = useCallback(() => jobDescriptionsApi.list(), []);
  const { data, loading, error, refetch } = useAsyncData(fetchAnalyses, [
    fetchAnalyses,
  ]);
  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [libraryFiles, setLibraryFiles] = useState<ChatFileListItem[]>([]);
  const [jdText, setJdText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [localImages, setLocalImages] = useState<LocalJdImage[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [imagePickerOpen, setImagePickerOpen] = useState(false);
  const [imagePickerQuery, setImagePickerQuery] = useState("");
  const [task, setTask] = useState<JdTask | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] =
    useState<JobDescriptionAnalysisListItem | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadKeyRef = useRef(0);
  const runningRef = useRef(false);
  const { state } = useAppContext();
  const { setModelSelection } = useAppActions();
  const { addToast } = useToast();

  useEffect(() => {
    let mounted = true;
    Promise.all([modelSelectionsApi.list(), chatFilesApi.list()])
      .then(([modelItems, fileItems]) => {
        if (!mounted) return;
        setModels(modelItems);
        setLibraryFiles(fileItems.filter(isImageFile));
        if (state.currentModelSelection === null && modelItems.length > 0) {
          setModelSelection(modelItems[0].id);
        }
      })
      .catch(() => {
        if (!mounted) return;
        setModels([]);
        setLibraryFiles([]);
      })
      .finally(() => {
        if (mounted) setModelsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [setModelSelection, state.currentModelSelection]);

  const selectedLibraryFiles = useMemo(() => {
    const selected = new Set(selectedFileIds);
    return libraryFiles.filter((file) => selected.has(file.id));
  }, [libraryFiles, selectedFileIds]);

  const filteredLibraryFiles = useMemo(() => {
    const query = imagePickerQuery.trim().toLowerCase();
    if (!query) return libraryFiles;
    return libraryFiles.filter(
      (file) =>
        file.id.toLowerCase().includes(query) ||
        file.original_filename.toLowerCase().includes(query)
    );
  }, [imagePickerQuery, libraryFiles]);

  const selectedFileIdSet = useMemo(
    () => new Set(selectedFileIds),
    [selectedFileIds]
  );

  const hasInput =
    jdText.trim() ||
    sourceUrl.trim() ||
    localImages.length > 0 ||
    selectedFileIds.length > 0;
  const hasNoModel = !modelsLoading && models.length === 0;
  const running = task?.status === "running";
  const disabled = running || hasNoModel || !state.currentModelSelection;

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    const accepted: LocalJdImage[] = [];
    for (const file of picked) {
      if (!isSupportedJdImage(file)) {
        addToast("JD 图片仅支持 PNG、JPG、JPEG", "error");
        continue;
      }
      uploadKeyRef.current += 1;
      accepted.push({
        key: `jd-image-${uploadKeyRef.current}`,
        file,
        previewUrl: URL.createObjectURL(file),
      });
    }
    setLocalImages((current) => [...current, ...accepted]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeLocalImage = (key: string) => {
    setLocalImages((current) => {
      const target = current.find((item) => item.key === key);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return current.filter((item) => item.key !== key);
    });
  };

  const toggleLibraryFile = (fileId: string) => {
    setSelectedFileIds((current) =>
      current.includes(fileId)
        ? current.filter((item) => item !== fileId)
        : [...current, fileId]
    );
  };

  const handleSubmit = async () => {
    if (!state.currentModelSelection) {
      addToast("请先选择用于分析 JD 的模型", "error");
      return;
    }
    if (!hasInput) {
      addToast("请粘贴 JD、填写来源 URL，或选择图片", "error");
      return;
    }
    if (runningRef.current) {
      addToast("已有 JD 正在分析，请等待完成", "warning");
      return;
    }

    runningRef.current = true;
    setTask({
      status: "running",
      progress: 0,
      message: "正在提交 JD 分析",
      modelError: null,
      error: null,
      analysisId: null,
    });

    const handleEvent = (event: JobDescriptionStreamEvent) => {
      const kind = event.event || event.type;
      switch (kind) {
        case "job_description": {
          const detail = extractAnalysis(event.data);
          setTask((current) => ({
            ...(current ?? {
              status: "running",
              progress: 0,
              message: "",
              modelError: null,
              error: null,
              analysisId: null,
            }),
            progress: 0.05,
            message: "记录已创建，开始分析",
            analysisId: detail?.id ?? current?.analysisId ?? null,
          }));
          break;
        }
        case "progress": {
          setTask((current) => ({
            ...(current ?? {
              status: "running",
              progress: 0,
              message: "",
              modelError: null,
              error: null,
              analysisId: null,
            }),
            progress:
              typeof event.data.progress === "number"
                ? Math.max(0, Math.min(event.data.progress, 1))
                : current?.progress ?? 0,
            message:
              typeof event.data.message === "string"
                ? event.data.message
                : "正在分析 JD",
          }));
          break;
        }
        case "model_error": {
          const detail =
            typeof event.data.detail === "string"
              ? event.data.detail
              : "模型调用失败，正在重试";
          setTask((current) => ({
            ...(current ?? {
              status: "running",
              progress: 0,
              message: "",
              modelError: null,
              error: null,
              analysisId: null,
            }),
            modelError: detail,
          }));
          break;
        }
        case "final": {
          const detail = extractAnalysis(event.data);
          setTask((current) => ({
            ...(current ?? {
              status: "running",
              progress: 0,
              message: "",
              modelError: null,
              error: null,
              analysisId: null,
            }),
            status: "success",
            progress: 1,
            message: "JD 分析完成",
            analysisId: detail?.id ?? current?.analysisId ?? null,
          }));
          runningRef.current = false;
          setJdText("");
          setSourceUrl("");
          localImages.forEach((item) => URL.revokeObjectURL(item.previewUrl));
          setLocalImages([]);
          setSelectedFileIds([]);
          setImagePickerOpen(false);
          addToast("JD 分析完成", "success");
          refetch();
          break;
        }
        case "error": {
          const detail =
            typeof event.data.detail === "string"
              ? event.data.detail
              : "JD 分析失败";
          setTask((current) => ({
            ...(current ?? {
              status: "running",
              progress: 0,
              message: "",
              modelError: null,
              error: null,
              analysisId: null,
            }),
            status: "error",
            message: "JD 分析失败",
            error: detail,
            analysisId:
              typeof event.data.analysis_id === "number"
                ? event.data.analysis_id
                : current?.analysisId ?? null,
          }));
          runningRef.current = false;
          addToast(detail, "error");
          refetch();
          break;
        }
      }
    };

    try {
      await jobDescriptionsApi.analyze(
        {
          selectionId: state.currentModelSelection,
          jdText,
          sourceUrl,
          files: localImages.map((item) => item.file),
          fileIds: selectedFileIds,
        },
        handleEvent,
        (error) => {
          setTask((current) => ({
            ...(current ?? {
              status: "running",
              progress: 0,
              message: "",
              modelError: null,
              error: null,
              analysisId: null,
            }),
            status: "error",
            message: "提交失败",
            error: error.message,
          }));
          runningRef.current = false;
          addToast(error.message, "error");
        }
      );
    } finally {
      runningRef.current = false;
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(confirmDelete.id);
    try {
      await jobDescriptionsApi.delete(confirmDelete.id);
      addToast("JD 分析记录已删除", "success");
      setConfirmDelete(null);
      refetch();
    } catch (err: unknown) {
      addToast(err instanceof Error ? err.message : "删除失败", "error");
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return (
      <div className="electron-titlebar-safe-top mx-auto max-w-4xl p-6 lg:py-8">
        <Skeleton className="mb-2 h-8 w-32 rounded-lg" />
        <Skeleton className="mb-6 h-4 w-72 rounded-lg" />
        <Skeleton className="mb-6 h-80 rounded-[20px]" />
        <div className="space-y-3">
          {[1, 2, 3].map((item) => (
            <Skeleton key={item} className="h-32 rounded-[20px]" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="electron-titlebar-safe-top mx-auto max-w-4xl p-6">
        <div className="py-20 text-center">
          <p className="mb-4 text-sm text-error-text">{error}</p>
          <Button variant="secondary" onClick={refetch}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="electron-titlebar-safe-top mx-auto max-w-4xl p-6 lg:py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-text-primary">
          JD 分析
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          保存并结构化分析岗位描述，支持文本、URL 和图片输入
        </p>
      </div>

      <Card shadow="none" radius="lg" padding="lg" className="mb-6">
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

        <div className="grid gap-4">
          <textarea
            value={jdText}
            disabled={running}
            onChange={(event) => setJdText(event.target.value)}
            placeholder="粘贴 JD 原文"
            className="min-h-40 resize-y rounded-2xl border border-border-light bg-white px-4 py-3 text-sm text-text-primary outline-none transition focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={JD_IMAGE_ACCEPT}
            onChange={handleFileChange}
            className="hidden"
          />

          <div className="rounded-2xl border border-dashed border-border-default bg-surface-primary p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-text-primary">选择图片</p>
                <p className="mt-1 text-xs text-text-muted">
                  支持上传本地 PNG、JPG、JPEG，也可复用文件库图片
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                disabled={running}
                onClick={() => setImagePickerOpen(true)}
              >
                选择图片
              </Button>
            </div>

            {localImages.length === 0 && selectedLibraryFiles.length === 0 ? (
              <p className="mt-4 rounded-xl bg-white px-3 py-4 text-center text-xs text-text-muted">
                尚未选择图片
              </p>
            ) : (
              <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {localImages.map((item) => (
                  <ChatAttachmentCard
                    key={item.key}
                    attachment={{
                      fileId: null,
                      originalFilename: item.file.name,
                      mediaType: item.file.type || null,
                      pending: true,
                      previewUrl: item.previewUrl,
                      sizeBytes: item.file.size,
                    }}
                    variant="composer"
                    onRemove={running ? undefined : () => removeLocalImage(item.key)}
                  />
                ))}
                {selectedLibraryFiles.map((file) => (
                  <ChatAttachmentCard
                    key={file.id}
                    attachment={{
                      fileId: file.id,
                      originalFilename: file.original_filename,
                      mediaType: file.media_type,
                      rawUrl: chatFilesApi.rawUrl(file.id),
                      sizeBytes: file.size_bytes,
                    }}
                    variant="composer"
                    onRemove={
                      running ? undefined : () => toggleLibraryFile(file.id)
                    }
                  />
                ))}
              </div>
            )}
          </div>

          <input
            value={sourceUrl}
            disabled={running}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="来源 URL"
            className="h-11 rounded-2xl border border-border-light bg-white px-4 text-sm text-text-primary outline-none transition focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
          />

          {task && (
            <div className="rounded-2xl bg-surface-secondary p-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-text-primary">
                  {task.message}
                </p>
                {task.analysisId && !running && (
                  <Link
                    href={`/job-descriptions/${task.analysisId}`}
                    className="text-xs font-medium text-primary-600"
                  >
                    查看详情
                  </Link>
                )}
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-white">
                <div
                  className={`h-full transition-all ${
                    task.status === "error" ? "bg-error-text" : "bg-primary-500"
                  }`}
                  style={{ width: `${Math.round(task.progress * 100)}%` }}
                />
              </div>
              {task.modelError && (
                <p className="mt-2 text-xs text-warning-text">{task.modelError}</p>
              )}
              {task.error && (
                <p className="mt-2 text-xs text-error-text">{task.error}</p>
              )}
            </div>
          )}

          <div className="flex justify-end">
            <Button disabled={disabled || !hasInput} onClick={handleSubmit}>
              {running ? "分析中..." : "开始分析"}
            </Button>
          </div>
        </div>
      </Card>

      {data && data.length === 0 ? (
        <div className="rounded-[20px] border-2 border-dashed border-border-default bg-surface-primary px-4 py-16 text-center">
          <p className="mb-1 text-sm font-medium text-text-primary">暂无 JD 分析</p>
          <p className="text-xs text-text-muted">提交第一份 JD 后，这里会显示历史记录</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data?.map((item) => (
            <Card key={item.id} shadow="none" radius="lg" padding="md">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-base font-semibold text-text-primary">
                      {item.job_title || `JD #${item.id}`}
                    </h2>
                    <Badge variant={statusVariant(item.status)} size="sm">
                      {statusLabel(item.status)}
                    </Badge>
                  </div>
                  <p className="text-sm text-text-secondary">
                    {[item.company_name, item.primary_location]
                      .filter(Boolean)
                      .join(" · ") || "未识别公司和地点"}
                  </p>
                  {item.summary && (
                    <p className="mt-2 line-clamp-2 text-sm text-text-muted">
                      {item.summary}
                    </p>
                  )}
                  {item.error_message && (
                    <p className="mt-2 text-sm text-error-text">{item.error_message}</p>
                  )}
                  <p className="mt-2 text-xs text-text-muted">
                    {formatTime(item.created_at)} · {item.block_count} 个需求块 ·{" "}
                    {item.fact_count} 条事实
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Link
                    href={`/job-descriptions/${item.id}`}
                    className={buttonClassName({ variant: "secondary", size: "sm" })}
                  >
                    详情
                  </Link>
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={deleting === item.id}
                    onClick={() => setConfirmDelete(item)}
                  >
                    {deleting === item.id ? "删除中..." : "删除"}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title="删除 JD 分析"
        message={`确定要删除「${confirmDelete?.job_title || `JD #${confirmDelete?.id}`}」吗？此操作不会删除文件库图片。`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
        loading={!!deleting}
      />

      {imagePickerOpen && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/20 backdrop-blur-sm"
            onClick={() => setImagePickerOpen(false)}
          />
          <div className="relative flex max-h-[82vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-[0_24px_70px_rgba(15,23,42,0.24)]">
            <div className="flex items-center justify-between border-b border-border-light px-5 py-4">
              <div>
                <h3 className="font-display text-lg font-semibold text-text-primary">
                  选择图片
                </h3>
                <p className="text-xs text-text-muted">
                  上传新图片或从文件库选择已有图片
                </p>
              </div>
              <button
                type="button"
                onClick={() => setImagePickerOpen(false)}
                className="rounded-lg p-1.5 text-text-muted transition hover:bg-surface-secondary hover:text-text-primary"
                aria-label="关闭选择图片"
                title="关闭"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="border-b border-border-light px-5 py-4">
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={running}
                  onClick={() => fileInputRef.current?.click()}
                >
                  上传本地图片
                </Button>
                <input
                  value={imagePickerQuery}
                  onChange={(event) => setImagePickerQuery(event.target.value)}
                  placeholder="搜索文件库图片"
                  className="h-10 min-w-0 flex-1 rounded-xl bg-surface-secondary px-3 text-sm text-text-primary outline-none transition focus:bg-white focus:ring-2 focus:ring-primary-500/25"
                />
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {libraryFiles.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border-default px-4 py-10 text-center">
                  <p className="text-sm font-medium text-text-primary">
                    文件库暂无图片
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    可以直接上传本地图片，提交后会保存进文件库
                  </p>
                </div>
              ) : filteredLibraryFiles.length === 0 ? (
                <p className="py-8 text-center text-sm text-text-muted">
                  没有匹配的文件库图片
                </p>
              ) : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {filteredLibraryFiles.map((file) => {
                    const selected = selectedFileIdSet.has(file.id);
                    return (
                      <ChatAttachmentCard
                        key={file.id}
                        onClick={() => {
                          if (!running) toggleLibraryFile(file.id);
                        }}
                        selected={selected}
                        variant="picker"
                        attachment={{
                          fileId: file.id,
                          originalFilename: file.original_filename,
                          mediaType: file.media_type,
                          rawUrl: chatFilesApi.rawUrl(file.id),
                          sizeBytes: file.size_bytes,
                          referenceCount: file.reference_count,
                          createdAt: file.created_at,
                        }}
                      />
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-border-light px-5 py-4">
              <span className="text-xs text-text-muted">
                已选 {localImages.length + selectedFileIds.length} 张图片
              </span>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setImagePickerOpen(false)}
              >
                完成
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
