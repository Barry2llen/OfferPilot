import { useEffect, useRef, useState } from "react";
import ChatMessage from "@/app/components/chat/chat-message";
import ChatWelcome from "@/app/components/chat/chat-welcome";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type {
  ChatInterrupt,
  ChatMessage as ChatMessageType,
} from "@/app/hooks/use-chat-stream";

const AUTO_SCROLL_THRESHOLD_PX = 48;
const SHOW_SCROLL_BUTTON_THRESHOLD_PX = 240;

interface ChatAreaProps {
  messages: ChatMessageType[];
  liveMessages: ChatMessageType[];
  isStreaming: boolean;
  historyLoading: boolean;
  interrupt: ChatInterrupt | null;
  streamError: string | null;
  threadModelMismatchMessage: string | null;
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
  threadModelMismatchMessage,
  hasNoModel,
  onRetry,
  onPrompt,
}: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAutoScrollEnabled, setIsAutoScrollEnabled] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);

  const hasAnyMessages =
    messages.length > 0 || liveMessages.length > 0 || isStreaming;

  useEffect(() => {
    if (isAutoScrollEnabled) {
      messagesEndRef.current?.scrollIntoView({
        behavior: isStreaming ? "auto" : "smooth",
      });
    }
  }, [messages, liveMessages, isStreaming, interrupt, streamError, isAutoScrollEnabled]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    setIsAutoScrollEnabled(distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX);
    setShowScrollToBottom(
      distanceFromBottom >= SHOW_SCROLL_BUTTON_THRESHOLD_PX
    );
  };

  const scrollToBottom = () => {
    setIsAutoScrollEnabled(true);
    setShowScrollToBottom(false);
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
          <>
            {messages.map((msg, index) => (
              <ChatMessage
                key={getMessageKey(msg, index)}
                message={msg}
              />
            ))}

            {liveMessages.map((msg, index) =>
              <ChatMessage
                key={getMessageKey(msg, index)}
                message={msg}
                streaming={
                  msg.role === "assistant" &&
                  isStreaming &&
                  index === liveMessages.length - 1
                }
              />
            )}

            {isStreaming && liveMessages.length === 0 && (
              <ChatMessage
                key="live-waiting"
                message={{ id: "live-waiting", role: "assistant", content: "" }}
                streaming
              />
            )}
          </>

          {interrupt && interrupt.type !== "query" && (
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

          {threadModelMismatchMessage && (
            <div className="flex justify-center py-3">
              <div className="rounded-2xl bg-warning-bg px-4 py-3 text-xs text-warning-text">
                {threadModelMismatchMessage}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Scroll to bottom button */}
      {showScrollToBottom && hasAnyMessages && (
        <div className="sticky bottom-3 flex justify-center w-full z-10 pointer-events-none">
          <button
            onClick={scrollToBottom}
            className="pointer-events-auto flex h-10 w-10 items-center justify-center rounded-full bg-white shadow-card border border-border-default text-text-secondary hover:text-primary-600 hover:border-primary-200 hover:bg-primary-50 transition-all"
            aria-label="回到最新"
            title="回到最新"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

function getMessageKey(message: ChatMessageType, index: number): string {
  return message.id || message.toolCallId || `${message.role}-${index}`;
}
