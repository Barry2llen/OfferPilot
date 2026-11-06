import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import i18n from "@/app/lib/i18n";
import { resumeMediaLabel, resumesApi } from "@/app/lib/api/resumes";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import AnalysisTaskStatus from "@/app/components/analysis/analysis-task-status";
import type { ResumeListItem } from "@/app/lib/api/types";
import type { AnalysisTaskSnapshot } from "@/app/lib/analysis-events/types";

interface ResumeCardProps {
  resume: ResumeListItem;
  analysisTask?: AnalysisTaskSnapshot;
  onDelete: (resume: ResumeListItem) => void;
  deleting: boolean;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleDateString(i18n.language, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function parseLabel(status: ResumeListItem["parse_status"]): string {
  switch (status) {
    case "parsed":
      return i18n.t("resume.parsed");
    case "processing":
      return i18n.t("resume.parsing");
    case "failed":
      return i18n.t("resume.parseFailed");
    case "unparsed":
    default:
      return i18n.t("resume.unparsed");
  }
}

function parseVariant(status: ResumeListItem["parse_status"]) {
  if (status === "parsed") return "success";
  if (status === "failed") return "error";
  if (status === "processing") return "warning";
  return "neutral";
}

function fileIconTone(label: string) {
  if (label === "PDF") {
    return "bg-error-bg text-error-text";
  }
  if (label === "DOCX" || label === "DOC") {
    return "bg-info-bg text-info-text";
  }
  return "bg-surface-secondary text-text-secondary";
}

export default function ResumeCard({
  resume,
  analysisTask,
  onDelete,
  deleting,
}: ResumeCardProps) {
  const { t } = useTranslation();
  const title =
    resume.original_filename || t("resume.defaultTitle", { id: resume.id });
  const formatLabel = resume.has_file
    ? resumeMediaLabel(resume.media_type, resume.original_filename)
    : t("common.noFile");
  const description = resume.parse_error || resume.summary;
  const isParsed = resume.parse_status === "parsed";
  const metaItems = [
    formatTime(resume.upload_time),
    isParsed
      ? `${t("resume.shortSectionCount", { count: resume.section_count })} · ${t(
          "resume.shortFactCount",
          { count: resume.fact_count },
        )}`
      : null,
    resume.parsed_at
      ? t("resume.parsedAt", { date: formatTime(resume.parsed_at) })
      : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <article className="group rounded-xl border border-border-light bg-surface-primary px-4 py-4 transition-colors duration-150 hover:border-text-muted/40 sm:px-5">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between xl:gap-6">
        <div className="flex min-w-0 flex-1 items-start gap-3 sm:gap-4">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${fileIconTone(
              formatLabel
            )}`}
          >
            <FileIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h3
              className="truncate font-display text-[15px] font-semibold leading-6 text-text-primary"
              title={title}
            >
              {title}
            </h3>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs tabular-nums text-text-muted">
              {metaItems.map((item, index) => (
                <span
                  key={`${index}-${item}`}
                  className={index > 0 ? "before:mr-2 before:content-['·']" : undefined}
                >
                  {item}
                </span>
              ))}
            </p>
            {description && (
              <p
                className={`mt-1.5 line-clamp-1 text-xs leading-5 ${
                  resume.parse_error ? "text-error-text" : "text-text-secondary"
                }`}
                title={description}
              >
                {description}
              </p>
            )}
            <AnalysisTaskStatus task={analysisTask} />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 pl-[52px] sm:pl-14 xl:shrink-0 xl:justify-end xl:pl-0">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <Badge
              variant={parseVariant(resume.parse_status)}
              className="rounded-full px-2.5"
            >
              {parseLabel(resume.parse_status)}
            </Badge>
            <Badge variant="neutral" className="max-w-[8rem] rounded-full px-2.5">
              <span className="truncate">{formatLabel}</span>
            </Badge>
          </div>

          <div className="flex items-center gap-1 text-xs font-medium">
            {resume.has_file ? (
              <a
                href={resumesApi.previewUrl(resume.id)}
                target="_blank"
                rel="noreferrer"
                className={buttonClassName({
                  variant: "ghost",
                  size: "sm",
                  className: "h-8 px-3 text-primary-700 hover:text-primary-600",
                })}
              >
                {t("common.preview")}
              </a>
            ) : (
              <span className="px-2.5 text-text-muted">{t("common.preview")}</span>
            )}
            <Link
              to={`/resumes/${resume.id}`}
              className={buttonClassName({
                variant: "ghost",
                size: "sm",
                className: "h-8 px-3 text-primary-700 hover:text-primary-600",
              })}
            >
              {t("common.details")}
            </Link>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(resume)}
              disabled={deleting}
              className="h-8 px-2.5 text-error-text hover:bg-error-bg"
              aria-label={`${t("common.delete")} ${title}`}
              title={t("common.delete")}
            >
              {deleting ? t("resume.deleteInProgress") : <TrashIcon className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}

function FileIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 3.75h6l4 4v12.5H7V3.75Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 3.75v4h4M9.5 12h5M9.5 15h5M9.5 18h3" />
    </svg>
  );
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 7h14M10 11v6M14 11v6M8 7l1 13h6l1-13M9.5 7l.75-3h3.5l.75 3" />
    </svg>
  );
}
