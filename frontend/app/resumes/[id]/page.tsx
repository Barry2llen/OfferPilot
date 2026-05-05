"use client";

import { useState, useCallback } from "react";
import Image from "next/image";
import { useParams } from "next/navigation";
import Link from "next/link";
import { resumesApi } from "@/app/lib/api/resumes";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Badge from "@/app/components/ui/badge";
import Card from "@/app/components/ui/card";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Spinner from "@/app/components/ui/spinner";
import ResumeUploader from "@/app/components/resumes/resume-uploader";
import type { ResumeSection } from "@/app/lib/api/types";

export default function ResumeDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const { addToast } = useToast();

  const { data: resume, loading, error, refetch } = useAsyncData(
    () => resumesApi.get(id),
    [id]
  );

  const [replaceOpen, setReplaceOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [operating, setOperating] = useState(false);

  const handleReplace = useCallback(
    async () => {
      setReplaceOpen(false);
      refetch();
      addToast("文件已替换", "success");
    },
    [refetch, addToast]
  );

  const handleCopyRawText = async () => {
    if (!resume?.raw_text) return;
    try {
      await navigator.clipboard.writeText(resume.raw_text);
      addToast("解析文本已复制", "success");
    } catch {
      addToast("复制失败", "error");
    }
  };

  const handleDelete = async () => {
    setOperating(true);
    try {
      await resumesApi.delete(id);
      addToast("简历已删除", "success");
      window.location.href = "/resumes";
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除失败";
      addToast(msg, "error");
    } finally {
      setOperating(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="text-center py-20">
          <p className="text-error-text text-sm mb-4">{error}</p>
          <div className="flex gap-3 justify-center">
            <Button variant="secondary" onClick={refetch}>
              重试
            </Button>
            <Link
              href="/resumes"
              className={buttonClassName({ variant: "ghost" })}
            >
              返回列表
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!resume) return null;

  return (
    <div className="max-w-3xl mx-auto p-6 lg:py-8">
      <div className="flex items-center gap-3 mb-6">
        <Link
          href="/resumes"
          className={buttonClassName({ variant: "ghost", size: "sm" })}
        >
          ← 返回列表
        </Link>
      </div>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-text-primary">
            {resume.original_filename || `简历 #${resume.id}`}
          </h1>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <Badge variant={resume.has_file ? "success" : "warning"}>
              {resume.has_file ? "可预览" : "无原文件"}
            </Badge>
            <Badge variant="neutral">{resume.media_type || "未知"}</Badge>
            <span className="text-xs text-text-muted">
              {new Date(resume.upload_time).toLocaleString("zh-CN")}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmDelete(true)}
            className="text-error-text hover:bg-error-bg"
          >
            删除
          </Button>
        </div>
      </div>

      {resume.has_file && (
        <Card className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-base font-semibold text-text-primary">
              文件预览
            </h2>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setReplaceOpen(!replaceOpen)}
            >
              {replaceOpen ? "取消替换" : "替换文件"}
            </Button>
          </div>
          {replaceOpen ? (
            <ResumeUploader
              onUploaded={handleReplace}
              uploadFile={(file, selectionId, onEvent, onError, signal) =>
                resumesApi.replace(
                  id,
                  file,
                  selectionId,
                  onEvent,
                  onError,
                  signal
                )
              }
            />
          ) : (
            <div className="rounded-xl overflow-hidden border border-border-light bg-surface-secondary">
              {resume.media_type?.includes("pdf") ? (
                <iframe
                  src={resumesApi.previewUrl(id)}
                  className="w-full h-[500px]"
                  title="简历预览"
                />
              ) : resume.media_type?.startsWith("image/") ? (
                <Image
                  src={resumesApi.previewUrl(id)}
                  alt={resume.original_filename || ""}
                  width={1200}
                  height={1600}
                  unoptimized
                  className="w-auto h-auto max-w-full max-h-[500px] mx-auto"
                />
              ) : (
                <div className="text-center py-12 text-text-muted text-sm">
                  不支持在线预览此格式
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      <Card className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
          <div>
            <h2 className="font-display text-base font-semibold text-text-primary">
              解析结果
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge
                variant={
                  resume.parse_status === "parsed"
                    ? "success"
                    : resume.parse_status === "failed"
                      ? "warning"
                      : "neutral"
                }
              >
                {resume.parse_status === "parsed"
                  ? "已解析"
                  : resume.parse_status === "failed"
                    ? "解析失败"
                    : resume.parse_status === "processing"
                      ? "解析中"
                      : "未解析"}
              </Badge>
              {resume.parsed_at && (
                <span className="text-xs text-text-muted">
                  {new Date(resume.parsed_at).toLocaleString("zh-CN")}
                </span>
              )}
              {resume.parse_status === "parsed" && (
                <span className="text-xs text-text-muted">
                  {resume.section_count} 个章节 · {resume.fact_count} 条事实
                </span>
              )}
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            disabled={!resume.raw_text}
            onClick={handleCopyRawText}
          >
            复制解析文本
          </Button>
        </div>

        {resume.parse_error ? (
          <div className="rounded-lg bg-error-bg px-4 py-3 text-sm text-error-text">
            {resume.parse_error}
          </div>
        ) : resume.parse_status !== "parsed" ? (
          <div className="rounded-lg bg-surface-secondary px-4 py-8 text-center text-sm text-text-muted">
            上传或替换文件后会在这里显示解析文本和结构化章节
          </div>
        ) : (
          <div className="space-y-5">
            {resume.summary && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-text-primary">
                  摘要
                </h3>
                <p className="text-sm text-text-secondary">{resume.summary}</p>
              </div>
            )}
            <div>
              <h3 className="mb-2 text-sm font-semibold text-text-primary">
                完整文本
              </h3>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-secondary p-4 text-sm text-text-secondary">
                {resume.raw_text}
              </pre>
            </div>
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-text-primary">
                结构化章节
              </h3>
              {resume.sections.map((section: ResumeSection, index: number) => (
                <section
                  key={`${section.title}-${index}`}
                  className="rounded-lg border border-border-light p-4"
                >
                  <h4 className="font-display text-sm font-semibold text-text-primary">
                    {section.title || `章节 ${index + 1}`}
                  </h4>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-text-secondary">
                    {section.content}
                  </p>
                  {section.facts.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {section.facts.map((fact, factIndex) => (
                        <div
                          key={`${fact.fact_type}-${factIndex}`}
                          className="rounded-lg bg-surface-secondary px-3 py-2"
                        >
                          <div className="mb-1 flex flex-wrap items-center gap-2">
                            <Badge variant="info">{fact.fact_type}</Badge>
                            <span className="text-sm text-text-primary">
                              {fact.text}
                            </span>
                          </div>
                          {fact.keywords.length > 0 && (
                            <p className="text-xs text-text-muted">
                              {fact.keywords.join("、")}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              ))}
            </div>
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={confirmDelete}
        title="删除简历"
        message={`确定要删除「${resume.original_filename || `简历 #${resume.id}`}」吗？此操作会删除数据库记录和原始文件。`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
        loading={operating}
      />
    </div>
  );
}
