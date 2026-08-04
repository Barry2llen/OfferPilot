import { memo, useState, useEffect, useCallback, useMemo, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { aiChatApi } from "@/app/lib/api/ai";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type { AIChatHistorySummary } from "@/app/lib/api/types";

interface ChatSidebarProps {
  onSelectThread: (threadId: string) => void;
  onNewChat: () => void;
  activeThreadId: string | null;
  chatHistoryVersion: number;
  onClose?: () => void;
}

function ChatSidebar({
  onSelectThread,
  onNewChat,
  activeThreadId,
  chatHistoryVersion,
  onClose,
}: ChatSidebarProps) {
  const [chats, setChats] = useState<AIChatHistorySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const hasLoadedRef = useRef(false);
  const loadRequestRef = useRef(0);

  const load = useCallback(async (showLoading = false) => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;

    if (showLoading) {
      setLoading(true);
      setError(null);
    }

    try {
      const data = await aiChatApi.listChats(50, 0);
      if (loadRequestRef.current !== requestId) return;

      setChats(data.items);
      setError(null);
      hasLoadedRef.current = true;
    } catch (err: unknown) {
      if (loadRequestRef.current !== requestId) return;

      if (showLoading || !hasLoadedRef.current) {
        setError(err instanceof Error ? err.message : "加载失败");
      }
    } finally {
      if (loadRequestRef.current === requestId && showLoading) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    load(!hasLoadedRef.current);
  }, [load, chatHistoryVersion]);

  const handleNewChat = () => {
    onNewChat();
  };

  const handleDelete = async (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleting(threadId);
    try {
      await aiChatApi.deleteChat(threadId);
      if (activeThreadId === threadId) {
        onNewChat();
      }
      setChats((prev) => prev.filter((c) => c.thread_id !== threadId));
    } catch {
      // ignore
    } finally {
      setDeleting(null);
    }
  };

  const filteredChats = useMemo(() => {
    if (!searchQuery.trim()) return chats;
    const lowerQuery = searchQuery.toLowerCase();
    return chats.filter((c) => 
      c.title?.toLowerCase().includes(lowerQuery) || 
      c.last_message_preview?.toLowerCase().includes(lowerQuery)
    );
  }, [chats, searchQuery]);

  const groupedChats = useMemo(() => {
    const groups: { label: string; items: AIChatHistorySummary[] }[] = [
      { label: "今天", items: [] },
      { label: "昨天", items: [] },
      { label: "最近7天", items: [] },
      { label: "更早", items: [] },
    ];

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const last7Days = new Date(today);
    last7Days.setDate(last7Days.getDate() - 7);

    filteredChats.forEach((chat) => {
      const date = new Date(chat.updated_at);
      if (date >= today) groups[0].items.push(chat);
      else if (date >= yesterday) groups[1].items.push(chat);
      else if (date >= last7Days) groups[2].items.push(chat);
      else groups[3].items.push(chat);
    });

    return groups.filter((g) => g.items.length > 0);
  }, [filteredChats]);

  return (
    <>
      {/* Mobile backdrop */}
      <div 
        className="fixed inset-0 z-20 bg-black/20 backdrop-blur-sm lg:hidden"
        onClick={onClose}
        aria-hidden="true"
      />
      
      {/* Sidebar container */}
      <div className="fixed inset-y-0 left-0 z-30 w-64 shrink-0 border-r border-border-light flex flex-col bg-white transform transition-transform duration-200 lg:relative lg:translate-x-0">
        <div className="p-3 border-b border-border-light flex flex-col gap-3">
          <Button variant="secondary" size="sm" onClick={handleNewChat} className="w-full" pill>
            新对话
          </Button>
          <div className="relative">
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input 
              type="text"
              placeholder="搜索历史..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-surface-secondary border border-transparent rounded-full focus:bg-white focus:border-border-default focus:ring-1 focus:ring-border-default outline-none transition-all placeholder:text-text-muted"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <AnimatePresence initial={false} mode="popLayout">
            {loading ? (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="flex items-center justify-center py-8"
              >
                <Spinner size="sm" />
              </motion.div>
            ) : error ? (
              <motion.div
                key="error"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="text-center py-8 px-3"
              >
                <p className="text-xs text-error-text mb-2">{error}</p>
                <Button variant="ghost" size="sm" onClick={() => load(true)}>
                  重试
                </Button>
              </motion.div>
            ) : chats.length === 0 ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="flex flex-col items-center justify-center py-12 px-4 text-center"
              >
                <svg className="w-16 h-16 text-border-default mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <p className="text-sm font-medium text-text-primary mb-1">暂无历史会话</p>
                <p className="text-xs text-text-muted">开始一段新的对话吧</p>
              </motion.div>
            ) : filteredChats.length === 0 ? (
              <motion.p
                key="no-results"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="text-xs text-text-muted text-center py-8 px-3"
              >
                未找到相关会话
              </motion.p>
            ) : (
              <motion.div
                key="list"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="py-2"
              >
                {groupedChats.map((group) => (
                  <motion.div layout key={group.label} className="mb-4 last:mb-0">
                    <div className="px-3 py-1">
                      <span className="text-[10px] font-semibold tracking-wider text-text-muted uppercase">
                        {group.label}
                      </span>
                    </div>
                    <AnimatePresence initial={false}>
                      {group.items.map((chat) => {
                        const isActive = activeThreadId === chat.thread_id;

                        return (
                          <motion.div
                            layout
                            key={chat.thread_id}
                            initial={{ opacity: 0, y: -6, scale: 0.98 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: -4, scale: 0.98 }}
                            transition={{ duration: 0.18, ease: "easeOut" }}
                            className={`transition-colors group ${
                              isActive ? "bg-primary-200/30" : "hover:bg-surface-secondary"
                            }`}
                          >
                            <div className="flex items-start gap-2 px-3 py-2.5">
                              <button
                                type="button"
                                onClick={() => {
                                  onSelectThread(chat.thread_id);
                                }}
                                className="flex-1 min-w-0 text-left"
                              >
                                <p className="text-sm font-medium text-text-primary truncate">
                                  {chat.title || "新对话"}
                                </p>
                                <p className="text-xs text-text-muted truncate mt-0.5">
                                  {chat.last_message_preview || "(无消息)"}
                                </p>
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
                          </motion.div>
                        );
                      })}
                    </AnimatePresence>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </>
  );
}

export default memo(ChatSidebar);
