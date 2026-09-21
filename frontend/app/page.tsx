import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAppContext, useAppActions } from "@/app/lib/context/app-context";
import { useChatStream } from "@/app/hooks/use-chat-stream";
import ChatArea from "@/app/components/chat/chat-area";
import ChatHeader from "@/app/components/chat/chat-header";
import ChatInput, {
  type ChatComposerPayload,
} from "@/app/components/chat/chat-input";
import ChatRunPanel from "@/app/components/chat/chat-run-panel";
import ChatSidebar from "@/app/components/chat/chat-sidebar";
import type { ModelSelectionResponse } from "@/app/lib/api/types";
import { shouldWarnForSmallerContextWindow } from "@/app/lib/chat/model-context-warning";

export default function Home() {
  const { t } = useTranslation();
  const { state } = useAppContext();
  const {
    setThreadId,
    setThreadRequiresImageInput,
    setModelSelection,
    setAgentStatus,
  } = useAppActions();

  const {
    messages,
    liveMessages,
    streamError,
    isStreaming,
    contextCompactionStatus,
    startChat,
    stopStream,
    runs,
    pendingInputs,
    connectionState,
    submitting,
    answerInput,
    cancelRun,
    cancelQueued,
    disconnect,
    clearMessages,
    resetStreamingState,
  } = useChatStream();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const historyLoading = false;
  const [modelContextWindowWarning, setModelContextWindowWarning] =
    useState(false);

  const currentModel = models.find(
    (model) => model.id === state.currentModelSelection,
  );
  const threadModelMismatchMessage =
    state.currentThreadRequiresImageInput &&
    currentModel?.supports_image_input === false
      ? t("chat.threadImageMismatch")
      : null;
  const modelContextWindowWarningMessage = modelContextWindowWarning
    ? t("chat.modelContextWindowWarning")
    : null;

  useEffect(() => {
    let mounted = true;

    modelSelectionsApi
      .list()
      .then((data) => {
        if (!mounted) return;
        setModels(data);
      })
      .catch(() => {
        if (!mounted) return;
        setModels([]);
      })
      .finally(() => {
        if (!mounted) return;
        setModelsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const handleSend = useCallback(
    (payload: ChatComposerPayload, onAccepted: () => void) => {
      if (!state.currentModelSelection) return;
      if (!state.currentThreadId) {
        clearMessages();
      }
      startChat(
        state.currentModelSelection,
        payload.prompt,
        state.currentThreadId,
        undefined,
        {
          localFiles: payload.localFiles,
          fileIds: payload.fileIds,
          draftAttachments: payload.draftAttachments,
          onAccepted,
        },
      );
    },
    [
      clearMessages,
      startChat,
      state.currentModelSelection,
      state.currentThreadId,
    ],
  );

  const handleSelectThread = useCallback(
    async (threadId: string) => {
      disconnect();
      setModelContextWindowWarning(false);
      setThreadId(threadId || null);
      setThreadRequiresImageInput(false);
    },
    [setThreadId, setThreadRequiresImageInput, disconnect],
  );

  const handleNewChat = useCallback(() => {
    disconnect();
    setModelContextWindowWarning(false);
    resetStreamingState();
    clearMessages();
    setThreadId(null);
    setThreadRequiresImageInput(false);
    setAgentStatus("idle");
  }, [
    clearMessages,
    resetStreamingState,
    setAgentStatus,
    setThreadId,
    setThreadRequiresImageInput,
    disconnect,
  ]);

  const handleCloseSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((open) => !open);
  }, []);

  const handleModelChange = useCallback(
    (id: number | null) => {
      const previousModel = models.find(
        (model) => model.id === state.currentModelSelection,
      );
      const nextModel = models.find((model) => model.id === id);
      setModelSelection(id);
      setModelContextWindowWarning(
        shouldWarnForSmallerContextWindow(
          Boolean(state.currentThreadId && messages.length > 0),
          previousModel ?? null,
          nextModel ?? null,
        ),
      );
    },
    [
      messages.length,
      models,
      setModelSelection,
      state.currentModelSelection,
      state.currentThreadId,
    ],
  );

  const handleQuickPrompt = useCallback(
    (prompt: string) => {
      if (!state.currentModelSelection) return;
      if (!state.currentThreadId) {
        clearMessages();
      }
      startChat(state.currentModelSelection, prompt, state.currentThreadId);
    },
    [
      clearMessages,
      startChat,
      state.currentModelSelection,
      state.currentThreadId,
    ],
  );

  const hasNoModel = state.currentModelSelection === null;

  return (
    <div className="flex h-full">
      {sidebarOpen && (
        <ChatSidebar
          onSelectThread={handleSelectThread}
          onNewChat={handleNewChat}
          activeThreadId={state.currentThreadId}
          chatHistoryVersion={state.chatHistoryVersion}
          onClose={handleCloseSidebar}
        />
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <ChatHeader
          threadId={state.currentThreadId}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={handleToggleSidebar}
          models={models}
          modelsLoading={modelsLoading}
          currentModelSelection={state.currentModelSelection}
          isStreaming={isStreaming}
          onModelChange={handleModelChange}
        />

        <ChatArea
          messages={messages}
          liveMessages={liveMessages}
          isStreaming={isStreaming}
          historyLoading={historyLoading}
          streamError={streamError}
          contextCompactionStatus={contextCompactionStatus}
          modelContextWindowWarning={modelContextWindowWarningMessage}
          threadModelMismatchMessage={threadModelMismatchMessage}
          hasNoModel={hasNoModel}
          onPrompt={handleQuickPrompt}
        />

        <ChatRunPanel
          runs={runs}
          inputs={pendingInputs}
          connectionState={connectionState}
          onAnswer={answerInput}
          onCancel={cancelRun}
          onCancelQueued={cancelQueued}
        />
        <ChatInput
          onSend={handleSend}
          onStop={stopStream}
          isStreaming={isStreaming}
          disabled={hasNoModel || submitting}
          noticeMessage={
            threadModelMismatchMessage ?? modelContextWindowWarningMessage
          }
        />
      </div>
    </div>
  );
}
