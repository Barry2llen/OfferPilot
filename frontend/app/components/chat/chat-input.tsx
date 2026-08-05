import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import Button from "@/app/components/ui/button";
import { useToast } from "@/app/components/ui/toast";
import ChatAttachmentCard, {
  isAttachmentImage,
} from "@/app/components/chat/chat-attachment-card";
import {
  chatFilesApi,
  CHAT_ATTACHMENT_ACCEPT,
  isSupportedChatAttachment,
} from "@/app/lib/api/chat-files";
import { formatLocaleNumber } from "@/app/lib/i18n";
import type { ChatFileListItem, QueryChoice } from "@/app/lib/api/types";
import type {
  ChatAttachmentItem,
  ChatInterrupt,
} from "@/app/hooks/use-chat-stream";

interface LocalUploadItem {
  key: string;
  file: File;
  previewUrl?: string;
}

export interface ChatComposerPayload {
  prompt: string;
  localFiles: File[];
  fileIds: string[];
  draftAttachments: ChatAttachmentItem[];
}

interface ChatInputProps {
  onSend: (payload: ChatComposerPayload, onAccepted: () => void) => void;
  onStop: () => void;
  onRetry: () => void;
  isStreaming: boolean;
  isInterrupted: boolean;
  disabled: boolean;
  noticeMessage?: string | null;
  interrupt: ChatInterrupt | null;
  onAnswerQuery: (choice: QueryChoice, note?: string | null) => void;
}

