"use client";

import { useState } from "react";
import type { ToolCallEntry } from "@/app/hooks/use-chat-stream";

interface AgentTimelineProps {
  toolCalls: ToolCallEntry[];
  streamingText: string;
}

export default function AgentTimeline({
  toolCalls,
  streamingText,
}: AgentTimelineProps) {
  if (toolCalls.length === 0 && !streamingText) return null;

  return (
    <div className="border-t border-border-light bg-surface-secondary/50 p-3 max-h-48 overflow-y-auto">
      <h4 className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-2">
        Agent 运行时间线
      </h4>
      <div className="space-y-2">
        {toolCalls.map((tc, i) => (
          <ToolCallEntry key={i} entry={tc} />
        ))}
        {streamingText && (
          <div className="flex items-center gap-2 text-xs">
            <span className="w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse shrink-0" />
            <span className="text-text-muted">生成中</span>
            <span className="text-text-secondary font-mono text-[11px] truncate">
              {streamingText.slice(-50)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function ToolCallEntry({ entry }: { entry: ToolCallEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs w-full text-left"
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
        <div className="mt-1.5 ml-3.5 p-2 bg-white rounded-lg border border-border-light text-[11px] font-mono text-text-secondary overflow-x-auto">
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
