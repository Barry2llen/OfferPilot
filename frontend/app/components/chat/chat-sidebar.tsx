"use client";

import { useState, useEffect, useCallback } from "react";
import { aiChatApi } from "@/app/lib/api/ai";
import { useAppContext, useAppActions } from "@/app/lib/context/app-context";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type { AIChatHistorySummary } from "@/app/lib/api/types";

interface ChatSidebarProps {
  onSelectThread: (threadId: string) => void;
  activeThreadId: string | null;
}

export default function ChatSidebar({
  onSelectThread,
  activeThreadId,
}: ChatSidebarProps) {
  const [chats, setChats] = useState<AIChatHistorySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { state, dispatch } = useAppContext();
  const { setThreadId } = useAppActions();
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await aiChatApi.listChats(50, 0);
      setChats(data.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, state.chatHistoryVersion]);

  const handleNewChat = () => {
    setThreadId(null);
    dispatch({ type: "SET_AGENT_STATUS", payload: "idle" });
    onSelectThread("");
  };

  const handleDelete = async (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleting(threadId);
    try {
      await aiChatApi.deleteChat(threadId);
      if (activeThreadId === threadId) {
        setThreadId(null);
        onSelectThread("");
      }
      setChats((prev) => prev.filter((c) => c.thread_id !== threadId));
    } catch {
      // ignore
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="w-64 shrink-0 border-r border-border-light flex flex-col h-full bg-white">
      <div className="p-3 border-b border-border-light">
        <Button variant="secondary" size="sm" onClick={handleNewChat} className="w-full" pill>
          新对话
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Spinner size="sm" />
          </div>
        ) : error ? (
          <div className="text-center py-8 px-3">
            <p className="text-xs text-error-text mb-2">{error}</p>
            <Button variant="ghost" size="sm" onClick={load}>
              重试
            </Button>
          </div>
        ) : chats.length === 0 ? (
          <p className="text-xs text-text-muted text-center py-8 px-3">
            暂无历史会话
          </p>
        ) : (
          chats.map((chat) => {
            const isActive = activeThreadId === chat.thread_id;

            return (
              <div
                key={chat.thread_id}
                className={`border-b border-border-light/50 transition-colors group ${
                  isActive ? "bg-primary-200/30" : "hover:bg-surface-secondary"
                }`}
              >
                <div className="flex items-start gap-2 px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => onSelectThread(chat.thread_id)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <p className="text-sm font-medium text-text-primary truncate">
                      {chat.title || "新对话"}
                    </p>
                    <p className="text-xs text-text-muted truncate mt-0.5">
                      {chat.last_message_preview || "(无消息)"}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] text-text-muted">
                        {new Date(chat.updated_at).toLocaleDateString("zh-CN")}
                      </span>
                      <span className="text-[10px] text-text-muted">
                        {chat.message_count} 条消息
                      </span>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => handleDelete(chat.thread_id, e)}
                    disabled={deleting === chat.thread_id}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-error-bg transition-all shrink-0 mt-0.5"
                    title="删除"
                  >
                    <svg className="w-3.5 h-3.5 text-text-muted hover:text-error-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
