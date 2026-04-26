"use client";

import { useAppContext } from "@/app/lib/context/app-context";
import type { AgentStatus } from "@/app/lib/api/types";

const statusLabels: Record<AgentStatus, string> = {
  idle: "就绪",
  generating: "生成中",
  tool_calling: "工具调用中",
  interrupted: "已中断",
  error: "错误",
};

const statusColors: Record<AgentStatus, string> = {
  idle: "bg-success-text",
  generating: "bg-primary-500 animate-pulse",
  tool_calling: "bg-sky-blue animate-pulse",
  interrupted: "bg-warning-text",
  error: "bg-error-text",
};

export default function ContextBar() {
  const { state } = useAppContext();

  const modelLabel = state.currentModelSelection
    ? `模型 #${state.currentModelSelection}`
    : "未选择";

  return (
    <div className="h-10 bg-white border-b border-border-light flex items-center px-4 gap-4 text-xs text-text-secondary shrink-0">
      <div className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full" />
        <span className="text-text-muted">模型</span>
        <span className="font-medium text-text-primary truncate max-w-[120px]">
          {modelLabel}
        </span>
      </div>

      {state.currentThreadId && (
        <div className="flex items-center gap-1.5">
          <span className="text-text-muted">会话</span>
          <code className="font-mono text-[11px] text-text-primary bg-border-light px-1 py-0.5 rounded">
            {state.currentThreadId.slice(0, 12)}...
          </code>
        </div>
      )}

      {state.currentResumeId && (
        <div className="flex items-center gap-1.5">
          <span className="text-text-muted">简历</span>
          <span className="font-medium text-text-primary">
            #{state.currentResumeId}
          </span>
        </div>
      )}

      <div className="flex-1" />

      <div className="flex items-center gap-1.5">
        <span
          className={`w-1.5 h-1.5 rounded-full ${statusColors[state.agentStatus]}`}
        />
        <span className="text-text-muted">
          {statusLabels[state.agentStatus]}
        </span>
      </div>
    </div>
  );
}
