import { Paperclip } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import FormDrawer from "@/app/components/ui/form-drawer";
import { useMediaQuery } from "@/app/hooks/use-media-query";
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
}

export default function ChatInput({
  onSend,
  onStop,
  isStreaming,
  disabled,
  disabledMessage,
  submitting = false,
  noticeMessage = null,
}: ChatInputProps) {
  const mobile = useMediaQuery("(max-width: 767px)");
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
    if (e.key === "Enter" && !e.nativeEvent.isComposing && e.keyCode !== 229 && !e.shiftKey && (!mobile || e.ctrlKey || e.metaKey)) {
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
  const hasDraftAttachments =
    selectedLibraryFiles.length > 0 || localUploads.length > 0;
  const canSend =
    Boolean(input.trim() || hasDraftAttachments) && !disabled && !submitting;

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

        <div className="composer-surface">
          <div className="composer-grid">
            <div ref={attachmentMenuRef} className="relative shrink-0">
              <button
                type="button"
                onClick={() => setAttachmentMenuOpen((open) => !open)}
                disabled={disabled}
                className="inline-flex items-center gap-2 rounded-lg border border-border-default bg-surface-primary p-2 text-text-secondary shadow-sm transition hover:text-text-primary disabled:opacity-40"
                title={t("chat.addAttachment")}
                aria-label={t("chat.addAttachment")}
                aria-expanded={attachmentMenuOpen}
              >
                <Paperclip size={18} /><span className="hidden sm:inline">{t("chat.addAttachment")}</span>
              </button>

              {attachmentMenuOpen && (
                <div className="absolute bottom-[calc(100%+0.5rem)] left-0 z-40 w-48 overflow-hidden rounded-2xl border border-border-light bg-surface-primary p-1.5 shadow-[0_18px_50px_rgba(15,23,42,0.18)]">
                  <button
                    type="button"
                    onClick={openLocalFileDialog}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-text-primary transition hover:bg-surface-secondary"
                  >
                    <svg
                      className="h-4 w-4 text-text-muted"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 16V4m0 0l-4 4m4-4l4 4M4 16.5A2.5 2.5 0 006.5 19h11a2.5 2.5 0 002.5-2.5"
                      />
                    </svg>
                    <span>{t("chat.uploadFile")}</span>
                  </button>
                  <button
                    type="button"
                    onClick={openPicker}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-text-primary transition hover:bg-surface-secondary"
                  >
                    <svg
                      className="h-4 w-4 text-text-muted"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 7a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V7z"
                      />
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
                  ? disabledMessage ?? t("chat.configureModel")
                  : t("chat.promptPlaceholder")
              }
              disabled={disabled}
              rows={1}
              aria-label={t("chat.promptPlaceholder")}
              className="composer-text resize-none bg-transparent py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none disabled:text-text-muted/50"
            />
            <div className="composer-actions flex items-center gap-1.5">
              {isStreaming && (
                <Button variant="secondary" size="sm" onClick={onStop} aria-label={t("chatRuns.stopCurrent")}>
                  {t("chat.stop")}
                </Button>
              )}
              <Button
                variant="primary"
                size="sm"
                onClick={handleSend}
                disabled={!canSend}
                pill
              >
                {t(isStreaming ? "chatRuns.enqueue" : "chatRuns.send")}
              </Button>
            </div>
          </div>
        </div>
        <p className="mt-2 text-center text-xs text-text-muted">
          {noticeMessage ?? t(mobile ? "appearance.mobileKeyboard" : "appearance.keyboard")}
        </p>
      </div>

      <FormDrawer open={pickerOpen} title={t("chat.chooseLibraryAttachment")} onClose={() => setPickerOpen(false)}>
            <div className="border-b border-border-light px-5 py-4">
              <input
                value={pickerQuery}
                onChange={(event) => setPickerQuery(event.target.value)}
                placeholder={t("files.searchPlaceholder")}
                className="h-10 w-full rounded-xl bg-surface-secondary px-3 text-sm text-text-primary outline-none transition focus:bg-surface-primary focus:ring-2 focus:ring-primary-500/25"
              />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
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
            </div>

            <div className="flex items-center justify-between border-t border-border-light px-5 py-4">
              <span className="text-xs text-text-muted">
                {t("chat.selectedFiles", {
                  count: formatLocaleNumber(selectedLibraryFiles.length),
                })}
              </span>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setPickerOpen(false)}
              >
                {t("common.done")}
              </Button>
            </div>
      </FormDrawer>
    </div>
  );
}
