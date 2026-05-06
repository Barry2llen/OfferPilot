"use client";

import { useState, useCallback, useEffect } from "react";
import { aiChatApi } from "@/app/lib/api/ai";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAppContext, useAppActions } from "@/app/lib/context/app-context";
import { useChatStream } from "@/app/hooks/use-chat-stream";
import ChatArea from "@/app/components/chat/chat-area";
import ChatHeader from "@/app/components/chat/chat-header";
import ChatInput from "@/app/components/chat/chat-input";
import ChatSidebar from "@/app/components/chat/chat-sidebar";
import type { ModelSelectionResponse } from "@/app/lib/api/types";

export default function Home() {
  const { state } = useAppContext();
  const { setThreadId, setModelSelection } = useAppActions();

  const {
    messages,
    liveMessages,
    interrupt,
    streamError,
    isStreaming,
    startChat,
    stopStream,
    retry,
    loadHistory,
    clearMessages,
    resetStreamingState,
  } = useChatStream();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);

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
    (prompt: string) => {
      if (!state.currentModelSelection) return;
      if (!state.currentThreadId) {
        clearMessages();
      }
      startChat(state.currentModelSelection, prompt, state.currentThreadId);
    },
    [state.currentModelSelection, state.currentThreadId, startChat, clearMessages]
  );

  const handleRetry = useCallback(() => {
    if (!state.currentModelSelection || !state.currentThreadId) return;
    retry(state.currentModelSelection, state.currentThreadId);
  }, [state.currentModelSelection, state.currentThreadId, retry]);

  const handleSelectThread = useCallback(
    async (threadId: string) => {
      stopStream();
      if (!threadId) {
        resetStreamingState();
        clearMessages();
        setThreadId(null);
        return;
      }
      setHistoryLoading(true);
      setThreadId(threadId);
      try {
        const history = await aiChatApi.getHistory(threadId);
        loadHistory(history.messages);
      } catch {
        resetStreamingState();
        clearMessages();
        setThreadId(null);
      } finally {
        setHistoryLoading(false);
      }
    },
    [clearMessages, loadHistory, resetStreamingState, setThreadId, stopStream]
  );

  const handleQuickPrompt = useCallback(
    (prompt: string) => {
      if (!state.currentModelSelection) return;
      if (!state.currentThreadId) {
        clearMessages();
      }
      startChat(state.currentModelSelection, prompt, state.currentThreadId);
    },
    [state.currentModelSelection, state.currentThreadId, startChat, clearMessages]
  );

  const hasNoModel = state.currentModelSelection === null;

  return (
    <div className="flex h-full">
      {sidebarOpen && (
        <ChatSidebar
          onSelectThread={handleSelectThread}
          activeThreadId={state.currentThreadId}
        />
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <ChatHeader
          threadId={state.currentThreadId}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen((open) => !open)}
          models={models}
          modelsLoading={modelsLoading}
          currentModelSelection={state.currentModelSelection}
          isStreaming={isStreaming}
          onModelChange={setModelSelection}
        />

        <ChatArea
          messages={messages}
          liveMessages={liveMessages}
          isStreaming={isStreaming}
          historyLoading={historyLoading}
          interrupt={interrupt}
          streamError={streamError}
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
        />
      </div>
    </div>
  );
}
