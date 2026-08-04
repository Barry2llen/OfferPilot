import { useState } from "react";

export interface ChatAttachmentDisplayItem {
  fileId?: string | null;
  originalFilename: string;
  mediaType?: string | null;
  injectionMode?: string | null;
  pending?: boolean;
  rawUrl?: string;
  previewUrl?: string;
  sizeBytes?: number;
  referenceCount?: number;
  createdAt?: string;
}

type AttachmentKind =
  | "image"
  | "pdf"
  | "word"
  | "code"
  | "text"
  | "table"
  | "archive"
  | "file";

type AttachmentCardVariant = "composer" | "message" | "grid" | "picker";

interface ChatAttachmentCardProps {
  attachment: ChatAttachmentDisplayItem;
  variant?: AttachmentCardVariant;
  selected?: boolean;
  onClick?: () => void;
  onRemove?: () => void;
  className?: string;
}

const CODE_EXTENSIONS = new Set([
  "js",
  "ts",
  "tsx",
  "jsx",
  "py",
  "java",
  "go",
  "rs",
  "sh",
  "sql",
  "html",
  "htm",
  "xml",
  "css",
  "json",
]);

const TEXT_EXTENSIONS = new Set([
  "txt",
  "md",
  "log",
  "ini",
  "conf",
  "yaml",
  "yml",
]);

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "gif", "bmp"]);

const TABLE_EXTENSIONS = new Set(["csv", "tsv", "xlsx", "xls"]);

const ARCHIVE_EXTENSIONS = new Set(["zip", "7z", "rar", "tar", "gz"]);

const KIND_STYLES: Record<AttachmentKind, { label: string; className: string }> = {
  image: { label: "IMG", className: "bg-info-bg text-info-text" },
  pdf: { label: "PDF", className: "bg-error-bg text-error-text" },
  word: { label: "DOC", className: "bg-info-bg text-info-text" },
  code: { label: "CODE", className: "bg-text-charcoal text-white" },
  text: { label: "TXT", className: "bg-surface-secondary text-text-secondary" },
  table: { label: "CSV", className: "bg-success-bg text-success-text" },
  archive: { label: "ZIP", className: "bg-warning-bg text-warning-text" },
  file: { label: "FILE", className: "bg-surface-secondary text-text-secondary" },
};

export function isAttachmentImage(
  filename: string,
  mediaType?: string | null
): boolean {
  if (mediaType?.toLowerCase().startsWith("image/")) {
    return true;
  }
  return IMAGE_EXTENSIONS.has(getExtension(filename));
}

export function getAttachmentKind(
  filename: string,
  mediaType?: string | null
): AttachmentKind {
  const normalizedMediaType = mediaType?.toLowerCase() ?? "";
  const extension = getExtension(filename);

  if (isAttachmentImage(filename, mediaType)) {
    return "image";
  }
  if (normalizedMediaType === "application/pdf" || extension === "pdf") {
    return "pdf";
  }
  if (
    normalizedMediaType.includes("word") ||
    normalizedMediaType.includes("officedocument.wordprocessingml") ||
    extension === "docx"
  ) {
    return "word";
  }
  if (TABLE_EXTENSIONS.has(extension) || normalizedMediaType.includes("csv")) {
    return "table";
  }
  if (CODE_EXTENSIONS.has(extension)) {
    return "code";
  }
  if (TEXT_EXTENSIONS.has(extension) || normalizedMediaType.startsWith("text/")) {
    return "text";
  }
  if (ARCHIVE_EXTENSIONS.has(extension)) {
    return "archive";
  }
  return "file";
}

