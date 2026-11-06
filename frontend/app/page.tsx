import { createPortal } from "react-dom";
import { useHistorySlot } from "@/app/lib/context/layout-context";
import { useMediaQuery } from "@/app/hooks/use-media-query";
import FormDrawer from "@/app/components/ui/form-drawer";
import { useState, useCallback, useEffect, useMemo, useRef } from "react";
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
import ThinkingPicker, { type ThinkingOverride } from "@/app/components/chat/thinking-picker";
import ChatSidebar from "@/app/components/chat/chat-sidebar";
import type { ModelSelectionResponse } from "@/app/lib/api/types";
import { shouldWarnForSmallerContextWindow } from "@/app/lib/chat/model-context-warning";
import { plainPreview } from "@/app/lib/chat/preview";

export default function Home() {
  const { t } = useTranslation();
  const { state } = useAppContext();
  const initialModel = useRef(state.currentModelSelection);
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
    historyLoading,
    answerInput,
    cancelRun,
    cancelQueued,
    clearMessages,
  } = useChatStream();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const desktop = useMediaQuery("(min-width: 1200px)");
  const historySlot = useHistorySlot();
  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [modelContextWindowWarning, setModelContextWindowWarning] =
    useState(false);
  const [thinkingOverride, setThinkingOverride] = useState<ThinkingOverride>();

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
        if (initialModel.current === null && data.length) setModelSelection(data[0].id);
        setModelsLoaded(true);
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
  }, [setModelSelection]);

  useEffect(() => {
    if (
      modelsLoaded &&
      state.currentModelSelection !== null &&
      !models.some((model) => model.id === state.currentModelSelection)
    )
      setModelSelection(null);
  }, [modelsLoaded, models, state.currentModelSelection, setModelSelection]);

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
          thinkingOverride,
        },
      );
    },
    [
      clearMessages,
      startChat,
      state.currentModelSelection,
      state.currentThreadId,
      thinkingOverride,
    ],
  );

  const handleSelectThread = useCallback(
    (threadId: string) => {
      setSidebarOpen(false);
      if (threadId === state.currentThreadId) return;
      setThinkingOverride(undefined);
      setModelContextWindowWarning(false);
      setThreadId(threadId || null);
      setThreadRequiresImageInput(false);
    },
    [setThreadId, setThreadRequiresImageInput, state.currentThreadId],
  );

  const handleNewChat = useCallback(() => {
    setSidebarOpen(false);
    setModelContextWindowWarning(false);
    setThinkingOverride(undefined);
    clearMessages();
    setThreadId(null);
    setThreadRequiresImageInput(false);
    setAgentStatus("idle");
  }, [clearMessages, setAgentStatus, setThreadId, setThreadRequiresImageInput]);

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
      if (id !== state.currentModelSelection) setThinkingOverride(undefined);
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
      startChat(state.currentModelSelection, prompt, state.currentThreadId, undefined, { thinkingOverride });
    },
    [
      clearMessages,
      startChat,
      state.currentModelSelection,
      state.currentThreadId,
      thinkingOverride,
    ],
  );

  const hasNoModel = state.currentModelSelection === null;
  const threadTitle = useMemo(() => {
    const firstPrompt = messages.find(
      (message) => message.role === "user" && message.content.trim(),
    )?.content;
    return firstPrompt ? plainPreview(firstPrompt).slice(0, 80) || null : null;
  }, [messages]);

  return (
    <div className="chat-page flex h-full min-h-0">
      {desktop && historySlot ? createPortal(
        <ChatSidebar
          onSelectThread={handleSelectThread}
          onNewChat={handleNewChat}
          activeThreadId={state.currentThreadId}
          chatHistoryVersion={state.chatHistoryVersion}
          onClose={handleCloseSidebar}
        />, historySlot) : <FormDrawer open={sidebarOpen} title={t("appearance.history")} onClose={handleCloseSidebar}>
        <ChatSidebar
          onSelectThread={handleSelectThread}
          onNewChat={handleNewChat}
          activeThreadId={state.currentThreadId}
          chatHistoryVersion={state.chatHistoryVersion}
          onClose={handleCloseSidebar}
        />
      </FormDrawer>}

      <div className="flex-1 flex flex-col min-w-0">
        <ChatHeader
          onNewChat={handleNewChat}
          threadId={state.currentThreadId}
          threadTitle={threadTitle}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={handleToggleSidebar}
          models={models}
          modelsLoading={modelsLoading}
          currentModelSelection={state.currentModelSelection}
          isStreaming={isStreaming}
          onModelChange={handleModelChange}
        />

        <ChatArea
          activityKey={pendingInputs.map((input) => input.request_id).join(",")}
          messages={messages}
          liveMessages={liveMessages}
          isStreaming={isStreaming}
          historyLoading={historyLoading}
          streamError={streamError}
          contextCompactionStatus={contextCompactionStatus}
          modelContextWindowWarning={modelContextWindowWarningMessage}
          threadModelMismatchMessage={threadModelMismatchMessage}
          hasNoModel={hasNoModel}
          hasConfiguredModels={models.length > 0}
          onPrompt={handleQuickPrompt}
        >
        <ChatRunPanel
          runs={runs}
          inputs={pendingInputs}
          connectionState={connectionState}
          onAnswer={answerInput}
          onCancel={cancelRun}
          onCancelQueued={cancelQueued}
        />
        </ChatArea>

        <ChatInput
          onSend={handleSend}
          onStop={stopStream}
          isStreaming={isStreaming}
          disabled={hasNoModel}
          disabledMessage={models.length ? t("appearance.chooseModel") : undefined}
          submitting={submitting}
          noticeMessage={
            threadModelMismatchMessage ?? modelContextWindowWarningMessage
          }
          trailing={
            <ThinkingPicker
              model={currentModel}
              override={thinkingOverride}
              onChange={setThinkingOverride}
              disabled={isStreaming}
            />
          }
        />
      </div>
    </div>
  );
}
