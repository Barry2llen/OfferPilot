"use client";

import { useCallback, useMemo, useState } from "react";
import Button, { buttonClassName } from "@/app/components/ui/button";
import ChatAttachmentCard from "@/app/components/chat/chat-attachment-card";
import { Skeleton } from "@/app/components/ui/skeleton";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { chatFilesApi } from "@/app/lib/api/chat-files";

export default function FilesPage() {
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
        <Skeleton className="mb-6 h-12 rounded-2xl" />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((item) => (
            <Skeleton key={item} className="h-60 rounded-xl" />
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
            重试
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="electron-titlebar-safe-top mx-auto max-w-5xl p-6 lg:py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-text-primary">
          文件库
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          查看聊天中上传过的附件，并在对话里复用历史文件
        </p>
      </div>

      <div className="mb-6">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索文件名或文件 ID"
          className="h-11 w-full rounded-2xl border border-border-light bg-white px-4 text-sm text-text-primary outline-none transition focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
        />
      </div>

      {filteredFiles.length === 0 ? (
        <div className="rounded-[20px] border-2 border-dashed border-border-default bg-surface-primary px-4 py-16 text-center">
          <p className="mb-1 text-sm font-medium text-text-primary">暂无聊天文件</p>
          <p className="text-xs text-text-muted">在 AI 对话里上传附件后，这里会显示文件记录</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 items-stretch gap-4 md:grid-cols-3 xl:grid-cols-4">
          {filteredFiles.map((file) => (
            <div
              key={file.id}
              className="group flex h-full min-h-72 flex-col overflow-hidden rounded-xl border border-border-light bg-white shadow-sm transition hover:border-text-muted hover:shadow-card"
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
                variant="grid"
                className="flex-1 border-0 shadow-none"
              />
              <div className="mt-auto border-t border-border-light p-3">
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
                  打开原文件
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
