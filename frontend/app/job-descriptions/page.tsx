import { Link } from "react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import AnalysisTaskStatus from "@/app/components/analysis/analysis-task-status";
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
import {
  createJobDescriptionState,
  reduceJobDescriptionEof,
  reduceJobDescriptionEvent,
  reduceJobDescriptionTransportError,
} from "@/app/lib/job-descriptions/adapter";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAppActions, useAppContext } from "@/app/lib/context/app-context";
import { useToast } from "@/app/components/ui/toast";
import i18n, { formatLocaleNumber } from "@/app/lib/i18n";
import type {
  ChatFileListItem,
  JobDescriptionAnalysisListItem,
  ModelSelectionResponse,
} from "@/app/lib/api/types";
import type {
  JobDescriptionStreamEffect,
  JobDescriptionStreamLabels,
  JobDescriptionTask,
} from "@/app/lib/job-descriptions/types";
import { analysisTaskKey } from "@/app/lib/analysis-events/types";

interface LocalJdImage {
  key: string;
  file: File;
  previewUrl: string;
}

function formatTime(value: string | null): string {
  if (!value) return i18n.t("jobDescription.notCompleted");
  return new Date(value).toLocaleString(i18n.language, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusLabel(status: JobDescriptionAnalysisListItem["status"]): string {
  if (status === "parsed") return i18n.t("jobDescription.completed");
  if (status === "failed") return i18n.t("jobDescription.failed");
  return i18n.t("jobDescription.processing");
}

function statusVariant(status: JobDescriptionAnalysisListItem["status"]) {
  if (status === "parsed") return "success";
  if (status === "failed") return "error";
  return "warning";
}

function isImageFile(file: ChatFileListItem): boolean {
  const mediaType = file.media_type?.toLowerCase() || "";
  return mediaType === "image/png" || mediaType === "image/jpeg";
}

export default function JobDescriptionsPage() {
  const { t } = useTranslation();
  const fetchAnalyses = useCallback(() => jobDescriptionsApi.list(), []);
  const { data, loading, error, refetch, refresh } = useAsyncData(fetchAnalyses, [
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
  const [task, setTask] = useState<JobDescriptionTask | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] =
    useState<JobDescriptionAnalysisListItem | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadKeyRef = useRef(0);
  const runningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const { state } = useAppContext();
  const { setModelSelection } = useAppActions();
  const { addToast } = useToast();

  useEffect(() => {
    if (state.analysisEventVersions.job_description > 0) refresh();
  }, [refresh, state.analysisEventVersions.job_description]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

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
        addToast(t("jobDescription.invalidImage"), "error");
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
      addToast(t("jobDescription.chooseModelError"), "error");
      return;
    }
    if (!hasInput) {
      addToast(t("jobDescription.inputRequired"), "error");
      return;
    }
    if (runningRef.current) {
      addToast(t("jobDescription.busy"), "warning");
      return;
    }

    runningRef.current = true;
    const initialTask: JobDescriptionTask = {
      status: "running",
      progress: 0,
      message: t("jobDescription.submitting"),
      modelError: null,
      error: null,
      analysisId: null,
    };
    setTask(initialTask);

    const labels: JobDescriptionStreamLabels = {
      createdMessage: t("jobDescription.created"),
      progressMessage: t("jobDescription.analysisProgress"),
      modelRetryMessage: t("jobDescription.modelRetrying"),
      completeMessage: t("jobDescription.analysisComplete"),
      failedMessage: t("jobDescription.analysisFailed"),
      submitFailedMessage: t("jobDescription.submitFailed"),
    };
    let streamState = createJobDescriptionState(initialTask);
    const controller = new AbortController();
    abortRef.current = controller;

    const applyResult = (result: {
      state: typeof streamState;
      effects: JobDescriptionStreamEffect[];
    }) => {
      streamState = result.state;
      setTask(streamState.task);
      for (const effect of result.effects) {
        switch (effect.type) {
          case "notify":
            addToast(effect.message, effect.level);
            break;
          case "refetch":
            refetch();
            break;
          case "reset_input":
            setJdText("");
            setSourceUrl("");
            localImages.forEach((item) => URL.revokeObjectURL(item.previewUrl));
            setLocalImages([]);
            setSelectedFileIds([]);
            setImagePickerOpen(false);
            break;
          case "accepted":
            break;
        }
      }
    };

    try {
      for await (const event of jobDescriptionsApi.analyze(
        {
          selectionId: state.currentModelSelection,
          jdText,
          sourceUrl,
          files: localImages.map((item) => item.file),
          fileIds: selectedFileIds,
        },
        { signal: controller.signal },
      )) {
        if (controller.signal.aborted) break;
        applyResult(reduceJobDescriptionEvent(streamState, event, labels));
      }
      if (!controller.signal.aborted) {
        applyResult(reduceJobDescriptionEof(streamState, labels));
      }
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        applyResult(
          reduceJobDescriptionTransportError(
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
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(confirmDelete.id);
    try {
      await jobDescriptionsApi.delete(confirmDelete.id);
      addToast(t("jobDescription.deleted"), "success");
      setConfirmDelete(null);
      refetch();
    } catch (err: unknown) {
      addToast(err instanceof Error ? err.message : t("errors.deleteFailed"), "error");
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
            {t("common.retry")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="electron-titlebar-safe-top mx-auto max-w-4xl p-6 lg:py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-text-primary">
          {t("jobDescription.title")}
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          {t("jobDescription.description")}
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
              to="/settings/providers"
              className={buttonClassName({ variant: "secondary", size: "sm" })}
            >
              {t("settings.title")}
            </Link>
          )}
        </div>

        <div className="grid gap-4">
          <textarea
            value={jdText}
            disabled={running}
            onChange={(event) => setJdText(event.target.value)}
            placeholder={t("jobDescription.textPlaceholder")}
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
                <p className="text-sm font-medium text-text-primary">{t("jobDescription.chooseImages")}</p>
                <p className="mt-1 text-xs text-text-muted">
                  {t("jobDescription.imageDescription")}
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                disabled={running}
                onClick={() => setImagePickerOpen(true)}
              >
                {t("jobDescription.chooseImages")}
              </Button>
            </div>

            {localImages.length === 0 && selectedLibraryFiles.length === 0 ? (
              <p className="mt-4 rounded-xl bg-white px-3 py-4 text-center text-xs text-text-muted">
                {t("jobDescription.notSelectedImages")}
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
            placeholder={t("jobDescription.sourceUrl")}
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
                    to={`/job-descriptions/${task.analysisId}`}
                    className="text-xs font-medium text-primary-600"
                  >
                    {t("jobDescription.detail")}
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
              {running ? t("jobDescription.analyzing") : t("jobDescription.start")}
            </Button>
          </div>
        </div>
      </Card>

      {data && data.length === 0 ? (
        <div className="rounded-[20px] border-2 border-dashed border-border-default bg-surface-primary px-4 py-16 text-center">
          <p className="mb-1 text-sm font-medium text-text-primary">{t("jobDescription.noAnalyses")}</p>
          <p className="text-xs text-text-muted">{t("jobDescription.noAnalysesDescription")}</p>
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
                      .join(" · ") || t("jobDescription.unidentifiedCompany")}
                  </p>
                  {item.summary && (
                    <p className="mt-2 line-clamp-2 text-sm text-text-muted">
                      {item.summary}
                    </p>
                  )}
                  {item.error_message && (
                    <p className="mt-2 text-sm text-error-text">{item.error_message}</p>
                  )}
                  <AnalysisTaskStatus
                    task={
                      state.analysisTasks[
                        analysisTaskKey("job_description", item.id)
                      ]
                    }
                  />
                  <p className="mt-2 text-xs text-text-muted">
                    {formatTime(item.created_at)} · {t("jobDescription.countBlocksFacts", {
                      blocks: formatLocaleNumber(item.block_count),
                      facts: formatLocaleNumber(item.fact_count),
                    })}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Link
                    to={`/job-descriptions/${item.id}`}
                    className={buttonClassName({ variant: "secondary", size: "sm" })}
                  >
                    {t("jobDescription.detail")}
                  </Link>
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={deleting === item.id}
                    onClick={() => setConfirmDelete(item)}
                  >
                    {deleting === item.id ? t("jobDescription.deleteInProgress") : t("common.delete")}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title={t("jobDescription.deleteTitle")}
        message={t("jobDescription.deleteMessage", {
          name:
            confirmDelete?.job_title ||
            t("jobDescription.defaultTitle", { id: confirmDelete?.id }),
        })}
        confirmLabel={t("common.delete")}
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
                  {t("jobDescription.pickerTitle")}
                </h3>
                <p className="text-xs text-text-muted">
                  {t("jobDescription.pickerDescription")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setImagePickerOpen(false)}
                className="rounded-lg p-1.5 text-text-muted transition hover:bg-surface-secondary hover:text-text-primary"
                aria-label={t("jobDescription.closePicker")}
                title={t("common.close")}
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
                  {t("jobDescription.uploadLocalImage")}
                </Button>
                <input
                  value={imagePickerQuery}
                  onChange={(event) => setImagePickerQuery(event.target.value)}
                  placeholder={t("jobDescription.searchLibraryImages")}
                  className="h-10 min-w-0 flex-1 rounded-xl bg-surface-secondary px-3 text-sm text-text-primary outline-none transition focus:bg-white focus:ring-2 focus:ring-primary-500/25"
                />
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {libraryFiles.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border-default px-4 py-10 text-center">
                  <p className="text-sm font-medium text-text-primary">
                    {t("jobDescription.libraryNoImages")}
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    {t("jobDescription.libraryNoImagesDescription")}
                  </p>
                </div>
              ) : filteredLibraryFiles.length === 0 ? (
                <p className="py-8 text-center text-sm text-text-muted">
                  {t("jobDescription.noMatchingImages")}
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
                {t("jobDescription.selectedImages", {
                  count: formatLocaleNumber(
                    localImages.length + selectedFileIds.length
                  ),
                })}
              </span>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setImagePickerOpen(false)}
              >
                {t("common.done")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
