"use client";

import { useState } from "react";
import type { ToolCallEntry } from "@/app/hooks/use-chat-stream";

interface AgentTimelineProps {
  toolCalls: ToolCallEntry[];
  streamingText: string;
  isStreaming: boolean;
}

export default function AgentTimeline({
  toolCalls,
  streamingText,
  isStreaming,
}: AgentTimelineProps) {
  const [collapsed, setCollapsed] = useState(true);
  const [maximized, setMaximized] = useState(false);

  if (toolCalls.length === 0 && !isStreaming && !streamingText) {
    return null;
  }

  const runningCount = toolCalls.filter((entry) => entry.status === "running").length;
  const successCount = toolCalls.filter((entry) => entry.status === "success").length;
  const errorCount = toolCalls.filter((entry) => entry.status === "error").length;
  const statusLabel = runningCount > 0
    ? "工具执行中"
    : isStreaming
      ? "生成中"
      : errorCount > 0
        ? "存在失败"
        : "已完成";

  return (
    <>
      <div className="border-t border-border-light bg-surface-secondary/50">
        <div className="flex h-11 items-center gap-3 px-4">
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            className="inline-flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1.5 py-1 text-left hover:bg-black/[0.03]"
            aria-expanded={!collapsed}
          >
            <svg
              className={`h-3.5 w-3.5 shrink-0 text-text-muted transition-transform ${
                collapsed ? "" : "rotate-90"
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="shrink-0 text-[11px] font-medium uppercase tracking-wider text-text-muted">
              Agent 运行时间线
            </span>
            <span className="h-1 w-1 rounded-full bg-border-default" />
            <span className="truncate text-xs text-text-secondary">{statusLabel}</span>
            <span className="hidden shrink-0 text-[11px] text-text-muted sm:inline">
              工具 {toolCalls.length}
              {successCount > 0 ? ` · 完成 ${successCount}` : ""}
              {errorCount > 0 ? ` · 失败 ${errorCount}` : ""}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setMaximized(true)}
            className="rounded-lg p-1.5 text-text-muted hover:bg-black/[0.04] hover:text-text-primary"
            aria-label="放大查看 Agent 运行时间线"
            title="放大查看"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4" />
            </svg>
          </button>
        </div>

        {!collapsed && (
          <div className="max-h-48 overflow-y-auto border-t border-border-light px-4 py-3">
            <TimelineDetails
              toolCalls={toolCalls}
              streamingText={streamingText}
              isStreaming={isStreaming}
            />
          </div>
        )}
      </div>

      {maximized && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/30 p-6"
          role="dialog"
          aria-modal="true"
          aria-label="Agent 运行时间线"
        >
          <div className="flex max-h-[82vh] w-full max-w-4xl flex-col rounded-2xl bg-white shadow-elevated">
            <div className="flex items-center gap-3 border-b border-border-light px-5 py-4">
              <div className="min-w-0 flex-1">
                <h3 className="font-display text-base font-semibold text-text-primary">
                  Agent 运行时间线
                </h3>
                <p className="mt-0.5 text-xs text-text-muted">
                  {statusLabel} · 工具 {toolCalls.length}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setMaximized(false)}
                className="rounded-lg p-2 text-text-muted hover:bg-surface-secondary hover:text-text-primary"
                aria-label="关闭放大视图"
                title="关闭"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="overflow-y-auto p-5">
              <TimelineDetails
                toolCalls={toolCalls}
                streamingText={streamingText}
                isStreaming={isStreaming}
                defaultExpanded
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function TimelineDetails({
  toolCalls,
  streamingText,
  isStreaming,
  defaultExpanded = false,
}: {
  toolCalls: ToolCallEntry[];
  streamingText: string;
  isStreaming: boolean;
  defaultExpanded?: boolean;
}) {
  return (
    <div className="space-y-2">
      {isStreaming && (
        <div className="flex items-center gap-2 text-xs">
          <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-primary-500" />
          <span className="text-text-muted">生成中</span>
          {streamingText && (
            <span className="truncate font-mono text-[11px] text-text-secondary">
              {streamingText.slice(-80)}
            </span>
          )}
        </div>
      )}
      {toolCalls.length === 0 ? (
        <div className="text-xs text-text-muted">暂无工具调用</div>
      ) : (
        toolCalls.map((entry, index) => (
          <ToolCallEntry key={`${entry.name}-${index}`} entry={entry} defaultExpanded={defaultExpanded} />
        ))
      )}
    </div>
  );
}

function ToolCallEntry({
  entry,
  defaultExpanded = false,
}: {
  entry: ToolCallEntry;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs w-full text-left"
        aria-expanded={expanded}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            entry.status === "running"
              ? "bg-sky-blue animate-pulse"
              : entry.status === "success"
                ? "bg-success-text"
                : "bg-error-text"
          }`}
        />
        <span className="text-text-muted font-medium">{entry.name}</span>
        <span
          className={`text-[11px] ${
            entry.status === "running"
              ? "text-sky-blue"
              : entry.status === "success"
                ? "text-success-text"
                : "text-error-text"
          }`}
        >
          {entry.status === "running"
            ? "执行中..."
            : entry.status === "success"
              ? "完成"
              : "失败"}
        </span>
      </button>
      {expanded && (
        <div className="mt-1.5 ml-3.5 whitespace-pre-wrap rounded-lg border border-border-light bg-white p-2 font-mono text-[11px] text-text-secondary overflow-x-auto">
          {entry.input && (
            <div className="mb-1">
              <span className="text-text-muted">input:</span>{" "}
              {JSON.stringify(entry.input, null, 2)}
            </div>
          )}
          {entry.output !== undefined && (
            <div className="mb-1">
              <span className="text-text-muted">output:</span>{" "}
              {typeof entry.output === "string"
                ? entry.output
                : JSON.stringify(entry.output, null, 2)}
            </div>
          )}
          {entry.error && (
            <div className="text-error-text">
              <span className="text-text-muted">error:</span> {entry.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
