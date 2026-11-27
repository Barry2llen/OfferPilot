import FormDrawer from "@/app/components/ui/form-drawer";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { resumesApi } from "@/app/lib/api/resumes";
import { formatLocaleNumber } from "@/app/lib/i18n";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ResumeCard from "@/app/components/resumes/resume-card";
import ResumeUploader from "@/app/components/resumes/resume-uploader";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Button from "@/app/components/ui/button";
import Select from "@/app/components/ui/select";
import { Skeleton } from "@/app/components/ui/skeleton";
import type { ResumeListItem } from "@/app/lib/api/types";
import { useAppContext } from "@/app/lib/context/app-context";
import { useResumeUpload } from "@/app/lib/context/resume-upload-context";
import { analysisTaskKey } from "@/app/lib/analysis-events/types";

interface ResumeStats {
  total: number;
  parsed: number;
  processing: number;
  failed: number;
}

export default function ResumesPage() {
  const { t } = useTranslation();
  const fetchResumes = useCallback(() => resumesApi.list(), []);
  const { data, loading, error, refetch, refresh } = useAsyncData(fetchResumes, [
    fetchResumes,
  ]);
  const {
    state: { analysisEventVersions, analysisTasks },
  } = useAppContext();
  const { running: uploading } = useResumeUpload();
  const { addToast } = useToast();

  useEffect(() => {
    if (analysisEventVersions.resume > 0) refresh();
  }, [analysisEventVersions.resume, refresh]);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("newest");
  const filtered = useMemo(() => (data ?? []).filter((item) =>
    (status === "all" || item.parse_status === status) && (item.original_filename ?? "").toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  ).sort((a, b) => sort === "name" ? (a.original_filename ?? "").localeCompare(b.original_filename ?? "") : new Date(b.upload_time).getTime() - new Date(a.upload_time).getTime()), [data, query, status, sort]);

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
    setUploadOpen(false);
    refetch();
  }, [refetch]);

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(confirmDelete.id);
    try {
      await resumesApi.delete(confirmDelete.id);
      addToast(t("upload.resumeDeleted"), "success");
      setConfirmDelete(null);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("errors.deleteFailed");
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

  const isEmpty = !data || data.length === 0;

  return (
    <PageCanvas>
      <div className="space-y-6">
        <header className="resource-heading">
          <div className="min-w-0">
            <h1>{t("nav.resumes")}</h1>
            {!isEmpty && (
              <p className="mt-1 text-sm text-text-muted">
                {t("resume.stats", {
                  count: stats.total,
                  total: formatLocaleNumber(stats.total),
                  parsed: formatLocaleNumber(stats.parsed),
                })}
              </p>
            )}
          </div>
          {!isEmpty && (
            <Button className="shrink-0" onClick={() => setUploadOpen(true)}>
              {t("appearance.upload")}
            </Button>
          )}
        </header>
        <FormDrawer
          open={uploadOpen}
          busy={uploading}
          title={t("appearance.upload")}
          onClose={() => setUploadOpen(false)}
        >
          <ResumeUploader onUploaded={handleUploaded} />
        </FormDrawer>

        {isEmpty ? (
          <ResumeUploader onUploaded={handleUploaded} variant="hero" />
        ) : (
        <section>
          <h2 className="sr-only">{t("resume.recentUploads")}</h2>
          <div className="resource-toolbar">
            <input type="search" aria-label={t("appearance.searchResumes")} placeholder={t("appearance.searchResumes")} value={query} onChange={(e) => setQuery(e.target.value)} />
            <Select aria-label={t("resume.filter")} className="resource-select" value={status} onChange={setStatus} options={[
              { value: "all", label: t("appearance.all") },
              { value: "parsed", label: t("resume.parsed") },
              { value: "processing", label: t("resume.parsing") },
              { value: "failed", label: t("resume.parseFailed") },
              { value: "unparsed", label: t("resume.unparsed") },
            ]} />
            <Select aria-label={t("resume.sort")} className="resource-select" align="end" value={sort} onChange={setSort} options={[
              { value: "newest", label: t("appearance.newest") },
              { value: "name", label: t("appearance.name") },
            ]} />
          </div>
            <div className="space-y-3">
              {filtered.length === 0 && <EmptyState title={t("appearance.noResults")} />}
              {filtered.map((resume) => (
                <ResumeCard
                  key={resume.id}
                  resume={resume}
                  analysisTask={analysisTasks[analysisTaskKey("resume", resume.id)]}
                  onDelete={setConfirmDelete}
                  deleting={deleting === resume.id}
                />
              ))}
            </div>
        </section>
        )}
      </div>

      <ConfirmDialog
        open={!!confirmDelete}
        title={t("resume.deleteTitle")}
        message={t("resume.deleteMessage", {
          name:
            confirmDelete?.original_filename ||
            t("resume.defaultTitle", { id: confirmDelete?.id }),
        })}
        confirmLabel={t("common.delete")}
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
    <div className="electron-titlebar-safe-top min-h-full bg-surface-primary">
      <div className="mx-auto max-w-[1040px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        {children}
      </div>
    </div>
  );
}

function EmptyState({ title }: { title: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border-default bg-surface-primary px-6 py-10 text-center">
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-surface-secondary text-text-muted">
        <FileStackIcon className="h-5 w-5" />
      </div>
      <p className="text-sm font-medium text-text-primary">{title}</p>
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
  const { t } = useTranslation();

  return (
    <div className="rounded-xl border border-border-light bg-surface-primary px-6 py-16 text-center shadow-card">
      <p className="mb-4 text-sm text-error-text">{error}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        {t("common.retry")}
      </Button>
    </div>
  );
}

function ResumesPageSkeleton() {
  return (
    <PageCanvas>
      <div className="space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Skeleton className="mb-2 h-7 w-28 rounded-lg" />
            <Skeleton className="h-4 w-48 rounded-lg" />
          </div>
          <Skeleton className="h-10 w-28 rounded-lg" />
        </div>
        <section>
          <Skeleton className="my-5 h-10 rounded-lg" />
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
