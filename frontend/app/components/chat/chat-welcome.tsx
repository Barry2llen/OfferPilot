"use client";

import Link from "next/link";
import QuickTasks from "@/app/components/chat/quick-tasks";
import { buttonClassName } from "@/app/components/ui/button";

interface ChatWelcomeProps {
  hasNoModel: boolean;
  onPrompt: (prompt: string) => void;
}


export default function ChatWelcome({ hasNoModel, onPrompt }: ChatWelcomeProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="w-full max-w-lg">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-blue/10">
          <svg
            className="h-8 w-8 text-brand-blue"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
        </div>

        <h1 className="font-display text-2xl font-semibold text-text-primary">
          你好，我是 OfferPilot
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          基于大模型的 AI 求职助手，帮你分析简历、准备面试
        </p>

        {hasNoModel ? (
          <div className="mt-6 rounded-2xl border border-dashed border-border-default p-6 text-center">
            <p className="mb-4 text-sm text-text-secondary">
              开始前需要先配置一个 AI 模型
            </p>
            <Link href="/settings/providers" className={buttonClassName()}>
              前往配置
            </Link>
          </div>
        ) : (
          <>
            <div className="mt-8 flex justify-center w-full">
              <QuickTasks onPrompt={onPrompt} disabled={false} />
            </div>

            <p className="mt-6 text-center text-[11px] text-text-muted">
              更多功能正在开发中：JD 分析 · 模拟面试 · 求职追踪
            </p>
          </>
        )}
      </div>
    </div>
  );
}
