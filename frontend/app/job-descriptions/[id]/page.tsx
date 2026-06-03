"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback } from "react";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import { Skeleton } from "@/app/components/ui/skeleton";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { jobDescriptionsApi } from "@/app/lib/api/job-descriptions";
import type {
  JobDescriptionAnalysisDetail,
  JobDescriptionBlock,
  JobDescriptionFact,
} from "@/app/lib/api/types";

function formatTime(value: string | null): string {
  if (!value) return "未完成";
  return new Date(value).toLocaleString("zh-CN");
}

function statusLabel(status: JobDescriptionAnalysisDetail["status"]): string {
  if (status === "parsed") return "已完成";
  if (status === "failed") return "失败";
  return "处理中";
}

function statusVariant(status: JobDescriptionAnalysisDetail["status"]) {
  if (status === "parsed") return "success";
  if (status === "failed") return "error";
  return "warning";
}

function factLabel(fact: JobDescriptionFact): string {
  return fact.custom_fact_type || fact.fact_type;
}

export default function JobDescriptionDetailPage() {
  const params = useParams<{ id: string }>();
  const analysisId = Number(params.id);
  const fetchDetail = useCallback(
    () => jobDescriptionsApi.get(analysisId),
    [analysisId]
  );
  const { data, loading, error, refetch } = useAsyncData(fetchDetail, [fetchDetail]);

  if (loading) {
    return (
      <div className="electron-titlebar-safe-top mx-auto max-w-4xl p-6 lg:py-8">
        <Skeleton className="mb-2 h-8 w-48 rounded-lg" />
        <Skeleton className="mb-6 h-4 w-64 rounded-lg" />
        <Skeleton className="mb-4 h-40 rounded-[20px]" />
        <Skeleton className="h-72 rounded-[20px]" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="electron-titlebar-safe-top mx-auto max-w-4xl p-6">
        <div className="py-20 text-center">
          <p className="mb-4 text-sm text-error-text">{error || "加载失败"}</p>
          <Button variant="secondary" onClick={refetch}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  const result = data.result;
  const title = data.job_title || result?.job_title || `JD #${data.id}`;
  const salary = result?.salary?.raw;
  const metaItems = [
    data.company_name || result?.company_name,
    data.primary_location || result?.primary_location,
    result?.experience_raw,
    result?.education_raw,
  ].filter(Boolean);

  return (
    <div className="electron-titlebar-safe-top mx-auto max-w-4xl p-6 lg:py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h1 className="font-display text-2xl font-semibold text-text-primary">
              {title}
            </h1>
            <Badge variant={statusVariant(data.status)}>{statusLabel(data.status)}</Badge>
          </div>
          <p className="text-sm text-text-muted">
            {metaItems.join(" · ") || "未识别公司、地点和要求"}
          </p>
        </div>
        <Link
          href="/job-descriptions"
          className={buttonClassName({ variant: "secondary", size: "sm" })}
        >
          返回列表
        </Link>
      </div>

      <Card shadow="none" radius="lg" padding="lg" className="mb-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="公司" value={data.company_name || result?.company_name} />
          <Metric label="地点" value={data.primary_location || result?.primary_location} />
          <Metric label="薪资" value={salary} />
          <Metric label="完成时间" value={formatTime(data.completed_at)} />
        </div>
        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noreferrer"
            className="mt-4 block truncate text-sm font-medium text-primary-600"
          >
            {data.source_url}
          </a>
        )}
        {data.error_message && (
          <p className="mt-4 rounded-xl bg-error-bg px-3 py-2 text-sm text-error-text">
            {data.error_message}
          </p>
        )}
      </Card>

      {result && (
        <Card shadow="none" radius="lg" padding="lg" className="mb-4">
          <h2 className="mb-4 text-base font-semibold text-text-primary">结构化字段</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <Info label="岗位族" value={result.job_family} />
            <Info label="级别" value={result.job_level} />
            <Info label="工作方式" value={result.remote_policy} />
            <Info label="雇佣类型" value={result.employment_type} />
            <Info label="经验" value={result.experience_raw} />
            <Info label="学历" value={result.education_raw} />
            <Info label="专业要求" value={result.major_requirement} />
            <Info label="公司规模" value={result.company_size} />
          </div>
          {result.benefits.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {result.benefits.map((benefit) => (
                <Badge key={benefit} variant="info">
                  {benefit}
                </Badge>
              ))}
            </div>
          )}
        </Card>
      )}

      {result?.blocks.length ? (
        <div className="mb-4 space-y-3">
          {result.blocks.map((block, index) => (
            <BlockCard key={`${block.title}-${index}`} block={block} />
          ))}
        </div>
      ) : (
        <Card shadow="none" radius="lg" padding="lg" className="mb-4">
          <p className="text-sm text-text-muted">暂无结构化需求块。</p>
        </Card>
      )}

      <Card shadow="none" radius="lg" padding="lg">
        <h2 className="mb-3 text-base font-semibold text-text-primary">JD 原文</h2>
        <pre className="max-h-[520px] whitespace-pre-wrap rounded-2xl bg-surface-secondary p-4 text-sm leading-6 text-text-primary">
          {data.raw_text || "暂无原文"}
        </pre>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="mb-1 text-xs text-text-muted">{label}</p>
      <p className="truncate text-sm font-semibold text-text-primary">
        {value || "未识别"}
      </p>
    </div>
  );
}

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="rounded-xl bg-surface-secondary px-3 py-2">
      <p className="mb-1 text-xs text-text-muted">{label}</p>
      <p className="text-sm text-text-primary">{value || "未识别"}</p>
    </div>
  );
}

function BlockCard({ block }: { block: JobDescriptionBlock }) {
  return (
    <Card shadow="none" radius="lg" padding="lg">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-text-primary">{block.title}</h2>
        <Badge variant="neutral">{block.block_type}</Badge>
      </div>
      <p className="mb-4 whitespace-pre-wrap text-sm leading-6 text-text-secondary">
        {block.content}
      </p>
      {block.facts.length > 0 && (
        <div className="space-y-2">
          {block.facts.map((fact, index) => (
            <div
              key={`${fact.text}-${index}`}
              className="rounded-xl border border-border-light bg-white p-3"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge variant="info">{factLabel(fact)}</Badge>
                <Badge variant="neutral">{fact.importance}</Badge>
              </div>
              <p className="text-sm font-medium text-text-primary">{fact.text}</p>
              <p className="mt-1 text-xs text-text-muted">{fact.evidence}</p>
              {fact.keywords.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {fact.keywords.map((keyword) => (
                    <span
                      key={keyword}
                      className="rounded-md bg-surface-secondary px-2 py-0.5 text-[11px] text-text-secondary"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
