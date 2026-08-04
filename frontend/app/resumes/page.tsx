import { useCallback, useMemo, useState, type ReactNode } from "react";
import { resumesApi } from "@/app/lib/api/resumes";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ResumeCard from "@/app/components/resumes/resume-card";
import ResumeUploader from "@/app/components/resumes/resume-uploader";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Button from "@/app/components/ui/button";
import { Skeleton } from "@/app/components/ui/skeleton";
import type { ResumeListItem } from "@/app/lib/api/types";

interface ResumeStats {
  total: number;
  parsed: number;
  processing: number;
  failed: number;
}

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

  const stats = useMemo<ResumeStats>(() => {
    const resumes = data ?? [];
    return {
      total: resumes.length,
      parsed: resumes.filter((item) => item.parse_status === "parsed").length,
      processing: resumes.filter((item) => item.parse_status === "processing")
        .length,
      failed: resumes.filter((item) => item.parse_status === "failed").length,
    };
  }, [data]);

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
    return <ResumesPageSkeleton />;
  }

  if (error) {
    return (
      <PageCanvas>
        <ErrorPanel error={error} onRetry={refetch} />
      </PageCanvas>
    );
  }

  return (
    <PageCanvas>
      <div className="space-y-8">
        <ResumeUploader onUploaded={handleUploaded} variant="hero" />

        <section>
          <div className="mb-3 flex items-center justify-between gap-4">
            <div>
              <h1 className="font-display text-base font-semibold text-text-primary">
                最近上传
              </h1>
              <p className="mt-1 text-xs text-text-muted">
                {stats.total > 0
                  ? `共 ${stats.total} 份简历，${stats.parsed} 份已完成解析`
                  : "上传第一份简历后会显示在这里"}
              </p>
            </div>
            <div className="flex items-center gap-1 text-text-muted">
              <IconButton label="筛选">
                <FilterIcon className="h-3.5 w-3.5" />
              </IconButton>
              <IconButton label="排序">
                <SortIcon className="h-3.5 w-3.5" />
              </IconButton>
            </div>
          </div>

          {data && data.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="space-y-3">
              {data?.map((resume) => (
                <ResumeCard
                  key={resume.id}
                  resume={resume}
                  onDelete={setConfirmDelete}
                  deleting={deleting === resume.id}
                />
              ))}
            </div>
          )}
        </section>
      </div>

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
    </PageCanvas>
  );
}

function PageCanvas({ children }: { children: ReactNode }) {
  return (
    <div className="electron-titlebar-safe-top min-h-full bg-white">
      <div className="mx-auto max-w-[1040px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        {children}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-[#c3c5d8] bg-white px-6 py-10 text-center shadow-card">
      <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-[#dce1ff] text-primary-700">
        <FileStackIcon className="h-5 w-5" />
      </div>
      <p className="font-display text-base font-medium text-text-primary">
        暂无简历
      </p>
      <p className="mt-1 text-xs text-text-muted">
        上传第一份简历后，解析状态和最近上传会同步更新。
      </p>
    </div>
  );
}

function ErrorPanel({
  error,
  onRetry,
}: {
  error: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-xl border border-border-light bg-white px-6 py-16 text-center shadow-card">
      <p className="mb-4 text-sm text-error-text">{error}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        重试
      </Button>
    </div>
  );
}

function ResumesPageSkeleton() {
  return (
    <PageCanvas>
      <div className="space-y-8">
        <Skeleton className="h-[232px] rounded-[20px]" />
        <Skeleton className="h-[110px] rounded-[18px]" />
        <section>
          <div className="mb-3 flex items-center justify-between">
            <div>
              <Skeleton className="mb-2 h-5 w-24 rounded-lg" />
              <Skeleton className="h-4 w-48 rounded-lg" />
            </div>
            <div className="flex gap-2">
              <Skeleton className="h-7 w-7 rounded-full" />
              <Skeleton className="h-7 w-7 rounded-full" />
            </div>
          </div>
          <div className="space-y-3">
            {[1, 2, 3].map((item) => (
              <Skeleton key={item} className="h-[88px] rounded-xl" />
            ))}
          </div>
        </section>
      </div>
    </PageCanvas>
  );
}

function IconButton({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className="rounded-full p-2 transition-colors hover:bg-surface-secondary hover:text-text-primary"
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}

function FilterIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M4 7h16M7 12h10M10 17h4"
      />
    </svg>
  );
}

function SortIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M8 6h10M8 12h7M8 18h4M5 6h.01M5 12h.01M5 18h.01"
      />
    </svg>
  );
}

function FileStackIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M8 4h7l3 3v12H8V4Z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M15 4v3h3M5 7v13h10M10.5 12h5M10.5 15h4"
      />
    </svg>
  );
}
