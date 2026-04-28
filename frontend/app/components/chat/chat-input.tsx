"use client";

import { useState, useRef, useEffect } from "react";
import Button from "@/app/components/ui/button";

interface ChatInputProps {
  onSend: (prompt: string) => void;
  onStop: () => void;
  onRetry: () => void;
  isStreaming: boolean;
  isInterrupted: boolean;
  disabled: boolean;
}

export default function ChatInput({
  onSend,
  onStop,
  onRetry,
  isStreaming,
  isInterrupted,
  disabled,
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [input]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-border-light bg-white p-4">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-end gap-3 bg-surface-secondary rounded-2xl p-2 pl-4 border border-border-light focus-within:border-primary-500/30 focus-within:ring-2 focus-within:ring-primary-500/20 transition-all">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              disabled
                ? "请先配置模型选择..."
                : "输入求职相关任务，如「根据这份简历优化项目经历」"
            }
            disabled={disabled}
            rows={1}
            className="flex-1 bg-transparent resize-none text-sm py-2 focus:outline-none text-text-primary placeholder:text-text-muted disabled:text-text-muted/50"
          />
          <div className="flex items-center gap-1.5">
            {isStreaming ? (
              <Button variant="danger" size="sm" onClick={onStop} pill>
                停止
              </Button>
            ) : isInterrupted ? (
              <Button variant="primary" size="sm" onClick={onRetry} pill>
                重试
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                onClick={handleSend}
                disabled={!input.trim() || disabled}
                pill
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </Button>
            )}
          </div>
        </div>
        <p className="text-[11px] text-text-muted text-center mt-2">
          Shift + Enter 换行，Enter 发送
        </p>
      </div>
    </div>
  );
}
