"use client";

import Link from "next/link";
import QuickTasks from "@/app/components/chat/quick-tasks";
import { buttonClassName } from "@/app/components/ui/button";

interface ChatWelcomeProps {
  hasNoModel: boolean;
  onPrompt: (prompt: string) => void;
}

const capabilities = [
  {
    icon: "📊",
    title: "分析简历",
    description: "帮你找到核心竞争力",
  },
  {
    icon: "✨",
    title: "优化表述",
    description: "让项目经历更有说服力",
  },
  {
    icon: "🔍",
    title: "查漏补缺",
    description: "全面检查简历完整度",
  },
];

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
            <div className="mt-6 grid grid-cols-3 gap-3">
              {capabilities.map((item) => (
                <div
                  key={item.title}
                  className="rounded-2xl bg-surface-secondary p-4"
                >
                  <div className="text-lg leading-none">{item.icon}</div>
                  <h2 className="mt-2 text-sm font-semibold text-text-primary">
                    {item.title}
                  </h2>
                  <p className="mt-1 text-xs text-text-muted">
                    {item.description}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-6 flex justify-center">
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
