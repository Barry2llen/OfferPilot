import { useTranslation } from "react-i18next";
import ModelSelectionPicker from "@/app/components/chat/model-selection-picker";
import ThinkingControl from "@/app/components/settings/thinking-control";
import { defaultThinkingType } from "@/app/lib/thinking";
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
  threadId: string | null;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  models: ModelSelectionResponse[];
  modelsLoading: boolean;
  currentModelSelection: number | null;
  isStreaming: boolean;
  onModelChange: (id: number | null) => void;
  thinkingOverride?: { value: string | number | null };
  onThinkingChange?: (value: { value: string | number | null }) => void;
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
  thinkingOverride,
  onThinkingChange,
}: ChatHeaderProps) {
  const { state } = useAppContext();
  const { t } = useTranslation();
  const selected = models.find((model) => model.id === currentModelSelection);
  const thinking = selected?.thinking ?? (selected ? { type: defaultThinkingType(selected.provider.provider), value: null } : null);

  return (
    <div className="app-region-drag electron-titlebar-safe-right min-h-12 shrink-0 border-b border-border-light bg-white px-4 py-2">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="app-region-no-drag rounded-lg p-1.5 transition-colors hover:bg-surface-secondary"
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

        <h2 className="min-w-0 flex-1 truncate font-display text-sm font-semibold text-text-primary">
          {threadId ? t("chat.chatTitle") : t("chat.newChat")}
        </h2>

        <div className="flex shrink-0 items-center gap-1.5 mr-2">
          <span
            className={`w-1.5 h-1.5 rounded-full ${statusColors[state.agentStatus]}`}
          />
          <span className="text-xs text-text-muted">
            {t(statusLabelKeys[state.agentStatus])}
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
        {selected && thinking && onThinkingChange && <div className="app-region-no-drag">
          <ThinkingControl provider={selected.provider.provider} value={{ ...thinking, value: thinkingOverride ? thinkingOverride.value : thinking.value }} allowType={false} disabled={isStreaming} onChange={(value) => onThinkingChange({ value: value.value })} />
        </div>}
      </div>
    </div>
  );
}
