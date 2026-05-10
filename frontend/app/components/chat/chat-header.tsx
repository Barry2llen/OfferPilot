"use client";

import ModelSelectionPicker from "@/app/components/chat/model-selection-picker";
import type { ModelSelectionResponse, AgentStatus } from "@/app/lib/api/types";
import { useAppContext } from "@/app/lib/context/app-context";

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

interface ChatHeaderProps {
  threadId: string | null;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  models: ModelSelectionResponse[];
  modelsLoading: boolean;
  currentModelSelection: number | null;
  isStreaming: boolean;
  onModelChange: (id: number | null) => void;
}

export default function ChatHeader({
  threadId,
  sidebarOpen,
  onToggleSidebar,
  models,
  modelsLoading,
  currentModelSelection,
  isStreaming,
  onModelChange,
}: ChatHeaderProps) {
  const { state } = useAppContext();

  return (
    <div className="app-region-drag electron-titlebar-safe-right min-h-12 shrink-0 border-b border-border-light bg-white px-4 py-2">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="app-region-no-drag rounded-lg p-1.5 transition-colors hover:bg-surface-secondary"
          title={sidebarOpen ? "收起会话侧栏" : "展开会话侧栏"}
          aria-label={sidebarOpen ? "收起会话侧栏" : "展开会话侧栏"}
          aria-expanded={sidebarOpen}
        >
          <svg
            className="h-4 w-4 text-text-muted"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>

        <h2 className="min-w-0 flex-1 truncate font-display text-sm font-semibold text-text-primary">
          {threadId ? "AI 对话" : "新对话"}
        </h2>

        <div className="flex shrink-0 items-center gap-1.5 mr-2">
          <span
            className={`w-1.5 h-1.5 rounded-full ${statusColors[state.agentStatus]}`}
          />
          <span className="text-xs text-text-muted">
            {statusLabels[state.agentStatus]}
          </span>
        </div>

        <div className="app-region-no-drag">
          <ModelSelectionPicker
            models={models}
            loading={modelsLoading}
            value={currentModelSelection}
            disabled={isStreaming}
            onChange={onModelChange}
          />
        </div>
      </div>
    </div>
  );
}
