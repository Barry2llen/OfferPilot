"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
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
  const [files, setFiles] = useState<File[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [task, setTask] = useState<JdTask | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] =
    useState<JobDescriptionAnalysisListItem | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const hasInput =
    jdText.trim() || sourceUrl.trim() || files.length > 0 || selectedFileIds.length > 0;
  const hasNoModel = !modelsLoading && models.length === 0;
  const running = task?.status === "running";
  const disabled = running || hasNoModel || !state.currentModelSelection;

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    const accepted: File[] = [];
    for (const file of picked) {
      if (!isSupportedJdImage(file)) {
        addToast("JD 图片仅支持 PNG、JPG、JPEG", "error");
        continue;
      }
      accepted.push(file);
    }
    setFiles((current) => [...current, ...accepted]);
    if (fileInputRef.current) fileInputRef.current.value = "";
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
          setFiles([]);
          setSelectedFileIds([]);
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
          files,
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
            value={sourceUrl}
            disabled={running}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="来源 URL"
            className="h-11 rounded-2xl border border-border-light bg-white px-4 text-sm text-text-primary outline-none transition focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
          />

          <div className="rounded-2xl border border-dashed border-border-default bg-surface-primary p-4">
            <div className="flex flex-wrap items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={JD_IMAGE_ACCEPT}
                onChange={handleFileChange}
                className="hidden"
              />
              <Button
                variant="secondary"
                size="sm"
                disabled={running}
                onClick={() => fileInputRef.current?.click()}
              >
                选择图片
              </Button>
              <span className="text-xs text-text-muted">支持 PNG、JPG、JPEG</span>
            </div>
            {files.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {files.map((file) => (
                  <button
                    key={`${file.name}-${file.size}`}
                    type="button"
                    disabled={running}
                    onClick={() =>
                      setFiles((current) => current.filter((item) => item !== file))
                    }
                    className="rounded-lg bg-info-bg px-2.5 py-1 text-xs font-medium text-info-text"
                  >
                    {file.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {libraryFiles.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-text-secondary">
                文件库图片
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {libraryFiles.map((file) => {
                  const checked = selectedFileIds.includes(file.id);
                  return (
                    <label
                      key={file.id}
                      className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-sm transition ${
                        checked
                          ? "border-primary-500 bg-primary-200/20"
                          : "border-border-light bg-white hover:border-text-muted"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={running}
                        onChange={() => toggleLibraryFile(file.id)}
                        className="h-4 w-4"
                      />
                      <span className="min-w-0 flex-1 truncate text-text-primary">
                        {file.original_filename}
                      </span>
                      <span className="text-xs text-text-muted">{file.id}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {selectedLibraryFiles.length > 0 && (
            <p className="text-xs text-text-muted">
              已选择 {selectedLibraryFiles.length} 张历史图片
            </p>
          )}

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
    </div>
  );
}