export function formatFileSize(sizeBytes?: number): string | null {
  if (typeof sizeBytes !== "number" || !Number.isFinite(sizeBytes)) {
    return null;
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatInjectionMode(mode?: string | null): string | null {
  switch (mode) {
    case "image":
      return "图片";
    case "ocr_text":
      return "OCR";
    case "text":
      return "文本";
    case undefined:
    case null:
    case "":
      return null;
    default:
      return mode;
  }
}

export default function ChatAttachmentCard({
  attachment,
  variant = "composer",
  selected = false,
  onClick,
  onRemove,
  className = "",
}: ChatAttachmentCardProps) {
  const clickable = Boolean(onClick);
  const content = (
    <>
      {variant === "grid" || variant === "picker" ? (
        <GridContent attachment={attachment} selected={selected} />
      ) : (
        <RowContent attachment={attachment} variant={variant} />
      )}

      {variant === "message" && attachment.pending && (
        <span className="absolute right-2 top-2 rounded-full bg-primary-500 px-2 py-0.5 text-[10px] font-semibold text-white shadow-sm">
          处理中
        </span>
      )}

      {onRemove && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onRemove();
          }}
          className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-white/95 text-text-muted shadow-sm transition hover:text-error-text"
          aria-label={`移除 ${attachment.originalFilename}`}
          title="移除附件"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </>
  );

  const rootClassName = [
    "relative overflow-hidden border text-left transition",
    variant === "grid" || variant === "picker"
      ? "h-full rounded-xl bg-white"
      : "rounded-2xl bg-white",
    variant === "message" ? "chat-message-enter" : "",
    selected
      ? "border-text-charcoal shadow-[0_0_0_2px_rgba(24,30,37,0.10)]"
      : "border-border-light shadow-sm",
    variant === "message" && attachment.pending
      ? "chat-attachment-pending border-primary-200"
      : "",
    clickable ? "cursor-pointer hover:border-text-muted hover:shadow-card" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  if (clickable) {
    return (
      <button type="button" onClick={onClick} className={rootClassName}>
        {content}
      </button>
    );
  }

  return <div className={rootClassName}>{content}</div>;
}

function RowContent({
  attachment,
  variant,
}: {
  attachment: ChatAttachmentDisplayItem;
  variant: AttachmentCardVariant;
}) {
  const sizeLabel = formatFileSize(attachment.sizeBytes);
  const modeLabel = formatInjectionMode(attachment.injectionMode);
  const statusLabel = attachment.pending
    ? variant === "message"
      ? "处理中"
      : "待上传"
    : attachment.fileId
      ? attachment.fileId
      : "未入库";

  return (
    <div className="flex min-h-20 w-full max-w-[18rem] items-center gap-3 p-2.5 pr-8">
      <AttachmentPreview attachment={attachment} className="h-14 w-14 rounded-xl" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-text-primary" title={attachment.originalFilename}>
          {attachment.originalFilename}
        </p>
        <p className="mt-1 truncate text-xs text-text-muted">
          {[statusLabel, modeLabel, sizeLabel].filter(Boolean).join(" · ")}
        </p>
      </div>
    </div>
  );
}

function GridContent({
  attachment,
  selected,
}: {
  attachment: ChatAttachmentDisplayItem;
  selected: boolean;
}) {
  const sizeLabel = formatFileSize(attachment.sizeBytes);
  const createdAtLabel = attachment.createdAt
    ? new Date(attachment.createdAt).toLocaleDateString("zh-CN")
    : null;
  const meta = [
    attachment.fileId,
    sizeLabel,
    typeof attachment.referenceCount === "number"
      ? `${attachment.referenceCount} 个引用`
      : null,
    createdAtLabel,
  ].filter(Boolean);

  return (
    <div className="flex h-full min-h-60 flex-col">
      <AttachmentPreview
        attachment={attachment}
        className="aspect-[4/3] w-full rounded-none"
        large
      />
      <div className="flex min-h-28 min-w-0 flex-1 flex-col p-3">
        <p className="line-clamp-2 text-sm font-semibold text-text-primary" title={attachment.originalFilename}>
          {attachment.originalFilename}
        </p>
        {meta.length > 0 && (
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-text-muted">
            {meta.join(" · ")}
          </p>
        )}
      </div>
      {selected && (
        <span className="absolute right-2 top-2 rounded-full bg-text-charcoal px-2 py-1 text-[11px] font-semibold text-white shadow-sm">
          已选
        </span>
      )}
    </div>
  );
}

function AttachmentPreview({
  attachment,
  className,
  large = false,
}: {
  attachment: ChatAttachmentDisplayItem;
  className: string;
  large?: boolean;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const kind = getAttachmentKind(attachment.originalFilename, attachment.mediaType);
  const imageSrc = kind === "image" ? attachment.previewUrl || attachment.rawUrl : null;

  if (imageSrc && !imageFailed) {
    return (
      <img
        src={imageSrc}
        alt={attachment.originalFilename}
        className={`${className} shrink-0 bg-surface-secondary object-contain`}
        onError={() => setImageFailed(true)}
      />
    );
  }

  const style = KIND_STYLES[kind];
  return (
    <div
      className={`${className} flex shrink-0 flex-col items-center justify-center gap-1 ${style.className}`}
      aria-label={style.label}
    >
      <FileIcon kind={kind} className={large ? "h-8 w-8" : "h-5 w-5"} />
      <span className={large ? "text-xs font-bold" : "text-[10px] font-bold"}>
        {style.label}
      </span>
    </div>
  );
}

function FileIcon({
  kind,
  className,
}: {
  kind: AttachmentKind;
  className: string;
}) {
  if (kind === "image") {
    return (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.5-4.5a2 2 0 012.8 0L16 16m-2-2l1.5-1.5a2 2 0 012.8 0L20 14m-14 6h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2zm3-11h.01" />
      </svg>
    );
  }

  if (kind === "code") {
    return (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l-3 3 3 3m8-6l3 3-3 3M13 5l-2 14" />
      </svg>
    );
  }

  if (kind === "table") {
    return (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16M8 6v12m8-12v12" />
      </svg>
    );
  }

  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 3h7l5 5v13H7a2 2 0 01-2-2V5a2 2 0 012-2zm7 0v5h5" />
    </svg>
  );
}

function getExtension(filename: string): string {
  const parts = filename.toLowerCase().split(".");
  return parts.length > 1 ? parts.at(-1) ?? "" : "";
}
