"use client";

import { useState, useCallback } from "react";
import { resumesApi } from "@/app/lib/api/resumes";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ResumeCard from "@/app/components/resumes/resume-card";
import ResumeUploader from "@/app/components/resumes/resume-uploader";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Button from "@/app/components/ui/button";
import { ResumeCardSkeleton, Skeleton } from "@/app/components/ui/skeleton";
import type { ResumeListItem } from "@/app/lib/api/types";

export default function ResumesPage() {
  const fetchResumes = useCallback(() => resumesApi.list(), []);
  const { data, loading, error, refetch } = useAsyncData(fetchResumes, [
    fetchResumes,
  ]);
  const { addToast } = useToast();

  const [deleting, setDeleting] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<ResumeListItem | null>(
    null
  );

  const handleUploaded = useCallback(() => {
    refetch();
  }, [refetch]);

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(confirmDelete.id);
    try {
      await resumesApi.delete(confirmDelete.id);
      addToast("简历已删除", "success");
      setConfirmDelete(null);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除失败";
      addToast(msg, "error");
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return (
      <div className="electron-titlebar-safe-top max-w-2xl mx-auto p-6 lg:py-8">
        <div className="mb-6">
          <Skeleton className="mb-2 h-8 w-24 rounded-lg" />
          <Skeleton className="h-4 w-48 rounded-lg" />
        </div>
        <Skeleton className="mb-6 h-48 rounded-[20px]" />
        <div className="space-y-3">
          {[1, 2, 3].map((item) => (
            <ResumeCardSkeleton key={item} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="electron-titlebar-safe-top max-w-2xl mx-auto p-6">
        <div className="text-center py-20">
          <p className="text-error-text text-sm mb-4">{error}</p>
          <Button variant="secondary" onClick={refetch}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="electron-titlebar-safe-top max-w-2xl mx-auto p-6 lg:py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-text-primary">
          简历库
        </h1>
        <p className="text-sm text-text-muted mt-1">
          上传和管理简历文件，查看解析结果与原始预览
        </p>
      </div>

      <div className="mb-6">
        <ResumeUploader onUploaded={handleUploaded} />
      </div>

      {data && data.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 px-4 text-center border-2 border-dashed border-border-default rounded-[20px] bg-surface-primary">
          <svg className="w-16 h-16 text-border-default mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-sm font-medium text-text-primary mb-1">暂无简历</p>
          <p className="text-xs text-text-muted">上传你的第一份简历，开始 AI 解析</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data?.map((r) => (
            <ResumeCard
              key={r.id}
              resume={r}
              onDelete={setConfirmDelete}
              deleting={deleting === r.id}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title="删除简历"
        message={`确定要删除「${confirmDelete?.original_filename || `简历 #${confirmDelete?.id}`}」吗？此操作会删除数据库记录和原始文件。`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
        loading={!!deleting}
      />
    </div>
  );
}
