"use client";

import { useState } from "react";
import type { ChatMessage as ChatMessageType } from "@/app/hooks/use-chat-stream";

interface Props {
  message: ChatMessageType;
}

export default function ChatMessage({ message }: Props) {
  const [expanded, setExpanded] = useState(false);

  const isUser = message.role === "user";
  const isTool = message.role === "tool";

  if (isTool) {
    return (
      <div className="flex justify-center py-1">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-text-muted bg-surface-secondary px-3 py-1.5 rounded-full hover:bg-border-default transition-colors inline-flex items-center gap-1.5"
        >
          <svg
            className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          工具: {message.toolName || "unknown"}
          {message.toolStatus && (
            <span
              className={
                message.toolStatus === "success"
                  ? "text-success-text"
                  : message.toolStatus === "error"
                    ? "text-error-text"
                    : "text-text-muted"
              }
            >
              {message.toolStatus === "success" ? " ✓" : message.toolStatus === "error" ? " ✗" : " ..."}
            </span>
          )}
        </button>
        {expanded && (
          <div className="mt-2 w-full max-w-lg bg-surface-secondary rounded-2xl p-3 text-xs font-mono text-text-secondary whitespace-pre-wrap break-all">
            {message.content}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={`flex gap-3 py-2 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-brand-blue/10 flex items-center justify-center shrink-0 mt-0.5">
          <svg className="w-3.5 h-3.5 text-brand-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-text-charcoal text-white rounded-br-md"
            : "bg-surface-secondary text-text-primary rounded-bl-md"
        }`}
      >
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
      </div>
    </div>
  );
}
