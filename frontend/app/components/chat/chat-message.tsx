import { useState } from "react";
import type {
  ChatMessage as ChatMessageType,
  ToolCallEntry,
} from "@/app/hooks/use-chat-stream";
import ChatAttachmentCard from "@/app/components/chat/chat-attachment-card";
import MarkdownContent from "@/app/components/chat/markdown-content";
import ToolCallCard from "@/app/components/chat/tool-call-card";

interface Props {
  message: ChatMessageType;
  streaming?: boolean;
}

const CHAT_CONTENT_CLASS = "mx-auto w-full max-w-3xl";

export default function ChatMessage({ message, streaming = false }: Props) {
  const isUser = message.role === "user";
  const isTool = message.role === "tool";
  const hasContent = Boolean(message.content.trim());
  const hasReasoning = Boolean(message.reasoning?.trim());
  const hasAttachments = Boolean(message.attachments?.length);

  if (!isUser && !isTool && !hasContent && !hasReasoning && !streaming) {
    return null;
  }

  if (isTool) {
    return (
      <ToolCallCard
        entry={{
          name: message.toolName || "unknown_tool",
          input: message.toolInput,
          output:
            message.toolStatus === "error"
              ? undefined
              : message.toolOutput ?? message.content,
          error:
            message.toolStatus === "error"
              ? message.toolError ?? message.content
              : undefined,
          status: normalizeToolStatus(message.toolStatus),
        }}
      />
    );
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    // Could add a toast here, but simple copy is fine
  };

  return (
    <div
      className="chat-message-enter group relative py-2"
    >
      <div
        className={`${CHAT_CONTENT_CLASS} flex ${isUser ? "justify-end" : "justify-start"}`}
      >
        <div
          className={`relative flex min-w-0 flex-col ${
            isUser
              ? "max-w-[min(80%,36rem)] items-end"
              : "w-full items-stretch"
          }`}
        >
          {(hasContent || !isUser) && (
            <div
              className={`max-w-full text-sm leading-relaxed ${
                isUser
                  ? "w-fit rounded-2xl rounded-br-md bg-text-charcoal px-4 py-2.5 text-white"
                  : "w-full text-text-primary"
              }`}
            >
              {!isUser && hasReasoning && message.reasoning && (
                <ReasoningDisclosure
                  content={message.reasoning}
                  durationMs={message.reasoningDurationMs}
                  active={streaming}
                  hasFollowingContent={hasContent}
                />
              )}
              {isUser ? (
                <MarkdownContent content={message.content} inverse={isUser} />
              ) : hasContent ? (
                <div className="flex items-end gap-1">
                  <MarkdownContent content={message.content} className="min-w-0 flex-1" />
                  {streaming && (
                    <span className="mb-1 inline-block h-4 w-1.5 shrink-0 animate-pulse bg-primary-500 align-middle" />
                  )}
                </div>
              ) : streaming ? (
                <WaitingIndicator label={hasReasoning ? "正在组织回复" : "正在思考"} />
              ) : null}
            </div>
          )}

          {hasAttachments && message.attachments && (
            <div
              className={`mt-2 flex flex-wrap gap-2 ${
                isUser ? "justify-end" : "justify-start"
              }`}
            >
              {message.attachments.map((attachment, index) => (
                <ChatAttachmentCard
                  key={`${attachment.fileId ?? "pending"}-${attachment.originalFilename}-${index}`}
                  attachment={attachment}
                  variant="message"
                />
              ))}
            </div>
          )}

          {hasContent && isUser && (
            <button
              type="button"
              onClick={handleCopy}
              className="absolute right-full top-1 mr-2 flex h-7 w-7 items-center justify-center rounded-md border border-border-light bg-white text-text-muted opacity-0 shadow-[0_1px_4px_rgba(15,23,42,0.08)] transition-all group-hover:opacity-100 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-600"
              title="复制文本"
              aria-label="复制文本"
            >
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </button>
          )}

          {hasContent && !isUser && (
            <div className={`mt-1.5 flex ${isUser ? "justify-end" : "justify-start"}`}>
              <button
                type="button"
                onClick={handleCopy}
                className="flex h-7 w-7 items-center justify-center rounded-md border border-border-light bg-white text-text-muted shadow-[0_1px_4px_rgba(15,23,42,0.08)] transition-colors hover:border-primary-200 hover:bg-primary-50 hover:text-primary-600"
                title="复制文本"
                aria-label="复制文本"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function normalizeToolStatus(status?: string): ToolCallEntry["status"] {
  if (status === "success" || status === "error" || status === "running") {
    return status;
  }
  return "success";
}

function ReasoningDisclosure({
  content,
  durationMs,
  active = false,
  hasFollowingContent = false,
}: {
  content: string;
  durationMs?: number;
  active?: boolean;
  hasFollowingContent?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const label = formatReasoningLabel(durationMs, active);

  return (
    <div className={`${hasFollowingContent ? "mb-2" : "mb-0"} text-text-secondary`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 py-1 text-left text-sm font-medium transition-colors hover:text-text-primary"
        aria-expanded={open}
      >
        <svg
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span>{label}</span>
      </button>
      {open && (
        <div className="mt-2 border-l border-border-default pl-4 text-sm leading-relaxed text-text-secondary">
          <MarkdownContent content={content} className="text-sm text-text-secondary" />
        </div>
      )}
    </div>
  );
}

function formatReasoningLabel(durationMs?: number, active = false): string {
  if (typeof durationMs === "number" && Number.isFinite(durationMs)) {
    if (durationMs < 1000) {
      return "思考了不足 1 秒";
    }
    return `思考了 ${Math.round(durationMs / 1000)} 秒`;
  }

  return active ? "正在思考" : "推理过程";
}

function WaitingIndicator({
  label,
  compact = false,
}: {
  label: string;
  compact?: boolean;
}) {
  return (
    <div
      className={`inline-flex items-center gap-2 text-text-secondary ${
        compact ? "text-xs" : "text-sm"
      }`}
    >
      <span>{label}</span>
      <span className="inline-flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((item) => (
          <span
            key={item}
            className="h-1.5 w-1.5 rounded-full bg-primary-500 animate-bounce"
            style={{ animationDelay: `${item * 120}ms` }}
          />
        ))}
      </span>
    </div>
  );
}
