import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import ModelSelectionPicker from "@/app/components/chat/model-selection-picker";
import type { ModelSelectionResponse, AgentStatus } from "@/app/lib/api/types";
import { useAppContext } from "@/app/lib/context/app-context";

const statusLabelKeys: Record<AgentStatus, string> = {
  idle: "chat.ready",
  generating: "chat.generating",
  compacting: "chat.compacting",
  tool_calling: "chat.toolCalling",
  interrupted: "chat.interrupted",
  waiting_input: "chatRuns.waitingInput",
  error: "chat.error",
};

const statusColors: Record<AgentStatus, string> = {
  idle: "bg-success-text",
  generating: "bg-primary-500 animate-pulse",
  compacting: "bg-violet-500 animate-pulse",
  tool_calling: "bg-sky-blue animate-pulse",
  interrupted: "bg-warning-text",
  waiting_input: "bg-warning-text",
  error: "bg-error-text",
};

interface ChatHeaderProps {
  onNewChat: () => void;
  threadId: string | null;
  /** Short label for the open conversation, derived from its first prompt. */
  threadTitle?: string | null;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  models: ModelSelectionResponse[];
  modelsLoading: boolean;
  currentModelSelection: number | null;
  isStreaming: boolean;
  onModelChange: (id: number | null) => void;
}

export default function ChatHeader({
  onNewChat,
  threadId,
  threadTitle,
  sidebarOpen,
  onToggleSidebar,
  models,
  modelsLoading,
  currentModelSelection,
  isStreaming,
  onModelChange,
}: ChatHeaderProps) {
  const { state } = useAppContext();
  const { t } = useTranslation();

  return (
    <div className="app-region-drag electron-titlebar-safe-right chat-header shrink-0 border-b border-border-light bg-surface-primary">
      <div className="chat-header-row">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="history-toggle app-region-no-drag icon-button transition-colors hover:bg-surface-secondary"
          title={sidebarOpen ? t("nav.collapse") : t("nav.expand")}
          aria-label={sidebarOpen ? t("nav.collapse") : t("nav.expand")}
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

        <h2
          className="min-w-0 flex-1 truncate font-display text-sm font-semibold text-text-primary"
          title={threadId && threadTitle ? threadTitle : undefined}
        >
          {threadId ? threadTitle || t("chat.chatTitle") : t("chat.newChat")}
        </h2>

        <button type="button" className="icon-button app-region-no-drag" aria-label={t("chat.newChat")} title={t("chat.newChat")} onClick={onNewChat}><Plus size={20} /></button>
        <div className="chat-model-controls app-region-no-drag">

        <div className="app-region-no-drag">
          <ModelSelectionPicker
            compact
            models={models}
            loading={modelsLoading}
            value={currentModelSelection}
            disabled={isStreaming}
            onChange={onModelChange}
          />
        </div>
        <div className="chat-status flex shrink-0 items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full ${statusColors[state.agentStatus]}`}
          />
          <span className="text-xs text-text-muted">
            {t(statusLabelKeys[state.agentStatus])}
          </span>
        </div>
        </div>
      </div>
    </div>
  );
}
