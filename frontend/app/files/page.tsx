import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button, { buttonClassName } from "@/app/components/ui/button";
import ChatAttachmentCard from "@/app/components/chat/chat-attachment-card";
import { Skeleton } from "@/app/components/ui/skeleton";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { chatFilesApi } from "@/app/lib/api/chat-files";

export default function FilesPage() {
  const { t } = useTranslation();
  const fetchFiles = useCallback(() => chatFilesApi.list(), []);
  const { data, loading, error, refetch } = useAsyncData(fetchFiles, [fetchFiles]);
  const [query, setQuery] = useState("");

  const filteredFiles = useMemo(() => {
    if (!data) {
      return [];
    }
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return data;
    }
    return data.filter((file) =>
      [file.id, file.original_filename]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery)
    );
  }, [data, query]);

  if (loading) {
    return (
      <div className="electron-titlebar-safe-top mx-auto max-w-5xl p-6 lg:py-8">
        <div className="mb-6">
          <Skeleton className="mb-2 h-8 w-28 rounded-lg" />
          <Skeleton className="h-4 w-56 rounded-lg" />
        </div>
        <Skeleton className="mb-6 h-10 rounded-lg" />
        <div className="space-y-2">
          {[1, 2, 3, 4].map((item) => (
            <Skeleton key={item} className="h-[72px] rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="electron-titlebar-safe-top mx-auto max-w-5xl p-6">
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
    <div className="electron-titlebar-safe-top mx-auto max-w-5xl p-6 lg:py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-text-primary">
          {t("files.title")}
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          {t("files.description")}
        </p>
      </div>

      <div className="mb-6">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label={t("files.searchPlaceholder")}
          placeholder={t("files.searchPlaceholder")}
          className="h-10 w-full rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-text-primary outline-none transition focus:border-text-muted"
        />
      </div>

      {filteredFiles.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border-default bg-surface-primary px-4 py-14 text-center">
          <p className="text-sm font-medium text-text-primary">{t(query.trim() ? "appearance.noResults" : "files.noFiles")}</p>
          {!query.trim() && <p className="mt-1 text-xs text-text-muted">{t("files.noFilesDescription")}</p>}
        </div>
      ) : (
        <div className="file-library-list">
          {filteredFiles.map((file) => (
            <div
              key={file.id}
              className="file-library-row"
            >
              <ChatAttachmentCard
                attachment={{
                  fileId: file.id,
                  originalFilename: file.original_filename,
                  mediaType: file.media_type,
                  rawUrl: chatFilesApi.rawUrl(file.id),
                  sizeBytes: file.size_bytes,
                  referenceCount: file.reference_count,
                  createdAt: file.created_at,
                }}
                variant="list"
                className="file-library-item"
              />
              <div className="file-library-action">
                <a
                  href={chatFilesApi.rawUrl(file.id)}
                  target="_blank"
                  rel="noreferrer"
                  className={buttonClassName({
                    variant: "secondary",
                    size: "sm",
                    className: "w-full",
                  })}
                >
                  {t("files.openOriginal")}
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
