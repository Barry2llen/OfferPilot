"use client";

import { useState } from "react";
import { motion } from "motion/react";
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

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    // Could add a toast here, but simple copy is fine
  };

  return (
    <motion.div
      className={`flex py-2 group relative ${isUser ? "justify-end" : "justify-start"}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <div
        className={`relative flex max-w-[min(80%,48rem)] flex-col pb-6 ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        <div
          className={`w-fit max-w-full rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "rounded-br-md bg-text-charcoal text-white"
              : "rounded-bl-md bg-surface-secondary text-text-primary"
          }`}
        >
          {!isUser && message.reasoning && (
            <ReasoningDisclosure content={message.reasoning} />
          )}
          <MarkdownContent content={message.content} inverse={isUser} />
        </div>

        <div
          className={`absolute bottom-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-center bg-white shadow-sm border border-border-light rounded-lg p-1 z-10 ${
            isUser ? "right-0" : "left-0"
          }`}
        >
          <button
            onClick={handleCopy}
            className="p-1 rounded text-text-muted hover:text-primary-600 hover:bg-primary-50 transition-colors"
            title="复制文本"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </div>
    </motion.div>
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
    <motion.div
      className="flex justify-start py-2"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <div className="max-w-[min(80%,48rem)] rounded-2xl rounded-bl-md bg-surface-secondary px-4 py-2.5 text-sm leading-relaxed text-text-primary">
        {reasoning && <ReasoningDisclosure content={reasoning} />}
        {content ? (
          <div className="flex items-end gap-1">
            <MarkdownContent content={content} className="min-w-0 flex-1" />
            {waiting && (
              <span className="mb-1 inline-block h-4 w-1.5 shrink-0 animate-pulse bg-primary-500 align-middle" />
            )}
          </div>
        ) : waiting ? (
          <WaitingIndicator label={reasoning ? "正在组织回复" : "正在思考"} />
        ) : null}
      </div>
    </motion.div>
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
