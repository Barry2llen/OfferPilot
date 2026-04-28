"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { aiChatApi } from "@/app/lib/api/ai";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAppContext, useAppActions } from "@/app/lib/context/app-context";
import { useChatStream } from "@/app/hooks/use-chat-stream";
import ChatMessage, {
  StreamingAssistantMessage,
} from "@/app/components/chat/chat-message";
import ChatInput from "@/app/components/chat/chat-input";
import ChatSidebar from "@/app/components/chat/chat-sidebar";
import AgentTimeline from "@/app/components/chat/agent-timeline";
import ModelSelectionPicker from "@/app/components/chat/model-selection-picker";
import QuickTasks from "@/app/components/chat/quick-tasks";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type { ModelSelectionResponse } from "@/app/lib/api/types";

export default function Home() {
  const { state } = useAppContext();
  const { setThreadId, setModelSelection } = useAppActions();

  const {
    messages,
    streamingText,
    streamingReasoning,
    toolCalls,
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
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, streamingReasoning]);

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
      {/* Chat Sidebar (left) */}
      {sidebarOpen && (
        <ChatSidebar
          onSelectThread={handleSelectThread}
          activeThreadId={state.currentThreadId}
        />
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat header */}
        <div className="min-h-12 border-b border-border-light flex flex-wrap items-center px-4 py-2 gap-3 bg-white shrink-0">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 rounded-lg hover:bg-surface-secondary transition-colors"
            title="Toggle sidebar"
          >
            <svg className="w-4 h-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <h2 className="font-display text-sm font-semibold text-text-primary truncate flex-1">
            {state.currentThreadId
              ? "AI 对话"
              : "新对话"}
          </h2>
          <ModelSelectionPicker
            models={models}
            loading={modelsLoading}
            value={state.currentModelSelection}
            disabled={isStreaming}
            onChange={setModelSelection}
          />
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {historyLoading ? (
            <div className="flex items-center justify-center py-20">
              <Spinner size="lg" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <div className="w-14 h-14 rounded-full bg-brand-blue/10 flex items-center justify-center mb-4">
                <svg className="w-7 h-7 text-brand-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h1 className="font-display text-xl font-semibold text-text-primary mb-2">
                OfferPilot AI 求职助手
              </h1>
              <p className="text-sm text-text-secondary mb-6 max-w-md">
                {hasNoModel
                  ? "请先配置模型供应商和模型选择，然后开始对话"
                  : "输入求职相关任务，开始一轮新的 AI 对话或继续当前会话"}
              </p>
              {hasNoModel ? (
                <Link
                  href="/settings/providers"
                  className={buttonClassName()}
                >
                  前往配置模型
                </Link>
              ) : (
                <QuickTasks onPrompt={handleQuickPrompt} disabled={isStreaming} />
              )}
            </div>
          ) : (
            <div className="max-w-3xl mx-auto">
              {messages.map((msg, i) => (
                <ChatMessage key={i} message={msg} />
              ))}

              {/* Streaming assistant message */}
              {(isStreaming || streamingText || streamingReasoning) && (
                <StreamingAssistantMessage
                  content={streamingText}
                  reasoning={streamingReasoning}
                  waiting={isStreaming}
                />
              )}

              {/* Interrupt message */}
              {interrupt && (
                <div className="flex justify-center py-3">
                  <div className="bg-warning-bg text-warning-text text-xs px-4 py-2 rounded-full flex items-center gap-2">
                    <span>Agent 已中断: {interrupt.message}</span>
                    <Button variant="primary" size="sm" onClick={handleRetry} pill>
                      重试
                    </Button>
                  </div>
                </div>
              )}

              {/* Stream error */}
              {streamError && (
                <div className="flex justify-center py-3">
                  <div className="bg-error-bg text-error-text text-xs px-4 py-2 rounded-full">
                    {streamError}
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Agent timeline */}
        <AgentTimeline
          toolCalls={toolCalls}
          streamingText={streamingText}
          isStreaming={isStreaming}
        />

        {/* Input */}
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
