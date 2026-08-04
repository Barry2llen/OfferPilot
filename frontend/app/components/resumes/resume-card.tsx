import { Link } from "react-router-dom";
import { resumesApi } from "@/app/lib/api/resumes";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import type { ResumeListItem } from "@/app/lib/api/types";

interface ResumeCardProps {
  resume: ResumeListItem;
  onDelete: (resume: ResumeListItem) => void;
  deleting: boolean;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function mediaLabel(type: string | null): string {
  if (!type) return "未知";
  if (type.includes("pdf")) return "PDF";
  if (type.includes("docx")) return "DOCX";
  if (type.includes("png") || type.includes("jpg") || type.includes("jpeg")) {
    return "图片";
  }
  return type;
}

function parseLabel(status: ResumeListItem["parse_status"]): string {
  switch (status) {
    case "parsed":
      return "已解析";
    case "processing":
      return "解析中";
    case "failed":
      return "解析失败";
    case "unparsed":
    default:
      return "未解析";
  }
}

function parseVariant(status: ResumeListItem["parse_status"]) {
  if (status === "parsed") return "success";
  if (status === "failed") return "error";
  if (status === "processing") return "warning";
  return "neutral";
}

function fileIconTone(type: string | null) {
  if (type?.includes("pdf")) {
    return "bg-error-bg text-error-text";
  }
  if (type?.includes("docx")) {
    return "bg-[#dce1ff] text-primary-700";
  }
  return "bg-[#cee5ff] text-info-text";
}

export default function ResumeCard({
  resume,
  onDelete,
  deleting,
}: ResumeCardProps) {
  const statusText =
    resume.parse_status === "parsed"
      ? `${resume.section_count} 个章节 · ${resume.fact_count} 条事实`
      : resume.has_file
        ? mediaLabel(resume.media_type)
        : "无原文件";
  const description = resume.parse_error || resume.summary || statusText;
  const factLabel =
    resume.parse_status === "parsed"
      ? `${resume.section_count} 章 · ${resume.fact_count} 事实`
      : mediaLabel(resume.media_type);

  return (
    <article className="group rounded-xl border border-border-light bg-white px-5 py-4 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-elevated">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 flex-1 items-start gap-4 sm:items-center">
          <div
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${fileIconTone(
              resume.media_type
            )}`}
          >
            <FileIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-display text-base font-semibold leading-6 text-text-primary">
              {resume.original_filename || `简历 #${resume.id}`}
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-xs text-text-muted">
              <span>{formatTime(resume.upload_time)}</span>
              <span className="h-1 w-1 rounded-full bg-border-default" />
              <span>{factLabel}</span>
              {resume.parsed_at && (
                <>
                  <span className="h-1 w-1 rounded-full bg-border-default" />
                  <span>
                    解析于 {new Date(resume.parsed_at).toLocaleDateString("zh-CN")}
                  </span>
                </>
              )}
            </div>
            <p
              className={`mt-1.5 line-clamp-1 text-xs leading-5 ${
                resume.parse_error ? "text-error-text" : "text-text-secondary"
              }`}
            >
              {description}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center xl:shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={parseVariant(resume.parse_status)}
              className="rounded-full px-3 py-1 font-mono text-[11px] font-bold"
            >
              {parseLabel(resume.parse_status)}
            </Badge>
            <Badge
              variant="neutral"
              className="rounded-full px-3 py-1 font-mono text-[11px] font-bold"
            >
              {resume.has_file ? mediaLabel(resume.media_type) : "无原文件"}
            </Badge>
          </div>

          <div className="flex items-center gap-1.5 font-mono text-xs font-medium">
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
                预览
              </a>
            ) : (
              <span className="px-2.5 text-text-muted">预览</span>
            )}
            <Link
              to={`/resumes/${resume.id}`}
              className={buttonClassName({
                variant: "ghost",
                size: "sm",
                className: "h-8 px-3 text-primary-700 hover:text-primary-600",
              })}
            >
              详情
            </Link>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(resume)}
              disabled={deleting}
              className="h-8 px-2.5 text-error-text hover:bg-error-bg"
              aria-label={`删除 ${resume.original_filename || `简历 #${resume.id}`}`}
            >
              {deleting ? "删除中..." : <TrashIcon className="h-4 w-4" />}
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
