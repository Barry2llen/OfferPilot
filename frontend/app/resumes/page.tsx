"use client";

import { useState, useCallback } from "react";
import { resumesApi } from "@/app/lib/api/resumes";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ResumeCard from "@/app/components/resumes/resume-card";
import ResumeUploader from "@/app/components/resumes/resume-uploader";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type { ResumeListItem } from "@/app/lib/api/types";

export default function ResumesPage() {
  const { data, loading, error, refetch } = useAsyncData(() =>
    resumesApi.list()
  );
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
      <div className="max-w-2xl mx-auto p-6">
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto p-6">
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
    <div className="max-w-2xl mx-auto p-6 lg:py-8">
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
        <div className="text-center py-16 border-2 border-dashed border-border-default rounded-[20px]">
          <p className="text-text-muted text-sm mb-3">
            暂无简历，上传你的第一份简历
          </p>
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
