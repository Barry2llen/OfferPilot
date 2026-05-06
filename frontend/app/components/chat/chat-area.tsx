"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence } from "motion/react";
import ChatMessage, {
  StreamingAssistantMessage,
} from "@/app/components/chat/chat-message";
import ChatWelcome from "@/app/components/chat/chat-welcome";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type { ChatMessage as ChatMessageType } from "@/app/hooks/use-chat-stream";

interface ChatAreaProps {
  messages: ChatMessageType[];
  liveMessages: ChatMessageType[];
  isStreaming: boolean;
  historyLoading: boolean;
  interrupt: { interruptId: string; message: string } | null;
  streamError: string | null;
  hasNoModel: boolean;
  onRetry: () => void;
  onPrompt: (prompt: string) => void;
}

export default function ChatArea({
  messages,
  liveMessages,
  isStreaming,
  historyLoading,
  interrupt,
  streamError,
  hasNoModel,
  onRetry,
  onPrompt,
}: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAutoScrollEnabled, setIsAutoScrollEnabled] = useState(true);

  const hasAnyMessages =
    messages.length > 0 || liveMessages.length > 0 || isStreaming;

  useEffect(() => {
    if (isAutoScrollEnabled) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, liveMessages, isStreaming, interrupt, streamError, isAutoScrollEnabled]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    // If user is near the bottom (within 20px), enable auto scroll, else disable
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 20;
    setIsAutoScrollEnabled(isNearBottom);
  };

  const scrollToBottom = () => {
    setIsAutoScrollEnabled(true);
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div 
      className="flex-1 overflow-y-auto px-4 py-4 sm:px-6 relative"
      ref={containerRef}
      onScroll={handleScroll}
    >
      {historyLoading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
        </div>
      ) : !hasAnyMessages ? (
        <ChatWelcome hasNoModel={hasNoModel} onPrompt={onPrompt} />
      ) : (
        <div className="w-full">
          <AnimatePresence initial={false}>
            {messages.map((msg, index) => (
              <ChatMessage
                key={getMessageKey(msg, index)}
                message={msg}
              />
            ))}

            {liveMessages.map((msg, index) =>
              msg.role === "assistant" ? (
                <StreamingAssistantMessage
                  key={`live-assistant-${index}`}
                  content={msg.content}
                  reasoning={msg.reasoning ?? ""}
                  waiting={isStreaming && index === liveMessages.length - 1}
                />
              ) : (
                <ChatMessage
                  key={`live-${msg.toolCallId ?? msg.role}-${index}`}
                  message={msg}
                />
              )
            )}

            {isStreaming && liveMessages.length === 0 && (
              <StreamingAssistantMessage
                key="live-waiting"
                content=""
                reasoning=""
                waiting={isStreaming}
              />
            )}
          </AnimatePresence>

          {interrupt && (
            <div className="flex justify-center py-3">
              <div className="flex items-center gap-2 rounded-full bg-warning-bg px-4 py-2 text-xs text-warning-text">
                <span>Agent 已中断: {interrupt.message}</span>
                <Button variant="primary" size="sm" onClick={onRetry} pill>
                  重试
                </Button>
              </div>
            </div>
          )}

          {streamError && (
            <div className="flex justify-center py-3">
              <div className="rounded-full bg-error-bg px-4 py-2 text-xs text-error-text">
                {streamError}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Scroll to bottom button */}
      {!isAutoScrollEnabled && hasAnyMessages && (
        <div className="sticky bottom-4 flex justify-center w-full z-10 pointer-events-none">
          <button
            onClick={scrollToBottom}
            className="pointer-events-auto flex items-center gap-2 rounded-full bg-white shadow-card border border-border-default px-4 py-1.5 text-xs font-medium text-text-secondary hover:text-primary-600 hover:border-primary-200 hover:bg-primary-50 transition-all"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
            回到最新
          </button>
        </div>
      )}
    </div>
  );
}

function getMessageKey(message: ChatMessageType, index: number): string {
  return message.toolCallId ?? `${message.role}-${index}`;
}