export default function ChatInput({
  onSend,
  onStop,
  onRetry,
  isStreaming,
  isInterrupted,
  disabled,
  noticeMessage = null,
  interrupt,
  onAnswerQuery,
}: ChatInputProps) {
  const { addToast } = useToast();
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [pickerQuery, setPickerQuery] = useState("");
  const [libraryFiles, setLibraryFiles] = useState<ChatFileListItem[]>([]);
  const [selectedLibraryFiles, setSelectedLibraryFiles] = useState<ChatFileListItem[]>([]);
  const [localUploads, setLocalUploads] = useState<LocalUploadItem[]>([]);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachmentMenuRef = useRef<HTMLDivElement>(null);
  const uploadIdRef = useRef(0);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [input]);

  useEffect(() => {
    if (!attachmentMenuOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!attachmentMenuRef.current?.contains(event.target as Node)) {
        setAttachmentMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAttachmentMenuOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [attachmentMenuOpen]);

  const buildDraftAttachments = (): ChatAttachmentItem[] => [
    ...selectedLibraryFiles.map((file) => ({
      fileId: file.id,
      originalFilename: file.original_filename,
      mediaType: file.media_type,
      injectionMode: null,
      pending: false,
      rawUrl: chatFilesApi.rawUrl(file.id),
      sizeBytes: file.size_bytes,
    })),
    ...localUploads.map((item) => ({
      fileId: null,
      originalFilename: item.file.name,
      mediaType: item.file.type || null,
      injectionMode: null,
      pending: true,
      previewUrl: item.previewUrl,
      sizeBytes: item.file.size,
    })),
  ];

  const resetDraft = () => {
    setInput("");
    setSelectedLibraryFiles([]);
    setLocalUploads([]);
    setAttachmentMenuOpen(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSend = () => {
    const trimmed = input.trim();
    if (
      (!trimmed && localUploads.length === 0 && selectedLibraryFiles.length === 0) ||
      disabled
    ) {
      return;
    }
    onSend(
      {
        prompt: trimmed,
        localFiles: localUploads.map((item) => item.file),
        fileIds: selectedLibraryFiles.map((file) => file.id),
        draftAttachments: buildDraftAttachments(),
      },
      resetDraft
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const loadLibraryFiles = async () => {
    setPickerLoading(true);
    setPickerError(null);
    try {
      const data = await chatFilesApi.list();
      setLibraryFiles(data);
    } catch (error: unknown) {
      setPickerError(error instanceof Error ? error.message : t("errors.loadLibraryFailed"));
    } finally {
      setPickerLoading(false);
    }
  };

  const openPicker = async () => {
    setAttachmentMenuOpen(false);
    setPickerOpen(true);
    await loadLibraryFiles();
  };

  const openLocalFileDialog = () => {
    setAttachmentMenuOpen(false);
    fileInputRef.current?.click();
  };

  const handleFileSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const pickedFiles = Array.from(event.target.files ?? []);
    const supported: LocalUploadItem[] = [];

    for (const file of pickedFiles) {
      if (!isSupportedChatAttachment(file)) {
        addToast(t("errors.unsupportedAttachment", { name: file.name }), "warning");
        continue;
      }
      uploadIdRef.current += 1;
      supported.push({
        key: `upload-${uploadIdRef.current}`,
        file,
        previewUrl: isAttachmentImage(file.name, file.type)
          ? URL.createObjectURL(file)
          : undefined,
      });
    }

    if (supported.length > 0) {
      setLocalUploads((prev) => [...prev, ...supported]);
    }

    event.target.value = "";
  };

  const removeLibraryFile = (fileId: string) => {
    setSelectedLibraryFiles((prev) => prev.filter((item) => item.id !== fileId));
  };

  const removeLocalUpload = (uploadKey: string) => {
    setLocalUploads((prev) => {
      const target = prev.find((upload) => upload.key === uploadKey);
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((upload) => upload.key !== uploadKey);
    });
  };

  const filteredLibraryFiles = libraryFiles.filter((file) => {
    const query = pickerQuery.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return (
      file.id.toLowerCase().includes(query) ||
      file.original_filename.toLowerCase().includes(query)
    );
  });

  const selectedLibraryIds = new Set(selectedLibraryFiles.map((file) => file.id));
  const hasDraftAttachments =
    selectedLibraryFiles.length > 0 || localUploads.length > 0;
  const queryInterrupt = interrupt?.type === "query" ? interrupt : null;
  const canSend =
    Boolean(input.trim() || hasDraftAttachments) && !disabled && !queryInterrupt;

  return (
    <div className="shrink-0 bg-gradient-to-t from-white via-white to-white/75 px-4 pb-5 pt-3 sm:px-6">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={CHAT_ATTACHMENT_ACCEPT}
        className="hidden"
        onChange={handleFileSelection}
      />

      <div className="mx-auto w-full max-w-3xl">
        {(selectedLibraryFiles.length > 0 || localUploads.length > 0) && (
          <div className="mb-2 flex flex-wrap gap-2">
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
                onRemove={() => removeLibraryFile(file.id)}
              />
            ))}
            {localUploads.map((item) => (
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
                onRemove={() => removeLocalUpload(item.key)}
              />
            ))}
          </div>
        )}

        {queryInterrupt ? (
          <QueryDecisionComposer
            key={queryInterrupt.interruptId || "query-interrupt"}
            interrupt={queryInterrupt}
            onAnswer={onAnswerQuery}
          />
        ) : (
          <div className="rounded-3xl bg-white p-2 shadow-[0_14px_40px_rgba(15,23,42,0.12)] transition-shadow focus-within:shadow-[0_0_0_2px_rgba(20,86,240,0.15),0_14px_40px_rgba(44,30,116,0.16)]">
            <div className="flex items-end gap-3 rounded-[1.25rem] bg-surface-secondary/80 p-2 pl-4">
              <div ref={attachmentMenuRef} className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setAttachmentMenuOpen((open) => !open)}
                  disabled={disabled || isStreaming}
                  className="rounded-full bg-white p-2 text-text-secondary shadow-sm transition hover:text-text-primary disabled:opacity-40"
                  title={t("chat.addAttachment")}
                  aria-label={t("chat.addAttachment")}
                  aria-expanded={attachmentMenuOpen}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v14m7-7H5" />
                  </svg>
                </button>

                {attachmentMenuOpen && (
                  <div className="absolute bottom-[calc(100%+0.5rem)] left-0 z-40 w-48 overflow-hidden rounded-2xl border border-border-light bg-white p-1.5 shadow-[0_18px_50px_rgba(15,23,42,0.18)]">
                    <button
                      type="button"
                      onClick={openLocalFileDialog}
                      className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-text-primary transition hover:bg-surface-secondary"
                    >
                      <svg className="h-4 w-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 16V4m0 0l-4 4m4-4l4 4M4 16.5A2.5 2.5 0 006.5 19h11a2.5 2.5 0 002.5-2.5" />
                      </svg>
                      <span>{t("chat.uploadFile")}</span>
                    </button>
                    <button
                      type="button"
                      onClick={openPicker}
                      className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-text-primary transition hover:bg-surface-secondary"
                    >
                      <svg className="h-4 w-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V7z" />
                      </svg>
                      <span>{t("chat.chooseFromLibrary")}</span>
                    </button>
                  </div>
                )}
              </div>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  disabled
                    ? t("chat.configureModel")
                    : t("chat.promptPlaceholder")
                }
                disabled={disabled}
                rows={1}
                className="flex-1 resize-none bg-transparent py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none disabled:text-text-muted/50"
              />
              <div className="flex items-center gap-1.5">
                {isStreaming ? (
                  <Button variant="danger" size="sm" onClick={onStop} pill>
                    {t("chat.stop")}
                  </Button>
                ) : isInterrupted ? (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={onRetry}
                    pill
                  >
                    {t("chat.retry")}
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSend}
                    disabled={!canSend}
                    pill
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}
        <p className="mt-2 text-center text-[11px] text-text-muted">
          {queryInterrupt
            ? t("chat.enterSubmit")
            : noticeMessage
              ? noticeMessage
              : t("chat.shiftEnterSubmit")}
        </p>
      </div>

      {pickerOpen && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/20 backdrop-blur-sm"
            onClick={() => setPickerOpen(false)}
          />
          <div className="relative flex max-h-[80vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-[0_24px_70px_rgba(15,23,42,0.24)]">
            <div className="flex items-center justify-between border-b border-border-light px-5 py-4">
              <div>
                <h3 className="font-display text-lg font-semibold text-text-primary">
                  {t("chat.chooseLibraryAttachment")}
                </h3>
                <p className="text-xs text-text-muted">
                  {t("chat.reuseUploadedFiles")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPickerOpen(false)}
                className="rounded-lg p-1.5 text-text-muted transition hover:bg-surface-secondary hover:text-text-primary"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="border-b border-border-light px-5 py-4">
              <input
                value={pickerQuery}
                onChange={(event) => setPickerQuery(event.target.value)}
                placeholder={t("files.searchPlaceholder")}
                className="h-10 w-full rounded-xl bg-surface-secondary px-3 text-sm text-text-primary outline-none transition focus:bg-white focus:ring-2 focus:ring-primary-500/25"
              />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {pickerLoading ? (
                <p className="py-8 text-center text-sm text-text-muted">{t("chat.loadingLibrary")}</p>
              ) : pickerError ? (
                <div className="py-8 text-center">
                  <p className="mb-3 text-sm text-error-text">{pickerError}</p>
                  <Button variant="secondary" size="sm" onClick={loadLibraryFiles}>
                    {t("chat.retry")}
                  </Button>
                </div>
              ) : filteredLibraryFiles.length === 0 ? (
                <p className="py-8 text-center text-sm text-text-muted">{t("chat.noAvailableFiles")}</p>
              ) : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {filteredLibraryFiles.map((file) => {
                    const selected = selectedLibraryIds.has(file.id);
                    return (
                      <ChatAttachmentCard
                        key={file.id}
                        onClick={() =>
                          setSelectedLibraryFiles((prev) =>
                            selected
                              ? prev.filter((item) => item.id !== file.id)
                              : [...prev, file]
                          )
                        }
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
                {t("chat.selectedFiles", {
                  count: formatLocaleNumber(selectedLibraryFiles.length),
                })}
              </span>
              <Button variant="primary" size="sm" onClick={() => setPickerOpen(false)}>
                {t("common.done")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function QueryDecisionComposer({
  interrupt,
  onAnswer,
}: {
  interrupt: ChatInterrupt;
  onAnswer: (choice: QueryChoice, note?: string | null) => void;
}) {
  const [selectedChoice, setSelectedChoice] = useState<QueryChoice | null>(null);
  const [note, setNote] = useState("");
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const { t } = useTranslation();
  const choices: {
    key: QueryChoice;
    label: string;
    description: string;
    recommended?: boolean;
  }[] = [
    {
      key: "firstChoice",
      label: interrupt.firstChoice || t("chat.queryOptionOne"),
      description:
        interrupt.firstChoiceDescription || t("chat.queryDefaultDescription"),
      recommended: true,
    },
    {
      key: "secondChoice",
      label: interrupt.secondChoice || t("chat.queryOptionTwo"),
      description: interrupt.secondChoiceDescription || t("chat.querySecondDescription"),
    },
    {
      key: "thirdChoice",
      label: interrupt.thirdChoice || t("chat.queryOptionThree"),
      description: interrupt.thirdChoiceDescription || t("chat.queryThirdDescription"),
    },
    {
      key: "other",
      label: t("chat.queryOther"),
      description: t("chat.queryOtherDescription"),
    },
  ];
  const trimmedNote = note.trim();
  const resolvedChoice = selectedChoice ?? (trimmedNote ? "other" : null);
  const canSubmit = Boolean(resolvedChoice);

  const submit = () => {
    if (!resolvedChoice) {
      noteRef.current?.focus();
      return;
    }
    onAnswer(resolvedChoice, trimmedNote || null);
  };

  const handleNoteKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setNote("");
    }
  };

  return (
    <div className="rounded-[1.45rem] border border-border-light bg-white px-4 py-3.5 text-text-primary shadow-[0_0_22px_rgba(44,30,116,0.16)] sm:px-5">
      <p className="mb-3 text-sm font-semibold leading-snug sm:text-base">
        {interrupt.question || t("chat.queryQuestion")}
      </p>
      <div className="space-y-1.5">
        {choices.map((choice, index) => {
          const selected = selectedChoice === choice.key;
          const displayLabel = choice.recommended
            ? `${choice.label} (${t("common.recommended")})`
            : choice.label;
          return (
            <div
              key={choice.key}
              className={`flex min-h-11 items-center gap-2 rounded-2xl border px-2.5 py-1.5 transition ${
                selected
                  ? "border-primary-500/45 bg-primary-200/45 shadow-[0_0_0_1px_rgba(20,86,240,0.08)]"
                  : "border-transparent bg-surface-secondary/70 hover:border-border-light hover:bg-white"
              }`}
            >
              <button
                type="button"
                onClick={() => setSelectedChoice(choice.key)}
                className="flex min-w-0 flex-1 items-center gap-3 rounded-xl text-left outline-none focus-visible:ring-2 focus-visible:ring-primary-500/25"
                aria-pressed={selected}
              >
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                    selected
                      ? "bg-primary-500 text-white"
                      : "border border-border-light bg-white text-text-muted"
                  }`}
                >
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold text-text-primary">
                  {displayLabel}
                </span>
              </button>
              <InfoTooltip description={choice.description} label={choice.label} />
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex flex-col gap-2.5 sm:flex-row sm:items-end">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span className="mt-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border-light bg-surface-secondary text-text-muted">
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.862 4.487l1.688-1.688a1.875 1.875 0 112.652 2.652L9.38 17.273 4 18.5l1.227-5.38L16.862 4.487z" />
            </svg>
          </span>
          <textarea
            ref={noteRef}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            onKeyDown={handleNoteKeyDown}
            rows={1}
            placeholder={t("chat.queryNotePlaceholder")}
            className="min-h-9 flex-1 resize-none bg-transparent py-2 text-sm text-text-primary outline-none placeholder:text-text-muted"
          />
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={!canSubmit}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-full bg-[#181e25] px-5 text-sm font-semibold text-white transition hover:bg-[#222b35] disabled:cursor-not-allowed disabled:bg-surface-secondary disabled:text-text-muted"
        >
          {t("chat.submit")}
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}

function InfoTooltip({
  description,
  label,
}: {
  description: string;
  label: string;
}) {
  const { t } = useTranslation();

  return (
    <span className="group relative shrink-0">
      <button
        type="button"
        title={description}
        aria-label={t("chat.optionDescription", { label, description })}
        className="flex h-8 w-8 items-center justify-center rounded-full text-text-muted transition hover:bg-white hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/25"
      >
        <svg
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 16v-4m0-4h.01" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 21a9 9 0 100-18 9 9 0 000 18z" />
        </svg>
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-[calc(100%+0.45rem)] right-0 z-30 hidden w-64 rounded-xl border border-border-light bg-white px-3 py-2 text-xs leading-relaxed text-text-secondary shadow-[0_12px_30px_rgba(15,23,42,0.16)] group-hover:block group-focus-within:block"
      >
        {description}
      </span>
    </span>
  );
}
