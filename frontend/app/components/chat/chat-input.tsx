import { ArrowUp, FolderOpen, Plus, Square, Upload } from "lucide-react";
import { useState, useRef, useEffect, useLayoutEffect, useCallback, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import FormDrawer from "@/app/components/ui/form-drawer";
import { useMediaQuery } from "@/app/hooks/use-media-query";
import { useDismiss } from "@/app/hooks/use-dismiss";
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

import type {
  ChatFileListItem,
} from "@/app/lib/api/types";
import type { ChatAttachmentItem } from "@/app/lib/chat/types";

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
  isStreaming: boolean;
  disabled: boolean;
  disabledMessage?: string;
  submitting?: boolean;
  noticeMessage?: string | null;
  /** Controls rendered before the send button, e.g. the thinking intensity picker. */
  trailing?: ReactNode;
  /** Changing this value clears the draft and attachments and focuses the input (new chat). */
  resetSignal?: number;
}

/** Textarea height (40px) plus slack; anything taller means the draft wrapped. */
const SINGLE_LINE_MAX_HEIGHT = 44;
const TEXTAREA_MAX_HEIGHT = 200;

export default function ChatInput({
  onSend,
  onStop,
  isStreaming,
  disabled,
  disabledMessage,
  submitting = false,
  noticeMessage = null,
  trailing,
  resetSignal = 0,
}: ChatInputProps) {
  const hasTouchInput = useMediaQuery("(pointer: coarse) and (hover: none)");
  const touchShortcuts = hasTouchInput && !window.offerPilotRuntime?.platform;
  const { addToast } = useToast();
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [pickerQuery, setPickerQuery] = useState("");
  const [libraryFiles, setLibraryFiles] = useState<ChatFileListItem[]>([]);
  const [selectedLibraryFiles, setSelectedLibraryFiles] = useState<
    ChatFileListItem[]
  >([]);
  const [localUploads, setLocalUploads] = useState<LocalUploadItem[]>([]);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [wrapped, setWrapped] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachmentMenuRef = useRef<HTMLDivElement>(null);
  const uploadIdRef = useRef(0);
  const lastResetSignal = useRef(resetSignal);
  const hasDraftAttachments =
    selectedLibraryFiles.length > 0 || localUploads.length > 0;

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const height = Math.min(textarea.scrollHeight, TEXTAREA_MAX_HEIGHT);
    textarea.style.height = `${height}px`;
    // Once a draft wraps it keeps the two-row layout until cleared, so the width change cannot flip it back and forth.
    setWrapped((current) => (textarea.value ? current || height > SINGLE_LINE_MAX_HEIGHT : false));
  }, []);

  useLayoutEffect(() => {
    resizeTextarea();
  }, [input, hasDraftAttachments, resizeTextarea]);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", resizeTextarea);
      return () => window.removeEventListener("resize", resizeTextarea);
    }
    let previousWidth: number | undefined;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry || entry.contentRect.width === previousWidth) return;
      previousWidth = entry.contentRect.width;
      resizeTextarea();
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [resizeTextarea]);

  useDismiss(attachmentMenuRef, attachmentMenuOpen, () => setAttachmentMenuOpen(false));

  useEffect(() => {
    if (resetSignal === lastResetSignal.current) return;
    lastResetSignal.current = resetSignal;
    setInput("");
    setSelectedLibraryFiles([]);
    setLocalUploads((current) => {
      current.forEach((item) => item.previewUrl && URL.revokeObjectURL(item.previewUrl));
      return [];
    });
    setAttachmentMenuOpen(false);
    textareaRef.current?.focus();
  }, [resetSignal]);

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

  const handleSend = () => {
    const trimmed = input.trim();
    if (
      (!trimmed &&
        localUploads.length === 0 &&
        selectedLibraryFiles.length === 0) ||
      disabled ||
      submitting
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
      () => {
        setInput((current) => (current === input ? "" : current));
        const sentIds = new Set(selectedLibraryFiles.map((file) => file.id));
        const sentKeys = new Set(localUploads.map((item) => item.key));
        setSelectedLibraryFiles((current) =>
          current.filter((file) => !sentIds.has(file.id)),
        );
        setLocalUploads((current) =>
          current.filter((item) => !sentKeys.has(item.key)),
        );
      },
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (
      e.key === "Enter" &&
      !e.nativeEvent.isComposing &&
      e.keyCode !== 229 &&
      !e.shiftKey &&
      (!touchShortcuts || e.ctrlKey || e.metaKey)
    ) {
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
      setPickerError(
        error instanceof Error ? error.message : t("errors.loadLibraryFailed"),
      );
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
        addToast(
          t("errors.unsupportedAttachment", { name: file.name }),
          "warning",
        );
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
    setSelectedLibraryFiles((prev) =>
      prev.filter((item) => item.id !== fileId),
    );
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

  const selectedLibraryIds = new Set(
    selectedLibraryFiles.map((file) => file.id),
  );
  const canSend =
    Boolean(input.trim() || hasDraftAttachments) && !disabled && !submitting;

  const multiline = wrapped || hasDraftAttachments || input.includes("\n");

  return (
    <div className="chat-composer shrink-0 px-4 pb-4 pt-3 sm:px-6">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={CHAT_ATTACHMENT_ACCEPT}
        className="hidden"
        onChange={handleFileSelection}
      />

      <div className="mx-auto w-full max-w-3xl">
        <div className={`composer-surface ${multiline ? "is-multiline" : ""}`}>
          {hasDraftAttachments && (
            <div className="composer-attachments">
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

          <div className="composer-row">
            <div ref={attachmentMenuRef} className="composer-leading">
              <button
                type="button"
                onClick={() => setAttachmentMenuOpen((open) => !open)}
                disabled={disabled}
                className="composer-icon-button"
                title={t("chat.addAttachment")}
                aria-label={t("chat.addAttachment")}
                aria-haspopup="menu"
                aria-expanded={attachmentMenuOpen}
              >
                <Plus size={20} strokeWidth={1.8} aria-hidden="true" />
              </button>

              {attachmentMenuOpen && (
                <div role="menu" className="select-menu absolute bottom-[calc(100%+0.5rem)] left-0 z-40 w-52 rounded-xl border border-border-light bg-surface-primary p-1 shadow-elevated">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={openLocalFileDialog}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-text-primary transition hover:bg-surface-secondary"
                  >
                    <Upload size={16} className="text-text-muted" aria-hidden="true" />
                    <span>{t("chat.uploadFile")}</span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={openPicker}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-text-primary transition hover:bg-surface-secondary"
                  >
                    <FolderOpen size={16} className="text-text-muted" aria-hidden="true" />
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
                  ? disabledMessage ?? t("chat.configureModel")
                  : t("chat.promptPlaceholder")
              }
              disabled={disabled}
              rows={1}
              aria-label={t("chat.promptPlaceholder")}
              className="composer-text disabled:opacity-60"
            />

            <div className="composer-trailing">
              {trailing}
              {isStreaming && (
                <button
                  type="button"
                  onClick={onStop}
                  className="composer-icon-button"
                  aria-label={t("chatRuns.stopCurrent")}
                  title={t("chatRuns.stopCurrent")}
                >
                  <Square size={14} fill="currentColor" aria-hidden="true" />
                </button>
              )}
              <button
                type="button"
                onClick={handleSend}
                disabled={!canSend}
                className="composer-send"
                aria-label={t(isStreaming ? "chatRuns.enqueue" : "chatRuns.send")}
                title={t(isStreaming ? "chatRuns.enqueue" : "chatRuns.send")}
              >
                <ArrowUp size={18} strokeWidth={2.2} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
        <p className="composer-hint">
          {noticeMessage ?? t(touchShortcuts ? "appearance.mobileKeyboard" : "appearance.keyboard")}
        </p>
      </div>

      <FormDrawer
        open={pickerOpen}
        title={t("chat.chooseLibraryAttachment")}
        onClose={() => setPickerOpen(false)}
        toolbar={
          <input
            type="search"
            value={pickerQuery}
            onChange={(event) => setPickerQuery(event.target.value)}
            aria-label={t("files.searchPlaceholder")}
            placeholder={t("files.searchPlaceholder")}
            className="h-9 w-full rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-text-primary outline-none transition"
          />
        }
        footer={
          <>
            <span className="text-xs text-text-muted">
              {t("chat.selectedFiles", {
                count: selectedLibraryFiles.length,
              })}
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setPickerOpen(false)}
            >
              {t("common.done")}
            </Button>
          </>
        }
      >
        {pickerLoading ? (
          <p className="py-8 text-center text-sm text-text-muted">
            {t("chat.loadingLibrary")}
          </p>
        ) : pickerError ? (
          <div className="py-8 text-center">
            <p className="mb-3 text-sm text-error-text">{pickerError}</p>
            <Button
              variant="secondary"
              size="sm"
              onClick={loadLibraryFiles}
            >
              {t("chat.retry")}
            </Button>
          </div>
        ) : filteredLibraryFiles.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">
            {t("chat.noAvailableFiles")}
          </p>
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
                        : [...prev, file],
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
      </FormDrawer>
    </div>
  );
}
