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

  return (
    <div className="h-10 bg-white border-b border-border-light flex items-center px-4 gap-4 text-xs text-text-secondary shrink-0">
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
