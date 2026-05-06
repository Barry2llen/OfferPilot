"use client";

import { useEffect, useRef } from "react";
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
  const hasAnyMessages =
    messages.length > 0 || liveMessages.length > 0 || isStreaming;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveMessages, isStreaming, interrupt, streamError]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-6">
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
    </div>
  );
}

function getMessageKey(message: ChatMessageType, index: number): string {
  return message.toolCallId ?? `${message.role}-${index}`;
}
