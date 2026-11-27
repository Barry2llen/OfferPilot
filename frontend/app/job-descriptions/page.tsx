import FormDrawer from "@/app/components/ui/form-drawer";
import { Link } from "react-router";
import { BriefcaseBusiness, ImagePlus, Link2, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
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
  const { initializeModelSelection, setModelSelection } = useAppActions();
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
        if (modelItems.length > 0) initializeModelSelection(modelItems[0].id);
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
  }, [initializeModelSelection]);

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
      <div className="electron-titlebar-safe-top min-h-full bg-surface-primary"><div className="mx-auto max-w-[1280px] px-5 pb-10 sm:px-8 lg:px-10">
        <Skeleton className="mb-2 h-8 w-32 rounded-lg" />
        <Skeleton className="mb-6 h-4 w-72 rounded-lg" />
        <div className="jd-workspace">
          <Skeleton className="h-96 rounded-2xl" />
          <div className="space-y-2">
            {[1, 2, 3].map((item) => (
              <Skeleton key={item} className="h-28 rounded-xl" />
            ))}
          </div>
        </div>
      </div></div>
    );
  }

  if (error) {
    return (
      <div className="electron-titlebar-safe-top min-h-full bg-surface-primary"><div className="mx-auto max-w-[1280px] px-5 pb-10 sm:px-8 lg:px-10">
        <div className="py-20 text-center">
          <p className="mb-4 text-sm text-error-text">{error}</p>
          <Button variant="secondary" onClick={refetch}>
            {t("common.retry")}
          </Button>
        </div>
      </div></div>
    );
  }

  const imageCount = localImages.length + selectedLibraryFiles.length;

  return (
    <div className="electron-titlebar-safe-top min-h-full bg-surface-primary"><div className="mx-auto max-w-[1280px] px-5 pb-10 sm:px-8 lg:px-10">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-text-primary">
          {t("jobDescription.title")}
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          {t("jobDescription.description")}
        </p>
      </header>

      <div className="jd-workspace">
        <div className="min-w-0 space-y-4">
          <section className="jd-composer" aria-label={t("jobDescription.title")}>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-light px-4 py-3">
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

            <textarea
              aria-label={t("jobDescription.textPlaceholder")}
              value={jdText}
              disabled={running}
              onChange={(event) => setJdText(event.target.value)}
              placeholder={t("jobDescription.textPlaceholder")}
              className="block min-h-64 w-full resize-y bg-transparent px-5 py-4 text-[15px] leading-7 text-text-primary placeholder:text-text-muted disabled:opacity-60"
            />
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={JD_IMAGE_ACCEPT}
              onChange={handleFileChange}
              className="hidden"
            />

            {imageCount > 0 && (
              <div className="grid grid-cols-1 gap-2 px-4 pb-4 sm:grid-cols-2">
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

            <label className="flex items-center gap-2.5 border-t border-border-light px-5">
              <Link2 size={16} className="shrink-0 text-text-muted" aria-hidden="true" />
              <input
                type="url"
                aria-label={t("jobDescription.sourceUrl")}
                value={sourceUrl}
                disabled={running}
                onChange={(event) => setSourceUrl(event.target.value)}
                placeholder={t("jobDescription.sourceUrl")}
                className="h-12 min-w-0 flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted disabled:opacity-60"
              />
            </label>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-light px-3 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={running}
                  onClick={() => setImagePickerOpen(true)}
                  title={t("jobDescription.imageDescription")}
                >
                  <ImagePlus size={16} aria-hidden="true" />
                  {t("jobDescription.chooseImages")}
                  {imageCount > 0 && (
                    <span className="rounded-full bg-surface-secondary px-1.5 text-xs tabular-nums text-text-primary">
                      {formatLocaleNumber(imageCount)}
                    </span>
                  )}
                </Button>
                <span className="hidden min-w-0 truncate text-xs text-text-muted md:inline">
                  {imageCount > 0 ? t("jobDescription.imageDescription") : t("jobDescription.notSelectedImages")}
                </span>
              </div>
              <Button size="sm" pill className="px-5" disabled={disabled || !hasInput} onClick={handleSubmit}>
                {running ? t("jobDescription.analyzing") : t("jobDescription.start")}
              </Button>
            </div>
          </section>

          <div className="jd-progress" aria-live="polite">{task && (
            <div className="rounded-xl border border-border-light bg-surface-secondary p-4">
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
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-primary">
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
          )}</div>
        </div>

        <section className="jd-saved min-w-0" aria-labelledby="jd-saved-title">
          <div className="mb-3 flex items-baseline justify-between gap-2 px-1">
            <h2 id="jd-saved-title" className="text-sm font-semibold text-text-primary">
              {t("appearance.savedAnalyses")}
            </h2>
            {data && data.length > 0 && (
              <span className="text-xs tabular-nums text-text-muted">{formatLocaleNumber(data.length)}</span>
            )}
          </div>
          {data && data.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border-default px-4 py-12 text-center">
              <BriefcaseBusiness size={22} strokeWidth={1.6} className="mx-auto mb-3 text-text-muted" aria-hidden="true" />
              <p className="mb-1 text-sm font-medium text-text-primary">{t("jobDescription.noAnalyses")}</p>
              <p className="text-xs text-text-muted">{t("jobDescription.noAnalysesDescription")}</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {data?.map((item) => (
                <li key={item.id} className="jd-saved-card relative rounded-xl border border-border-light p-4 transition-colors">
                  <div className="flex items-start gap-2">
                    <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-text-primary">
                      {/* Stretched link: the whole card opens the detail page. */}
                      <Link to={`/job-descriptions/${item.id}`} className="jd-card-link after:absolute after:inset-0 after:rounded-xl">
                        {item.job_title || `JD #${item.id}`}
                      </Link>
                    </h3>
                    <Badge variant={statusVariant(item.status)} size="sm">
                      {statusLabel(item.status)}
                    </Badge>
                  </div>
                  <p className="mt-1 truncate text-xs text-text-secondary">
                    {[item.company_name, item.primary_location]
                      .filter(Boolean)
                      .join(" · ") || t("jobDescription.unidentifiedCompany")}
                  </p>
                  {item.summary && (
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-text-muted">
                      {item.summary}
                    </p>
                  )}
                  {item.error_message && (
                    <p
                      className="mt-2 line-clamp-2 break-words text-xs text-error-text"
                      title={item.error_message}
                    >
                      {item.error_message}
                    </p>
                  )}
                  <AnalysisTaskStatus
                    task={
                      state.analysisTasks[
                        analysisTaskKey("job_description", item.id)
                      ]
                    }
                  />
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <p className="min-w-0 truncate text-xs tabular-nums text-text-muted">
                      {formatTime(item.created_at)}
                      {item.status === "parsed" &&
                        ` · ${t("jobDescription.blockCount", { count: item.block_count })} · ${t(
                          "jobDescription.factCount",
                          { count: item.fact_count },
                        )}`}
                    </p>
                    <button
                      type="button"
                      className="jd-delete relative z-10 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition hover:bg-error-bg hover:text-error-text disabled:opacity-40"
                      aria-label={deleting === item.id ? t("jobDescription.deleteInProgress") : t("common.delete")}
                      title={deleting === item.id ? t("jobDescription.deleteInProgress") : t("common.delete")}
                      disabled={deleting === item.id}
                      onClick={() => setConfirmDelete(item)}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

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

      <FormDrawer
        open={imagePickerOpen}
        title={t("jobDescription.pickerTitle")}
        onClose={() => setImagePickerOpen(false)}
        toolbar={
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
              type="search"
              value={imagePickerQuery}
              onChange={(event) => setImagePickerQuery(event.target.value)}
              aria-label={t("jobDescription.searchLibraryImages")}
              placeholder={t("jobDescription.searchLibraryImages")}
              className="h-9 min-w-0 flex-1 rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-text-primary outline-none transition"
            />
          </div>
        }
        footer={
          <>
            <span className="text-xs text-text-muted">
              {t("jobDescription.selectedImages", {
                count: localImages.length + selectedFileIds.length,
              })}
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setImagePickerOpen(false)}
            >
              {t("common.done")}
            </Button>
          </>
        }
      >
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
      </FormDrawer>
    </div></div>
  );
}
