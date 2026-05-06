"use client";

import Link from "next/link";
import Card from "@/app/components/ui/card";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import type { ResumeListItem } from "@/app/lib/api/types";

interface ResumeCardProps {
  resume: ResumeListItem;
  onDelete: (resume: ResumeListItem) => void;
  deleting: boolean;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function mediaLabel(type: string | null): string {
  if (!type) return "未知";
  if (type.includes("pdf")) return "PDF";
  if (type.includes("docx")) return "DOCX";
  if (type.includes("png") || type.includes("jpg") || type.includes("jpeg"))
    return "图片";
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
  if (status === "failed") return "warning";
  if (status === "processing") return "neutral";
  return "neutral";
}

export default function ResumeCard({
  resume,
  onDelete,
  deleting,
}: ResumeCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <h3 className="min-w-0 flex-1 truncate font-display text-base font-semibold text-text-primary">
              {resume.original_filename || `简历 #${resume.id}`}
            </h3>
            <Badge variant={resume.has_file ? "success" : "warning"} size="sm">
              {resume.has_file ? "可预览" : "无原文件"}
            </Badge>
            <Badge variant="neutral" size="sm">
              {mediaLabel(resume.media_type)}
            </Badge>
            <Badge variant={parseVariant(resume.parse_status)} size="sm">
              {parseLabel(resume.parse_status)}
            </Badge>
          </div>
          <p className="text-xs text-text-muted">
            {formatTime(resume.upload_time)}
          </p>
          {resume.summary && (
            <p className="mt-2 line-clamp-2 text-sm text-text-secondary">
              {resume.summary}
            </p>
          )}
          {resume.parse_error && (
            <p className="mt-2 line-clamp-2 text-sm text-error-text">
              {resume.parse_error}
            </p>
          )}
          {resume.parse_status === "parsed" && (
            <p className="mt-2 text-xs text-text-muted">
              {resume.section_count} 个章节 · {resume.fact_count} 条事实
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <div className="flex items-center gap-2">
            <Link
              href={`/resumes/${resume.id}`}
              className={buttonClassName({ variant: "ghost", size: "sm" })}
            >
              详情
            </Link>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(resume)}
              disabled={deleting}
              className="text-error-text hover:bg-error-bg"
            >
              {deleting ? "删除中..." : "删除"}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
