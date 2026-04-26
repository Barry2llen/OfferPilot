"use client";

import { useState, useEffect } from "react";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { resumesApi } from "@/app/lib/api/resumes";
import { useAppContext, useAppActions } from "@/app/lib/context/app-context";
import Card from "@/app/components/ui/card";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import type { ModelSelectionResponse, ResumeListItem } from "@/app/lib/api/types";

export default function ContextPanel() {
  const { state } = useAppContext();
  const { setModelSelection, setResumeId } = useAppActions();

  const [models, setModels] = useState<ModelSelectionResponse[]>([]);
  const [resumes, setResumes] = useState<ResumeListItem[]>([]);

  useEffect(() => {
    modelSelectionsApi.list().then(setModels).catch(() => {});
    resumesApi.list().then(setResumes).catch(() => {});
  }, [state.agentStatus]); // refresh on status change

  const statusLabel =
    state.agentStatus === "idle"
      ? "就绪"
      : state.agentStatus === "generating"
        ? "生成中..."
        : state.agentStatus === "tool_calling"
          ? "调用工具..."
          : state.agentStatus === "interrupted"
            ? "已中断"
            : "出错";

  const statusColor =
    state.agentStatus === "idle"
      ? "bg-success-text"
      : state.agentStatus === "error"
        ? "bg-error-text"
        : "bg-primary-500 animate-pulse";

  return (
    <div className="w-72 shrink-0 border-l border-border-light bg-white flex flex-col h-full overflow-y-auto">
      <div className="p-4 border-b border-border-light">
        <h3 className="font-display text-sm font-semibold text-text-primary mb-3">
          上下文与状态
        </h3>

        {/* Agent status */}
        <div className="flex items-center gap-2 mb-4">
          <span className={`w-2 h-2 rounded-full ${statusColor}`} />
          <span className="text-xs text-text-secondary">{statusLabel}</span>
        </div>

        {/* Model selector */}
        <div className="mb-4">
          <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1.5 block">
            当前模型
          </label>
          <select
            value={state.currentModelSelection ?? ""}
            onChange={(e) => setModelSelection(e.target.value ? Number(e.target.value) : null)}
            className="w-full rounded-xl border border-border-default px-3 py-2 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
          >
            <option value="">未选择</option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.provider.name} / {m.model_name}
              </option>
            ))}
          </select>
          {models.length === 0 && (
            <p className="text-[10px] text-text-muted mt-1">
              暂无可用模型
            </p>
          )}
        </div>

        {/* Resume context */}
        <div className="mb-4">
          <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1.5 block">
            当前简历
          </label>
          <select
            value={state.currentResumeId ?? ""}
            onChange={(e) => setResumeId(e.target.value ? Number(e.target.value) : null)}
            className="w-full rounded-xl border border-border-default px-3 py-2 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
          >
            <option value="">未选择</option>
            {resumes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.original_filename || `简历 #${r.id}`}
              </option>
            ))}
          </select>
          {resumes.length === 0 && (
            <p className="text-[10px] text-text-muted mt-1">
              暂无简历
            </p>
          )}
        </div>

        {/* Thread ID */}
        {state.currentThreadId && (
          <div>
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1.5 block">
              会话线程
            </label>
            <code className="font-mono text-[11px] text-text-secondary bg-surface-secondary px-2 py-1 rounded block truncate">
              {state.currentThreadId}
            </code>
          </div>
        )}
      </div>

      {/* Tools status */}
      <div className="p-4">
        <h4 className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-2">
          可用工具
        </h4>
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <span className="w-1.5 h-1.5 rounded-full bg-success-text" />
            Exa Web Search
          </div>
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="w-1.5 h-1.5 rounded-full bg-border-default" />
            简历解析器
          </div>
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="w-1.5 h-1.5 rounded-full bg-border-default" />
            JD 分析器
          </div>
        </div>
      </div>
    </div>
  );
}
