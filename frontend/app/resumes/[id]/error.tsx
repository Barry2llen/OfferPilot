"use client";

import Link from "next/link";
import Button, { buttonClassName } from "@/app/components/ui/button";

export default function ResumeDetailError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <div className="electron-titlebar-safe-top min-h-full bg-white">
      <div className="mx-auto max-w-[1080px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        <div className="flex min-h-[520px] flex-col items-center justify-center text-center">
          <h1 className="mb-2 font-display text-xl font-semibold text-text-primary">
            简历详情加载失败
          </h1>
          <p className="mb-6 max-w-md text-sm text-text-secondary">
            {error.message}
          </p>
          <div className="flex justify-center gap-3">
            <Button size="sm" onClick={unstable_retry}>
              重试
            </Button>
            <Link
              href="/resumes"
              className={buttonClassName({ variant: "ghost", size: "sm" })}
            >
              返回列表
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
