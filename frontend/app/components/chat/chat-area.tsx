import type { ReactNode, RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ChatMessage from "@/app/components/chat/chat-message";
import ChatWelcome from "@/app/components/chat/chat-welcome";
import Spinner from "@/app/components/ui/spinner";
import type {
  ChatMessage as ChatMessageType,
  ContextCompactionStatus,
} from "@/app/lib/chat/types";

const AUTO_SCROLL_THRESHOLD_PX = 48;
const SHOW_SCROLL_BUTTON_THRESHOLD_PX = 240;

interface ChatAreaProps {
  children?: ReactNode;
  activityKey?: string;
  pendingInputRef?: RefObject<HTMLDivElement | null>;
  messages: ChatMessageType[];
  liveMessages: ChatMessageType[];
  isStreaming: boolean;
  historyLoading: boolean;
  streamError: string | null;
  contextCompactionStatus: ContextCompactionStatus;
  modelContextWindowWarning: string | null;
  threadModelMismatchMessage: string | null;
  hasNoModel: boolean;
  hasConfiguredModels?: boolean;
  onPrompt: (prompt: string) => void;
}

export default function ChatArea({
  children,
  activityKey,
  pendingInputRef,
  messages,
  liveMessages,
  isStreaming,
  historyLoading,
  streamError,
  contextCompactionStatus,
  modelContextWindowWarning,
  threadModelMismatchMessage,
  hasNoModel,
  hasConfiguredModels,
  onPrompt,
}: ChatAreaProps) {
  const { t } = useTranslation();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAutoScrollEnabled, setIsAutoScrollEnabled] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [visiblePendingKey, setVisiblePendingKey] = useState<string | null>(null);

  useEffect(() => {
    const target = pendingInputRef?.current;
    const root = containerRef.current;
    if (!activityKey || !target || !root || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => {
      setVisiblePendingKey(entry?.isIntersecting ? activityKey : null);
    }, { root });
    observer.observe(target);
    return () => observer.disconnect();
  }, [activityKey, pendingInputRef]);

  const hasAnyMessages =
    messages.length > 0 ||
    liveMessages.length > 0 ||
    isStreaming ||
    contextCompactionStatus !== "idle" ||
    Boolean(modelContextWindowWarning);

  useEffect(() => {
    if (isAutoScrollEnabled) {
      messagesEndRef.current?.scrollIntoView({
        behavior: isStreaming || matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      });
    }
  }, [
    activityKey,
    messages,
    liveMessages,
    isStreaming,
    streamError,
    contextCompactionStatus,
    isAutoScrollEnabled,
  ]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    setIsAutoScrollEnabled(distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX);
    setShowScrollToBottom(
      distanceFromBottom >= SHOW_SCROLL_BUTTON_THRESHOLD_PX,
    );
  };

  const scrollToBottom = () => {
    setIsAutoScrollEnabled(true);
    setShowScrollToBottom(false);
    messagesEndRef.current?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  };

  const scrollToPendingInput = () => {
    const target = pendingInputRef?.current;
    target?.scrollIntoView({
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "start",
    });
    target?.focus({ preventScroll: true });
  };

  const showPendingInputJump = Boolean(activityKey && pendingInputRef && visiblePendingKey !== activityKey);
  const showJump = showPendingInputJump || (showScrollToBottom && hasAnyMessages);
  const jumpLabel = t(showPendingInputJump ? "chat.viewPendingInput" : "chat.returnToLatest");

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        className="chat-scroll min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6"
        ref={containerRef}
        onScroll={handleScroll}
      >
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col">
        {historyLoading ? (
          <div className="flex items-center justify-center py-20">
            <Spinner size="lg" />
          </div>
        ) : !hasAnyMessages ? (
          <div className="flex flex-1 flex-col">
            <ChatWelcome
              hasNoModel={hasNoModel}
              hasConfiguredModels={hasConfiguredModels}
              onPrompt={onPrompt}
            />
          </div>
        ) : (
          <div>
            {modelContextWindowWarning && (
              <div
                className="mb-4 rounded-2xl bg-warning-bg px-4 py-3 text-sm text-warning-text"
                role="alert"
                aria-live="polite"
              >
                {modelContextWindowWarning}
              </div>
            )}

            {contextCompactionStatus !== "idle" && (
              <div
                className={`mb-4 rounded-2xl px-4 py-3 text-sm ${
                  contextCompactionStatus === "failed"
                    ? "bg-error-bg text-error-text"
                    : contextCompactionStatus === "running"
                      ? "bg-primary-50 text-primary-700"
                      : "bg-success-bg text-success-text"
                }`}
                role="status"
                aria-live="polite"
              >
                {contextCompactionStatus === "running"
                  ? t("chat.contextCompacting")
                  : contextCompactionStatus === "failed"
                    ? t("chat.contextCompactionFailed")
                    : t("chat.contextCompacted")}
              </div>
            )}

            {messages.map((msg, index) => (
              <ChatMessage key={getMessageKey(msg, index)} message={msg} />
            ))}

            {liveMessages.map((msg, index) => (
              <ChatMessage
                key={getMessageKey(msg, index)}
                message={msg}
                streaming={
                  msg.role === "assistant" &&
                  isStreaming &&
                  index === liveMessages.length - 1
                }
              />
            ))}

            {isStreaming && liveMessages.length === 0 && (
              <ChatMessage
                key="live-waiting"
                message={{ id: "live-waiting", role: "assistant", content: "" }}
                streaming
              />
            )}
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

        {children}
        <div ref={messagesEndRef} />
      </div>

      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-3 z-10 flex justify-center" aria-live="polite">
        {showJump && (
          <button
            type="button"
            onClick={showPendingInputJump ? scrollToPendingInput : scrollToBottom}
            className={`pointer-events-auto flex h-10 items-center justify-center gap-2 rounded-full bg-surface-primary shadow-card border border-border-default text-text-secondary hover:text-primary-600 hover:border-primary-200 hover:bg-primary-50 transition-all ${showPendingInputJump ? "px-4 text-sm font-medium" : "w-10"}`}
            aria-label={jumpLabel}
            title={jumpLabel}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 14l-7 7m0 0l-7-7m7 7V3"
              />
            </svg>
            {showPendingInputJump && <span>{jumpLabel}</span>}
          </button>
        )}
      </div>
    </div>
  );
}

function getMessageKey(message: ChatMessageType, index: number): string {
  return message.id || message.toolCallId || `${message.role}-${index}`;
}
