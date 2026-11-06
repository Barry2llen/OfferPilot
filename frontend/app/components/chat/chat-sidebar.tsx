import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import { useToast } from "@/app/components/ui/toast";
import { memo, useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { aiChatApi } from "@/app/lib/api/ai";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type { AIChatHistorySummary } from "@/app/lib/api/types";
import { plainPreview } from "@/app/lib/chat/preview";

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
  const { addToast } = useToast();
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [chats, setChats] = useState<AIChatHistorySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const { t } = useTranslation();
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
        setError(err instanceof Error ? err.message : t("errors.loadFailed"));
      }
    } finally {
      if (loadRequestRef.current === requestId && showLoading) {
        setLoading(false);
      }
    }
  }, [t]);

  useEffect(() => {
    load(!hasLoadedRef.current);
  }, [load, chatHistoryVersion]);

  const handleNewChat = () => {
    onNewChat();
    onClose?.();
  };

  const handleDelete = async (threadId: string) => {
    setDeleting(threadId);
    try {
      await aiChatApi.deleteChat(threadId);
      if (activeThreadId === threadId) {
        onNewChat();
      }
      setChats((prev) => prev.filter((c) => c.thread_id !== threadId));
      setConfirmDelete(null);
    } catch {
      addToast(t("errors.deleteFailed"), "error");
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
    const groups: { labelKey: string; items: AIChatHistorySummary[] }[] = [
      { labelKey: "chat.today", items: [] },
      { labelKey: "chat.yesterday", items: [] },
      { labelKey: "chat.recentDays", items: [] },
      { labelKey: "chat.older", items: [] },
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
      <div className="chat-history flex min-h-0 flex-1 flex-col">
        <div className="p-3 border-b border-border-light flex flex-col gap-3">
          <Button variant="primary" size="md" onClick={handleNewChat} className="w-full" pill>
            {t("chat.newChat")}
          </Button>
          <div className="relative">
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input 
              type="text"
              aria-label={t("chat.searchHistory")}
              placeholder={t("chat.searchHistory")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-surface-secondary border border-transparent rounded-full outline-none transition-all placeholder:text-text-muted"
            />
          </div>
        </div>

        <div className="relative min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
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
                  {t("chat.retry")}
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
                <p className="text-sm font-medium text-text-primary mb-1">{t("chat.noHistory")}</p>
                <p className="text-xs text-text-muted">{t("chat.startConversation")}</p>
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
                {t("chat.noMatchingConversation")}
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
                  <motion.div layout key={group.labelKey} className="mb-4 last:mb-0">
                    <div className="px-2.5 pb-1 pt-1">
                      <span className="text-xs font-medium text-text-muted">
                        {t(group.labelKey)}
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
                            className={`group mb-0.5 rounded-lg transition-colors ${
                              isActive
                                ? "bg-text-primary/[0.07]"
                                : "hover:bg-text-primary/[0.04]"
                            }`}
                          >
                            <div className="flex items-start gap-1.5 py-2 pl-2.5 pr-1.5">
                              <button
                                type="button"
                                onClick={() => {
                                  onSelectThread(chat.thread_id);
                                  onClose?.();
                                }}
                                aria-current={isActive ? "true" : undefined}
                                className="flex-1 min-w-0 text-left"
                              >
                                <p className={`truncate text-sm text-text-primary ${isActive ? "font-semibold" : "font-medium"}`}>
                                  {chat.title || t("chat.newConversation")}
                                </p>
                                <p className="text-xs text-text-muted truncate mt-0.5">
                                  {plainPreview(chat.last_message_preview) || t("chat.noMessage")}
                                </p>
                              </button>
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); setConfirmDelete(chat.thread_id); }}
                                disabled={deleting === chat.thread_id}
                                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-text-muted opacity-0 transition-all hover:bg-error-bg hover:text-error-text focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                                title={t("chat.deleteConversation")}
                                aria-label={`${t("chat.deleteConversation")} ${chat.title || t("chat.newConversation")}`}
                              >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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
      <ConfirmDialog open={confirmDelete !== null} title={t("chat.deleteConversationTitle")} message={t("chat.deleteConversationMessage")} loading={!!deleting} onCancel={() => setConfirmDelete(null)} onConfirm={() => { if (confirmDelete) void handleDelete(confirmDelete); }} />
    </>
  );
}

export default memo(ChatSidebar);
