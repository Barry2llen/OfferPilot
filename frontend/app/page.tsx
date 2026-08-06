import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { aiChatApi } from "@/app/lib/api/ai";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAppContext, useAppActions } from "@/app/lib/context/app-context";
import { useChatStream } from "@/app/hooks/use-chat-stream";
import ChatArea from "@/app/components/chat/chat-area";
import ChatHeader from "@/app/components/chat/chat-header";
import ChatInput, {
  type ChatComposerPayload,
} from "@/app/components/chat/chat-input";
import ChatSidebar from "@/app/components/chat/chat-sidebar";
import type { ModelSelectionResponse, QueryChoice } from "@/app/lib/api/types";

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
    interrupt,
    streamError,
    isStreaming,
    contextCompactionStatus,
    startChat,
    stopStream,
    retry,
    answerQuery,
    loadHistory,
    clearMessages,
    resetStreamingState,
  } = useChatStream();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);

  const currentModel = models.find(
    (model) => model.id === state.currentModelSelection
  );
  const threadModelMismatchMessage =
    state.currentThreadRequiresImageInput &&
    currentModel?.supports_image_input === false
      ? t("chat.threadImageMismatch")
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
        }
      );
    },
    [
      clearMessages,
      startChat,
      state.currentModelSelection,
      state.currentThreadId,
    ]
  );

  const handleRetry = useCallback(() => {
    if (!state.currentModelSelection || !state.currentThreadId) return;
    retry(state.currentModelSelection, state.currentThreadId);
  }, [
    retry,
    state.currentModelSelection,
    state.currentThreadId,
  ]);

  const handleAnswerQuery = useCallback(
    (choice: QueryChoice, note?: string | null) => {
      if (!state.currentModelSelection || !state.currentThreadId) return;
      answerQuery(state.currentModelSelection, state.currentThreadId, choice, note);
    },
    [
      answerQuery,
      state.currentModelSelection,
      state.currentThreadId,
    ]
  );

  const handleSelectThread = useCallback(
    async (threadId: string) => {
      stopStream();
      if (!threadId) {
        resetStreamingState();
        clearMessages();
        setThreadId(null);
        setThreadRequiresImageInput(false);
        return;
      }
      setHistoryLoading(true);
      setThreadId(threadId);
      try {
        const history = await aiChatApi.getHistory(threadId);
        setThreadRequiresImageInput(history.requires_image_input);
        loadHistory(history.messages, history.context_compacted);
      } catch {
        resetStreamingState();
        clearMessages();
        setThreadId(null);
        setThreadRequiresImageInput(false);
      } finally {
        setHistoryLoading(false);
      }
    },
    [
      clearMessages,
      loadHistory,
      resetStreamingState,
      setThreadId,
      setThreadRequiresImageInput,
      stopStream,
    ]
  );

  const handleNewChat = useCallback(() => {
    stopStream();
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
    stopStream,
  ]);

  const handleCloseSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((open) => !open);
  }, []);

  const handleModelChange = useCallback(
    (id: number | null) => {
      setModelSelection(id);
    },
    [setModelSelection]
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
    ]
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
          interrupt={interrupt}
          streamError={streamError}
          contextCompactionStatus={contextCompactionStatus}
          threadModelMismatchMessage={threadModelMismatchMessage}
          hasNoModel={hasNoModel}
          onRetry={handleRetry}
          onPrompt={handleQuickPrompt}
        />

        <ChatInput
          onSend={handleSend}
          onStop={stopStream}
          onRetry={handleRetry}
          isStreaming={isStreaming}
          isInterrupted={!!interrupt}
          disabled={hasNoModel}
          noticeMessage={threadModelMismatchMessage}
          interrupt={interrupt}
          onAnswerQuery={handleAnswerQuery}
        />
      </div>
    </div>
  );
}
