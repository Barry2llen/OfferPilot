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

  const handleCopyText = useCallback(() => {
    if (resume?.content) {
      navigator.clipboard.writeText(resume.content);
      addToast("已复制解析文本", "success");
    }
  }, [resume, addToast]);

  const handleReplace = useCallback(
    async () => {
      setReplaceOpen(false);
      refetch();
      addToast("文件已替换", "success");
    },
    [refetch, addToast]
  );

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
            onClick={handleCopyText}
          >
            复制文本
          </Button>
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
              uploadFile={(file) => resumesApi.replace(id, file)}
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

      <Card>
        <h2 className="font-display text-base font-semibold text-text-primary mb-3">
          解析文本
        </h2>
        {resume.content ? (
          <pre className="whitespace-pre-wrap text-sm text-text-secondary leading-relaxed font-sans">
            {resume.content}
          </pre>
        ) : (
          <p className="text-text-muted text-sm">暂无解析内容</p>
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
