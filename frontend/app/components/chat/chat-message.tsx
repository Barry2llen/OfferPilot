"use client";

import { useState } from "react";
import type {
  ChatMessage as ChatMessageType,
  ToolCallEntry,
} from "@/app/hooks/use-chat-stream";
import MarkdownContent from "@/app/components/chat/markdown-content";
import ToolCallCard from "@/app/components/chat/tool-call-card";

interface Props {
  message: ChatMessageType;
}

interface StreamingAssistantMessageProps {
  content: string;
  reasoning: string;
  waiting: boolean;
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const isTool = message.role === "tool";

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

  return (
    <div className={`flex py-2 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[min(80%,48rem)] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-text-charcoal text-white rounded-br-md"
            : "bg-surface-secondary text-text-primary rounded-bl-md"
        }`}
      >
        {!isUser && message.reasoning && (
          <ReasoningDisclosure content={message.reasoning} />
        )}
        <MarkdownContent content={message.content} inverse={isUser} />
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

export function StreamingAssistantMessage({
  content,
  reasoning,
  waiting,
}: StreamingAssistantMessageProps) {
  return (
    <div className="flex justify-start py-2">
      <div className="max-w-[min(80%,48rem)] rounded-2xl rounded-bl-md bg-surface-secondary px-4 py-2.5 text-sm leading-relaxed text-text-primary">
        {reasoning && <ReasoningDisclosure content={reasoning} />}
        {content ? (
          <div className="flex items-end gap-1">
            <MarkdownContent content={content} className="min-w-0 flex-1" />
            <span className="mb-1 inline-block h-4 w-1.5 shrink-0 animate-pulse bg-primary-500 align-middle" />
          </div>
        ) : waiting ? (
          <WaitingIndicator label={reasoning ? "正在组织回复" : "正在思考"} />
        ) : null}
      </div>
    </div>
  );
}

function ReasoningDisclosure({ content }: { content: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mb-2 rounded-xl border border-border-light bg-white/70">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-text-secondary hover:text-text-primary"
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
        <span>推理过程</span>
      </button>
      {open && (
        <div className="border-t border-border-light px-3 py-2 text-xs leading-relaxed text-text-secondary">
          <MarkdownContent content={content} className="text-xs" />
        </div>
      )}
    </div>
  );
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
