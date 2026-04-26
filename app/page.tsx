"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { aiChatApi } from "@/app/lib/api/ai";
import { useAppContext, useAppActions } from "@/app/lib/context/app-context";
import { useChatStream } from "@/app/hooks/use-chat-stream";
import ChatMessage from "@/app/components/chat/chat-message";
import ChatInput from "@/app/components/chat/chat-input";
import ChatSidebar from "@/app/components/chat/chat-sidebar";
import ContextPanel from "@/app/components/chat/context-panel";
import AgentTimeline from "@/app/components/chat/agent-timeline";
import QuickTasks from "@/app/components/chat/quick-tasks";
import Button from "@/app/components/ui/button";
import Badge from "@/app/components/ui/badge";
import Spinner from "@/app/components/ui/spinner";

export default function Home() {
  const { state, dispatch } = useAppContext();
  const { setThreadId } = useAppActions();

  const {
    messages,
    streamingText,
    toolCalls,
    interrupt,
    streamError,
    isStreaming,
    startChat,
    stopStream,
    retry,
    loadHistory,
    clearMessages,
    setMessages,
  } = useChatStream();

  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const handleSend = useCallback(
    (prompt: string) => {
      if (!state.currentModelSelection) return;
      clearMessages();
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
      if (!threadId) {
        clearMessages();
        setThreadId(null);
        setActiveThreadId(null);
        return;
      }
      setHistoryLoading(true);
      setThreadId(threadId);
      setActiveThreadId(threadId);
      try {
        const history = await aiChatApi.getHistory(threadId);
        loadHistory(history.messages);
      } catch {
        // ignore
      } finally {
        setHistoryLoading(false);
      }
    },
    [clearMessages, loadHistory, setThreadId]
  );

  const handleQuickPrompt = useCallback(
    (prompt: string) => {
      if (!state.currentModelSelection) return;
      clearMessages();
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
          activeThreadId={activeThreadId}
        />
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat header */}
        <div className="h-12 border-b border-border-light flex items-center px-4 gap-2 bg-white shrink-0">
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
            {activeThreadId
              ? "AI 对话"
              : "新对话"}
          </h2>
          <button
            onClick={() => setPanelOpen(!panelOpen)}
            className="p-1.5 rounded-lg hover:bg-surface-secondary transition-colors"
            title="Toggle context panel"
          >
            <svg className="w-4 h-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
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
                  : "输入求职相关任务，AI Agent 将基于简历和上下文为你提供帮助"}
              </p>
              {hasNoModel ? (
                <a href="/settings/providers">
                  <Button>前往配置模型</Button>
                </a>
              ) : (
                <QuickTasks onPrompt={handleQuickPrompt} disabled={isStreaming} />
              )}
            </div>
          ) : (
            <div className="max-w-3xl mx-auto">
              {messages.map((msg, i) => (
                <ChatMessage key={i} message={msg} />
              ))}

              {/* Streaming text */}
              {streamingText && (
                <div className="flex gap-3 py-2">
                  <div className="w-7 h-7 rounded-full bg-brand-blue/10 flex items-center justify-center shrink-0 mt-0.5">
                    <svg className="w-3.5 h-3.5 text-brand-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <div className="max-w-[80%] rounded-2xl px-4 py-2.5 text-sm bg-surface-secondary text-text-primary rounded-bl-md">
                    <span className="whitespace-pre-wrap">{streamingText}</span>
                    <span className="inline-block w-1.5 h-4 bg-primary-500 animate-pulse ml-0.5 align-middle" />
                  </div>
                </div>
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
        <AgentTimeline toolCalls={toolCalls} streamingText={streamingText} />

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

      {/* Context Panel (right) */}
      {panelOpen && <ContextPanel />}
    </div>
  );
}
